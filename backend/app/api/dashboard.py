"""
Dashboard API routes.
Provides summary statistics and quick access data.
"""
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func

from app.db.session import get_db
from app.db.models import (
    Teacher, Subject, Semester, Room, Allocation,
    TeacherAbsence, Substitution, SubstitutionStatus
)
from app.schemas.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics."""
    today = date.today()
    
    total_teachers = db.query(func.count(Teacher.id)).filter(
        Teacher.is_active == True
    ).scalar() or 0
    
    total_subjects = db.query(func.count(Subject.id)).scalar() or 0
    
    total_semesters = db.query(func.count(Semester.id)).scalar() or 0
    
    total_rooms = db.query(func.count(Room.id)).filter(
        Room.is_available == True
    ).scalar() or 0
    
    total_allocations = db.query(func.count(Allocation.id)).scalar() or 0
    
    active_substitutions = db.query(func.count(Substitution.id)).filter(
        Substitution.status.in_([SubstitutionStatus.PENDING, SubstitutionStatus.ASSIGNED])
    ).scalar() or 0
    
    teachers_absent_today = db.query(func.count(TeacherAbsence.id)).filter(
        TeacherAbsence.absence_date == today
    ).scalar() or 0
    
    return DashboardStats(
        total_teachers=total_teachers,
        total_subjects=total_subjects,
        total_semesters=total_semesters,
        total_rooms=total_rooms,
        total_allocations=total_allocations,
        active_substitutions=active_substitutions,
        teachers_absent_today=teachers_absent_today
    )


@router.get("/recent-substitutions")
def get_recent_substitutions(
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """Get recent substitutions for dashboard display."""
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
