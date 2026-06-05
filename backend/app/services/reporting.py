"""
Reporting and analytics services (READ-ONLY).
Computes accreditation reports and teacher load dashboards from generated timetables.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import math

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.core.config import get_settings
from app.db.models import (
    Allocation,
    Teacher,
    Subject,
    Semester,
    Room,
    Department,
    ClassSubjectTeacher,
    ComponentType,
    subject_semesters,
)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _parse_available_days(value: Optional[str]) -> List[int]:
    if not value:
        return list(range(5))
    parts = [p.strip() for p in value.split(",") if p.strip() != ""]
    days: List[int] = []
    for part in parts:
        try:
            day = int(part)
            if 0 <= day <= 4:
                days.append(day)
        except ValueError:
            continue
    return days if days else list(range(5))


def _max_consecutive(slots: List[int]) -> int:
    if not slots:
        return 0
    slots_sorted = sorted(slots)
    max_run = 1
    run = 1
    for idx in range(1, len(slots_sorted)):
        if slots_sorted[idx] == slots_sorted[idx - 1] + 1:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    return max_run


def _get_departments_map(db: Session) -> Dict[int, Department]:
    return {d.id: d for d in db.query(Department).all()}


def _allocation_query(
    db: Session,
    dept_id: Optional[int] = None,
    year: Optional[int] = None,
):
    query = db.query(Allocation).options(
        joinedload(Allocation.teacher),
        joinedload(Allocation.subject),
        joinedload(Allocation.semester),
        joinedload(Allocation.room),
    )

    if dept_id or year is not None:
        query = query.join(Semester, Allocation.semester_id == Semester.id).join(
            Subject, Allocation.subject_id == Subject.id
        )

    if dept_id:
        query = query.filter(
            (Semester.dept_id == dept_id) | (Subject.dept_id == dept_id)
        )

    if year is not None:
        query = query.filter(Semester.year == year)

    return query


def build_teacher_workload_report(db: Session, dept_id: Optional[int] = None) -> dict:
    settings = get_settings()
    allocations = _allocation_query(db, dept_id=dept_id).all()

    dept_map = _get_departments_map(db)

    teachers_query = db.query(Teacher)
    if dept_id:
        teachers_query = teachers_query.filter(Teacher.dept_id == dept_id)
    teachers = teachers_query.all()

    metrics: Dict[int, dict] = {}
    teacher_day_slots: Dict[int, Dict[int, Set[int]]] = {}
    teacher_departments: Dict[int, Set[int]] = {}

    def _ensure_teacher(teacher: Teacher):
        if teacher.id not in metrics:
            metrics[teacher.id] = {
                "teacher_id": teacher.id,
                "teacher_name": teacher.name,
                "teacher_code": teacher.teacher_code,
                "total_hours": 0,
                "theory_hours": 0,
                "lab_hours": 0,
                "tutorial_hours": 0,
                "project_hours": 0,
                "report_hours": 0,
                "self_study_hours": 0,
                "seminar_hours": 0,
                "elective_hours": 0,
                "max_consecutive_periods": 0,
                "free_periods": 0,
                "departments": [],
                "available_days": _parse_available_days(teacher.available_days),
            }
            teacher_day_slots[teacher.id] = {d: set() for d in range(5)}
            teacher_departments[teacher.id] = set()

    for teacher in teachers:
        _ensure_teacher(teacher)

    for alloc in allocations:
        if not alloc.teacher:
            continue
        _ensure_teacher(alloc.teacher)

        data = metrics[alloc.teacher.id]
        data["total_hours"] += 1

        comp = getattr(alloc, "academic_component", None) or (
            alloc.component_type.value if alloc.component_type else "theory"
        )
        if comp == "lab":
            data["lab_hours"] += 1
        elif comp == "tutorial":
            data["tutorial_hours"] += 1
        elif comp == "project":
            data["project_hours"] += 1
        elif comp == "report":
            data["report_hours"] += 1
        elif comp == "self_study":
            data["self_study_hours"] += 1
        elif comp == "seminar":
            data["seminar_hours"] += 1
        else:
            data["theory_hours"] += 1

        if getattr(alloc, "is_elective", False):
            data["elective_hours"] += 1

        teacher_day_slots[alloc.teacher.id][alloc.day].add(alloc.slot)

        if alloc.semester and alloc.semester.dept_id:
            teacher_departments[alloc.teacher.id].add(alloc.semester.dept_id)
        if alloc.subject and alloc.subject.dept_id:
            teacher_departments[alloc.teacher.id].add(alloc.subject.dept_id)

    for teacher_id, data in metrics.items():
        max_consecutive = 0
        for day_slots in teacher_day_slots.get(teacher_id, {}).values():
            max_consecutive = max(max_consecutive, _max_consecutive(list(day_slots)))
        data["max_consecutive_periods"] = max_consecutive

        available_days = data.get("available_days", list(range(5)))
        total_slots = len(available_days) * settings.SLOTS_PER_DAY
        data["free_periods"] = max(total_slots - data["total_hours"], 0)

        dept_ids = teacher_departments.get(teacher_id, set())
        data["departments"] = [
            {"id": d_id, "name": dept_map[d_id].name, "code": dept_map[d_id].code}
            for d_id in sorted(dept_ids)
            if d_id in dept_map
        ]

        data.pop("available_days", None)

    department_summary = None
    if dept_id and dept_id in dept_map:
        dept = dept_map[dept_id]
        department_summary = {"id": dept.id, "name": dept.name, "code": dept.code}

    rows = sorted(metrics.values(), key=lambda r: (r["teacher_name"] or ""))

    return {
        "generated_at": datetime.utcnow(),
        "dept_id": dept_id,
        "department": department_summary,
        "total_teachers": len(rows),
        "rows": rows,
    }


def build_room_utilization_report(db: Session, dept_id: Optional[int] = None) -> dict:
    settings = get_settings()
    dept_map = _get_departments_map(db)

    rooms_query = db.query(Room)
    if dept_id:
        rooms_query = rooms_query.filter(
            (Room.dept_id == dept_id) | (Room.dept_id.is_(None))
        )
    rooms = rooms_query.all()

    allocations = _allocation_query(db, dept_id=dept_id).all()

    usage_counts: Dict[int, int] = {}
    usage_by_day: Dict[int, Dict[int, int]] = {}

    for alloc in allocations:
        room_id = alloc.room_id
        usage_counts[room_id] = usage_counts.get(room_id, 0) + 1
        if room_id not in usage_by_day:
            usage_by_day[room_id] = {d: 0 for d in range(5)}
        usage_by_day[room_id][alloc.day] += 1

    rows = []
    for room in rooms:
        total_available = settings.SLOTS_PER_DAY * len(DAY_NAMES) if room.is_available else 0
        used = usage_counts.get(room.id, 0)
        utilization = (used / total_available * 100.0) if total_available else 0.0

        day_counts = usage_by_day.get(room.id, {d: 0 for d in range(5)})
        max_day_count = max(day_counts.values()) if day_counts else 0
        peak_days = (
            [DAY_NAMES[d] for d, count in day_counts.items() if count == max_day_count and count > 0]
            if max_day_count > 0
            else []
        )

        rows.append({
            "room_id": room.id,
            "room_name": room.name,
            "room_type": room.room_type,
            "total_available_periods": total_available,
            "periods_used": used,
            "utilization_percent": round(utilization, 2),
            "peak_usage_days": peak_days,
        })

    department_summary = None
    if dept_id and dept_id in dept_map:
        dept = dept_map[dept_id]
        department_summary = {"id": dept.id, "name": dept.name, "code": dept.code}

    rows = sorted(rows, key=lambda r: r["room_name"])

    return {
        "generated_at": datetime.utcnow(),
        "dept_id": dept_id,
        "department": department_summary,
        "total_rooms": len(rows),
        "rows": rows,
    }


def build_subject_coverage_report(db: Session, dept_id: Optional[int] = None) -> dict:
    dept_map = _get_departments_map(db)

    pairs_query = db.query(Subject, Semester).join(
        subject_semesters, Subject.id == subject_semesters.c.subject_id
    ).join(Semester, Semester.id == subject_semesters.c.semester_id)

    if dept_id:
        pairs_query = pairs_query.filter(Semester.dept_id == dept_id)

    subject_pairs = pairs_query.all()

    allocations = _allocation_query(db, dept_id=dept_id).all()

    assigned_counts: Dict[Tuple[int, int], int] = {}
    assigned_teachers: Dict[Tuple[int, int], Set[Tuple[str, str]]] = {}

    for alloc in allocations:
        key = (alloc.subject_id, alloc.semester_id)
        assigned_counts[key] = assigned_counts.get(key, 0) + 1
        if alloc.teacher:
            if key not in assigned_teachers:
                assigned_teachers[key] = set()
            assigned_teachers[key].add(
                (alloc.teacher.name, alloc.teacher.teacher_code or "")
            )

    # Include fixed teacher mappings if no allocation-based teachers exist yet
    # OPTIMIZED: filter by dept_id when available instead of loading ALL rows
    cst_query = db.query(ClassSubjectTeacher)
    teacher_query = db.query(Teacher)
    if dept_id:
        dept_sem_ids = [
            sid for (sid,) in db.query(Semester.id).filter(Semester.dept_id == dept_id).all()
        ]
        if dept_sem_ids:
            cst_query = cst_query.filter(ClassSubjectTeacher.semester_id.in_(dept_sem_ids))
        teacher_query = teacher_query.filter(Teacher.dept_id == dept_id)

    class_assignments = cst_query.all()
    assignment_map: Dict[Tuple[int, int], Set[Tuple[str, str]]] = {}
    teacher_lookup = {t.id: t for t in teacher_query.all()}
    for assign in class_assignments:
        key = (assign.subject_id, assign.semester_id)
        if key not in assignment_map:
            assignment_map[key] = set()
        teacher = teacher_lookup.get(assign.teacher_id)
        if teacher:
            assignment_map[key].add((teacher.name, teacher.teacher_code or ""))

    rows = []
    for subject, semester in subject_pairs:
        key = (subject.id, semester.id)
        required = subject.total_weekly_hours
        assigned = assigned_counts.get(key, 0)
        status = "Complete" if assigned >= required else "Incomplete"

        teachers_set = assigned_teachers.get(key, set())
        if not teachers_set and key in assignment_map:
            teachers_set = assignment_map[key]

        teacher_names = [t[0] for t in sorted(teachers_set)]
        teacher_codes = [t[1] for t in sorted(teachers_set)]

        dept_name = None
        dept_id_value = semester.dept_id or subject.dept_id
        if dept_id_value and dept_id_value in dept_map:
            dept_name = dept_map[dept_id_value].name

        rows.append({
            "subject_id": subject.id,
            "subject_code": subject.code,
            "subject_name": subject.name,
            "required_hours": required,
            "assigned_hours": assigned,
            "status": status,
            "teacher_names": teacher_names,
            "teacher_codes": teacher_codes,
            "dept_id": dept_id_value,
            "department": dept_name,
            "year": semester.year,
            "section": semester.section,
            "semester_id": semester.id,
            "semester_name": semester.name,
            "semester_code": semester.code,
        })

    department_summary = None
    if dept_id and dept_id in dept_map:
        dept = dept_map[dept_id]
        department_summary = {"id": dept.id, "name": dept.name, "code": dept.code}

    rows = sorted(rows, key=lambda r: (r["semester_code"] or "", r["subject_code"] or ""))

    return {
        "generated_at": datetime.utcnow(),
        "dept_id": dept_id,
        "department": department_summary,
        "total_subjects": len(rows),
        "rows": rows,
    }


def build_teacher_load_dashboard(
    db: Session,
    dept_id: Optional[int] = None,
    year: Optional[int] = None,
) -> dict:
    settings = get_settings()
    dept_map = _get_departments_map(db)

    allocations = _allocation_query(db, dept_id=dept_id, year=year).all()

    teachers_query = db.query(Teacher)
    if dept_id:
        teachers_query = teachers_query.filter(Teacher.dept_id == dept_id)
    teachers = teachers_query.all()

    metrics: Dict[int, dict] = {}
    teacher_day_slots: Dict[int, Dict[int, Set[int]]] = {}
    teacher_departments: Dict[int, Set[int]] = {}

    def _ensure_teacher(teacher: Teacher):
        if teacher.id not in metrics:
            metrics[teacher.id] = {
                "teacher_id": teacher.id,
                "teacher_name": teacher.name,
                "teacher_code": teacher.teacher_code,
                "total_hours": 0,
                "theory_hours": 0,
                "lab_hours": 0,
                "tutorial_hours": 0,
                "project_hours": 0,
                "report_hours": 0,
                "self_study_hours": 0,
                "seminar_hours": 0,
                "elective_hours": 0,
                "max_consecutive_periods": 0,
                "days_with_overload": 0,
                "max_hours_per_week": teacher.max_hours_per_week,
                "max_consecutive_allowed": teacher.max_consecutive_classes,
                "load_ratio": 0.0,
                "status": "normal",
                "consecutive_overload": False,
                "departments": [],
                "available_days": _parse_available_days(teacher.available_days),
            }
            teacher_day_slots[teacher.id] = {d: set() for d in range(5)}
            teacher_departments[teacher.id] = set()

    for teacher in teachers:
        _ensure_teacher(teacher)

    for alloc in allocations:
        if not alloc.teacher:
            continue
        _ensure_teacher(alloc.teacher)
        data = metrics[alloc.teacher.id]
        data["total_hours"] += 1

        comp = getattr(alloc, "academic_component", None) or (
            alloc.component_type.value if alloc.component_type else "theory"
        )
        if comp == "lab":
            data["lab_hours"] += 1
        elif comp == "tutorial":
            data["tutorial_hours"] += 1
        elif comp == "project":
            data["project_hours"] += 1
        elif comp == "report":
            data["report_hours"] += 1
        elif comp == "self_study":
            data["self_study_hours"] += 1
        elif comp == "seminar":
            data["seminar_hours"] += 1
        else:
            data["theory_hours"] += 1

        if getattr(alloc, "is_elective", False):
            data["elective_hours"] += 1

        teacher_day_slots[alloc.teacher.id][alloc.day].add(alloc.slot)

        if alloc.semester and alloc.semester.dept_id:
            teacher_departments[alloc.teacher.id].add(alloc.semester.dept_id)
        if alloc.subject and alloc.subject.dept_id:
            teacher_departments[alloc.teacher.id].add(alloc.subject.dept_id)

    for teacher_id, data in metrics.items():
        day_slots = teacher_day_slots.get(teacher_id, {})
        max_consecutive = 0
        for slots in day_slots.values():
            max_consecutive = max(max_consecutive, _max_consecutive(list(slots)))
        data["max_consecutive_periods"] = max_consecutive

        available_days = data.get("available_days", list(range(5)))
        per_day_limit = 0
        if available_days:
            per_day_limit = math.ceil(data["max_hours_per_week"] / len(available_days))
        overload_days = 0
        for day in available_days:
            if len(day_slots.get(day, set())) > per_day_limit and per_day_limit > 0:
                overload_days += 1
        data["days_with_overload"] = overload_days

        max_hours = data["max_hours_per_week"] or 0
        data["load_ratio"] = round((data["total_hours"] / max_hours), 2) if max_hours else 0.0

        if data["load_ratio"] > 1.0:
            data["status"] = "overload"
        elif data["load_ratio"] >= 0.85:
            data["status"] = "high"
        else:
            data["status"] = "normal"

        data["consecutive_overload"] = (
            data["max_consecutive_periods"] > data["max_consecutive_allowed"]
        )

        dept_ids = teacher_departments.get(teacher_id, set())
        data["departments"] = [
            {"id": d_id, "name": dept_map[d_id].name, "code": dept_map[d_id].code}
            for d_id in sorted(dept_ids)
            if d_id in dept_map
        ]

        data.pop("available_days", None)

    department_summary = None
    if dept_id and dept_id in dept_map:
        dept = dept_map[dept_id]
        department_summary = {"id": dept.id, "name": dept.name, "code": dept.code}

    rows = sorted(metrics.values(), key=lambda r: (r["status"], r["teacher_name"] or ""))

    return {
        "generated_at": datetime.utcnow(),
        "dept_id": dept_id,
        "year": year,
        "department": department_summary,
        "total_teachers": len(rows),
        "rows": rows,
    }
