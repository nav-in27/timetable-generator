"""
Dashboard API routes.
Provides summary statistics and quick access data.

OPTIMIZATIONS (v2):
- Cached dashboard stats (30s TTL) to prevent repeated COUNT queries
- Single-query approach where possible
- Null-safe error handling with graceful degradation
"""
from datetime import date
from typing import Optional
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func

from app.db.session import get_db
from app.db.models import (
    Teacher, Subject, Semester, Room, Allocation,
    TeacherAbsence, Substitution, SubstitutionStatus,
    ElectiveBasket, FixedSlot
)
from app.schemas.schemas import DashboardStats, TeacherLoadDashboard
from app.services.reporting import build_teacher_load_dashboard
from app.core.cache import cache

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = logging.getLogger("app.dashboard")


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    dept_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get dashboard statistics, optionally scoped to a department. Cached for 30s."""
    cache_key = f"dashboard_stats:{dept_id or 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    today = date.today()

    try:
        # Teachers
        t_query = db.query(func.count(Teacher.id)).filter(Teacher.is_active == True)
        if dept_id:
            t_query = t_query.filter(Teacher.dept_id == dept_id)
        total_teachers = t_query.scalar() or 0

        # Subjects
        s_query = db.query(func.count(Subject.id))
        if dept_id:
            s_query = s_query.filter(Subject.dept_id == dept_id)
        total_subjects = s_query.scalar() or 0

        # Semesters
        sem_query = db.query(func.count(Semester.id))
        if dept_id:
            sem_query = sem_query.filter(Semester.dept_id == dept_id)
        total_semesters = sem_query.scalar() or 0

        # Rooms (shared rooms have dept_id=None and are accessible by all)
        r_query = db.query(func.count(Room.id)).filter(Room.is_available == True)
        if dept_id:
            r_query = r_query.filter((Room.dept_id == dept_id) | (Room.dept_id.is_(None)))
        total_rooms = r_query.scalar() or 0

        # Dept semester IDs (reused for allocations and fixed slots)
        dept_sem_ids = None
        if dept_id:
            dept_sem_ids = [
                sid for (sid,) in
                db.query(Semester.id).filter(Semester.dept_id == dept_id).all()
            ]

        # Allocations (filter via semester.dept_id)
        alloc_query = db.query(func.count(Allocation.id))
        if dept_id:
            if dept_sem_ids:
                alloc_query = alloc_query.filter(Allocation.semester_id.in_(dept_sem_ids))
            else:
                alloc_query = alloc_query.filter(Allocation.id < 0)  # No results
        total_allocations = alloc_query.scalar() or 0

        # Elective Baskets (filter via participating semesters' department)
        eb_query = db.query(func.count(ElectiveBasket.id))
        # ElectiveBasket filtering by dept is complex (via participating_semesters),
        # so we keep it global for now — baskets are typically college-wide
        total_elective_baskets = eb_query.scalar() or 0

        # Fixed Slots (filter via semester)
        fs_query = db.query(func.count(FixedSlot.id))
        if dept_id:
            if dept_sem_ids:
                fs_query = fs_query.filter(FixedSlot.semester_id.in_(dept_sem_ids))
            else:
                fs_query = fs_query.filter(FixedSlot.id < 0)  # No results
        total_fixed_slots = fs_query.scalar() or 0

        # Substitutions & absences — kept global for safety
        active_substitutions = db.query(func.count(Substitution.id)).filter(
            Substitution.status.in_([SubstitutionStatus.PENDING, SubstitutionStatus.ASSIGNED])
        ).scalar() or 0

        teachers_absent_today = db.query(func.count(TeacherAbsence.id)).filter(
            TeacherAbsence.absence_date == today
        ).scalar() or 0

        result = DashboardStats(
            total_teachers=total_teachers,
            total_subjects=total_subjects,
            total_semesters=total_semesters,
            total_rooms=total_rooms,
            total_allocations=total_allocations,
            total_elective_baskets=total_elective_baskets,
            total_fixed_slots=total_fixed_slots,
            active_substitutions=active_substitutions,
            teachers_absent_today=teachers_absent_today,
        )

        # Cache for 30 seconds
        cache.set(cache_key, result, ttl=30, tags=["dashboard", "allocations"])
        return result
    except Exception as e:
        logger.error(f"Dashboard stats failed (dept_id={dept_id}): {e}", exc_info=True)
        return DashboardStats(
            total_teachers=0,
            total_subjects=0,
            total_semesters=0,
            total_rooms=0,
            total_allocations=0,
            total_elective_baskets=0,
            total_fixed_slots=0,
            active_substitutions=0,
            teachers_absent_today=0,
        )


@router.get("/recent-substitutions")
def get_recent_substitutions(
    limit: int = 5,
    db: Session = Depends(get_db),
):
    """Get recent substitutions for dashboard display."""
    try:
        recent = db.query(Substitution).options(
            selectinload(Substitution.original_teacher),
            selectinload(Substitution.substitute_teacher),
            selectinload(Substitution.allocation).selectinload(Allocation.subject)
        ).order_by(
            Substitution.created_at.desc()
        ).limit(limit).all()

        result = []
        for sub in recent:
            result.append({
                "id": sub.id,
                "date": sub.substitution_date.isoformat(),
                "original_teacher": sub.original_teacher.name if sub.original_teacher else "Unknown",
                "substitute_teacher": sub.substitute_teacher.name if sub.substitute_teacher else "Unknown",
                "subject": sub.allocation.subject.name if sub.allocation and sub.allocation.subject else "Unknown",
                "status": sub.status.value
            })

        return result
    except Exception as e:
        logger.error(f"Recent substitutions failed: {e}", exc_info=True)
        return []


@router.get("/teacher-load", response_model=TeacherLoadDashboard)
def get_teacher_load_dashboard(
    dept_id: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Teacher load dashboard (READ-ONLY). Cached for 60s."""
    cache_key = f"teacher_load:{dept_id or 'all'}:{year or 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = build_teacher_load_dashboard(db, dept_id=dept_id, year=year)
    cache.set(cache_key, result, ttl=60, tags=["dashboard", "reports", "teachers"])
    return result
