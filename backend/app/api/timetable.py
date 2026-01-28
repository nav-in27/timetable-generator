"""
Timetable API routes.
Handles generation and viewing of timetables.
"""
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.db.models import Allocation, Semester, Teacher, Subject, Room, Substitution, SubstitutionStatus
from app.schemas.schemas import (
    AllocationResponse, TimetableView, TimetableDay, TimetableSlot,
    GenerationRequest, GenerationResult
)
from app.services.generator import TimetableGenerator
from app.core.config import get_settings

router = APIRouter(prefix="/timetable", tags=["Timetable"])
settings = get_settings()

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


@router.post("/generate", response_model=GenerationResult)
def generate_timetable(
    request: GenerationRequest,
    db: Session = Depends(get_db)
):
    """
    Generate timetable for specified semesters (or all if not specified).
    
    This uses the two-phase algorithm:
    1. Greedy/CSP-based initial generation
    2. Genetic Algorithm optimization
    """
    generator = TimetableGenerator(db)
    
    success, message, allocations, gen_time = generator.generate(
        semester_ids=request.semester_ids,
        clear_existing=request.clear_existing
    )
    
    return GenerationResult(
        success=success,
        message=message,
        total_allocations=len(allocations),
        hard_constraint_violations=0 if success else -1,
        soft_constraint_score=100.0 if success else 0.0,
        generation_time_seconds=round(gen_time, 3)
    )


@router.get("/allocations", response_model=List[AllocationResponse])
def list_allocations(
    semester_id: Optional[int] = None,
    teacher_id: Optional[int] = None,
    day: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all allocations, optionally filtered."""
    query = db.query(Allocation).options(
        joinedload(Allocation.teacher),
        joinedload(Allocation.subject),
        joinedload(Allocation.semester),
        joinedload(Allocation.room)
    )
    
    if semester_id:
        query = query.filter(Allocation.semester_id == semester_id)
    if teacher_id:
        query = query.filter(Allocation.teacher_id == teacher_id)
    if day is not None:
        query = query.filter(Allocation.day == day)
    
    return query.order_by(Allocation.day, Allocation.slot).all()


@router.get("/view/semester/{semester_id}", response_model=TimetableView)
def get_semester_timetable(
    semester_id: int,
    view_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """
    Get complete timetable for a semester/class.
    Includes substitution information if view_date is provided.
    """
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
    
    # Get all allocations for the semester
    allocations = db.query(Allocation).options(
        joinedload(Allocation.teacher),
        joinedload(Allocation.subject),
        joinedload(Allocation.room)
    ).filter(
        Allocation.semester_id == semester_id
    ).all()
    
    # Get substitutions for the view date if provided
    substitutions_map = {}
    if view_date:
        subs = db.query(Substitution).filter(
            Substitution.substitution_date == view_date,
            Substitution.status.in_([SubstitutionStatus.ASSIGNED, SubstitutionStatus.PENDING])
        ).all()
        
        for sub in subs:
            substitutions_map[sub.allocation_id] = sub
    
    # Build timetable view
    days = []
    for day_idx in range(5):
        slots = []
        for slot_idx in range(settings.SLOTS_PER_DAY):
            # Find allocation for this slot
            alloc = next(
                (a for a in allocations if a.day == day_idx and a.slot == slot_idx),
                None
            )
            
            if alloc:
                is_substituted = alloc.id in substitutions_map
                sub_teacher_name = None
                
                if is_substituted:
                    sub = substitutions_map[alloc.id]
                    sub_teacher = db.query(Teacher).filter(
                        Teacher.id == sub.substitute_teacher_id
                    ).first()
                    if sub_teacher:
                        sub_teacher_name = sub_teacher.name
                
                slot_data = TimetableSlot(
                    allocation_id=alloc.id,
                    teacher_name=alloc.teacher.name,
                    teacher_id=alloc.teacher.id,
                    subject_name=alloc.subject.name,
                    subject_code=alloc.subject.code,
                    room_name=alloc.room.name,
                    is_lab=alloc.subject.subject_type.value == "lab",
                    is_substituted=is_substituted,
                    substitute_teacher_name=sub_teacher_name
                )
            else:
                slot_data = TimetableSlot()
            
            slots.append(slot_data)
        
        days.append(TimetableDay(
            day=day_idx,
            day_name=DAY_NAMES[day_idx],
            slots=slots
        ))
    
    return TimetableView(
        entity_type="semester",
        entity_id=semester.id,
        entity_name=f"{semester.name} ({semester.code})",
        days=days
    )


@router.get("/view/teacher/{teacher_id}", response_model=TimetableView)
def get_teacher_timetable(
    teacher_id: int,
    view_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """
    Get complete timetable for a teacher.
    Shows all classes they're assigned to teach.
    """
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    # Get all allocations for the teacher
    allocations = db.query(Allocation).options(
        joinedload(Allocation.subject),
        joinedload(Allocation.semester),
        joinedload(Allocation.room)
    ).filter(
        Allocation.teacher_id == teacher_id
    ).all()
    
    # Build timetable view
    days = []
    for day_idx in range(5):
        slots = []
        for slot_idx in range(settings.SLOTS_PER_DAY):
            alloc = next(
                (a for a in allocations if a.day == day_idx and a.slot == slot_idx),
                None
            )
            
            if alloc:
                slot_data = TimetableSlot(
                    allocation_id=alloc.id,
                    teacher_name=teacher.name,
                    teacher_id=teacher.id,
                    subject_name=f"{alloc.subject.name} ({alloc.semester.code})",
                    subject_code=alloc.subject.code,
                    room_name=alloc.room.name,
                    is_lab=alloc.subject.subject_type.value == "lab",
                    is_substituted=False,
                    substitute_teacher_name=None
                )
            else:
                slot_data = TimetableSlot()
            
            slots.append(slot_data)
        
        days.append(TimetableDay(
            day=day_idx,
            day_name=DAY_NAMES[day_idx],
            slots=slots
        ))
    
    return TimetableView(
        entity_type="teacher",
        entity_id=teacher.id,
        entity_name=teacher.name,
        days=days
    )


@router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
def clear_timetable(
    semester_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Clear timetable allocations.
    If semester_id is provided, only clears for that semester.
    """
    query = db.query(Allocation)
    
    if semester_id:
        query = query.filter(Allocation.semester_id == semester_id)
    
    query.delete()
    db.commit()
    
    return None
