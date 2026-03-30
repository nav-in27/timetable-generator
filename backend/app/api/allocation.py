"""
Modules 3-6: Preference Allocation, Assignment Storage, Admin Override, Workload Dashboard
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.db.session import get_db
from app.db.models import (
    ClassSubjectTeacher, ComponentType, Teacher, Subject, Semester,
    SystemSetting, Allocation,
)

router = APIRouter(prefix="/allocation", tags=["Allocation"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────


class AssignmentResponse(BaseModel):
    id: int
    teacher_id: int
    teacher_name: Optional[str] = None
    subject_id: int
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    component_type: str
    weekly_hours: int = 0
    is_locked: bool = False
    assignment_reason: Optional[str] = None

    class Config:
        from_attributes = True


class AssignmentUpdate(BaseModel):
    teacher_id: Optional[int] = None
    class_id: Optional[int] = None
    is_locked: Optional[bool] = None


class SwapRequest(BaseModel):
    assignment_id_a: int
    assignment_id_b: int



class WorkloadEntry(BaseModel):
    teacher_id: int
    teacher_name: str
    theory_subjects: int = 0
    labs: int = 0
    total_weekly_hours: float = 0
    status: str = "Balanced"



# ── Module 4 & 5: Assignment CRUD + Admin Override ────────────────────────

@router.get("/assignments", response_model=List[AssignmentResponse])
def list_assignments(
    department_id: Optional[int] = None,
    semester_id: Optional[int] = None,
    teacher_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List all teacher-class-subject assignments with enriched data."""
    q = db.query(ClassSubjectTeacher)
    if semester_id:
        q = q.filter(ClassSubjectTeacher.semester_id == semester_id)
    if teacher_id:
        q = q.filter(ClassSubjectTeacher.teacher_id == teacher_id)
    if department_id:
        q = q.join(Semester, ClassSubjectTeacher.semester_id == Semester.id).filter(
            Semester.dept_id == department_id
        )

    rows = q.order_by(ClassSubjectTeacher.semester_id, ClassSubjectTeacher.subject_id).all()

    results = []
    for r in rows:
        teacher = db.query(Teacher).filter(Teacher.id == r.teacher_id).first()
        subject = db.query(Subject).filter(Subject.id == r.subject_id).first()
        semester = db.query(Semester).filter(Semester.id == r.semester_id).first()

        weekly_hours = 0
        if subject:
            if r.component_type == ComponentType.THEORY:
                weekly_hours = subject.theory_hours_per_week
            elif r.component_type == ComponentType.LAB:
                weekly_hours = subject.lab_hours_per_week
            elif r.component_type == ComponentType.TUTORIAL:
                weekly_hours = subject.tutorial_hours_per_week

        results.append(AssignmentResponse(
            id=r.id,
            teacher_id=r.teacher_id,
            teacher_name=teacher.name if teacher else None,
            subject_id=r.subject_id,
            subject_name=subject.name if subject else None,
            subject_code=subject.code if subject else None,
            class_id=r.semester_id,
            class_name=semester.name if semester else None,
            component_type=r.component_type.value,
            weekly_hours=weekly_hours,
            is_locked=r.is_locked,
            assignment_reason=r.assignment_reason,
        ))

    return results


@router.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: int, data: AssignmentUpdate, db: Session = Depends(get_db)):
    """
    Admin override: change teacher, class, or lock status of an assignment.
    """
    row = db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.id == assignment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if data.teacher_id is not None:
        teacher = db.query(Teacher).filter(Teacher.id == data.teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")
        row.teacher_id = data.teacher_id

    if data.class_id is not None:
        sem = db.query(Semester).filter(Semester.id == data.class_id).first()
        if not sem:
            raise HTTPException(status_code=404, detail="Class not found")
        row.semester_id = data.class_id

    if data.is_locked is not None:
        row.is_locked = data.is_locked

    db.commit()
    db.refresh(row)
    return {"detail": "Assignment updated", "id": assignment_id}


@router.post("/assignments/swap")
def swap_assignments(req: SwapRequest, db: Session = Depends(get_db)):
    """Swap teachers between two assignments."""
    a = db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.id == req.assignment_id_a).first()
    b = db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.id == req.assignment_id_b).first()
    if not a or not b:
        raise HTTPException(status_code=404, detail="One or both assignments not found")

    if a.is_locked or b.is_locked:
        raise HTTPException(status_code=400, detail="Cannot swap locked assignments")

    a.teacher_id, b.teacher_id = b.teacher_id, a.teacher_id
    db.commit()
    return {"detail": "Swapped teachers between assignments", "ids": [a.id, b.id]}


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, db: Session = Depends(get_db)):
    """Delete an assignment (admin override)."""
    row = db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.id == assignment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if row.is_locked:
        raise HTTPException(status_code=400, detail="Cannot delete a locked assignment. Unlock it first.")
    db.delete(row)
    db.commit()
    return {"detail": "Assignment deleted", "id": assignment_id}


@router.put("/assignments/{assignment_id}/lock")
def lock_assignment(assignment_id: int, db: Session = Depends(get_db)):
    """Lock an assignment so the allocation engine cannot modify it."""
    row = db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.id == assignment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    row.is_locked = True
    db.commit()
    return {"detail": "Assignment locked", "id": assignment_id}


@router.put("/assignments/{assignment_id}/unlock")
def unlock_assignment(assignment_id: int, db: Session = Depends(get_db)):
    """Unlock an assignment."""
    row = db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.id == assignment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    row.is_locked = False
    db.commit()
    return {"detail": "Assignment unlocked", "id": assignment_id}


# ── Module 6: Faculty Workload Dashboard ──────────────────────────────────

@router.get("/workload", response_model=List[WorkloadEntry])
def get_faculty_workload(
    department_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Faculty Workload Dashboard data.
    Shows theory count, lab count, total weekly hours, and status per teacher.
    """
    q = db.query(Teacher).filter(Teacher.is_active == True)
    if department_id:
        q = q.filter(Teacher.dept_id == department_id)

    teachers = q.order_by(Teacher.name).all()
    results = []

    for teacher in teachers:
        assignments = db.query(ClassSubjectTeacher).filter(
            ClassSubjectTeacher.teacher_id == teacher.id
        ).all()

        theory_count = 0
        lab_count = 0
        total_hours = 0.0

        for a in assignments:
            subj = db.query(Subject).filter(Subject.id == a.subject_id).first()
            if not subj:
                continue

            # Base weekly hours are part of total workload accounting.
            base_hours = subj.weekly_hours or 0

            if a.component_type == ComponentType.THEORY:
                theory_count += 1
                total_hours += max(subj.theory_hours_per_week, base_hours)
            elif a.component_type == ComponentType.LAB:
                lab_count += 1
                total_hours += max(subj.lab_hours_per_week, base_hours)
            elif a.component_type == ComponentType.TUTORIAL:
                total_hours += max(subj.tutorial_hours_per_week, base_hours)

        if total_hours <= 12:
            status = "Underload"
        elif total_hours <= 16:
            status = "Balanced"
        else:
            status = "Overload"

        results.append(WorkloadEntry(
            teacher_id=teacher.id,
            teacher_name=teacher.name,
            theory_subjects=theory_count,
            labs=lab_count,
            total_weekly_hours=total_hours,
            status=status,
        ))

    return results
