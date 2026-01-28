"""
Substitution API routes.
Handles teacher absences and substitution management.
"""
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.db.models import Teacher, Allocation, Substitution, TeacherAbsence, Subject
from app.schemas.schemas import (
    TeacherAbsenceCreate, TeacherAbsenceResponse,
    SubstitutionRequest, SubstitutionResponse, SubstitutionCandidate
)
from app.services.substitution import SubstitutionService

router = APIRouter(prefix="/substitution", tags=["Substitution"])


@router.post("/mark-absent", response_model=TeacherAbsenceResponse)
def mark_teacher_absent(
    absence_data: TeacherAbsenceCreate,
    db: Session = Depends(get_db)
):
    """
    Mark a teacher as absent for a specific date.
    This is the first step in the substitution workflow.
    """
    # Verify teacher exists
    teacher = db.query(Teacher).filter(Teacher.id == absence_data.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    service = SubstitutionService(db)
    absence = service.mark_teacher_absent(
        teacher_id=absence_data.teacher_id,
        absence_date=absence_data.absence_date,
        reason=absence_data.reason,
        is_full_day=absence_data.is_full_day,
        absent_slots=absence_data.absent_slots
    )
    
    return absence


@router.get("/absences", response_model=List[TeacherAbsenceResponse])
def list_absences(
    teacher_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Get list of teacher absences."""
    query = db.query(TeacherAbsence)
    
    if teacher_id:
        query = query.filter(TeacherAbsence.teacher_id == teacher_id)
    if from_date:
        query = query.filter(TeacherAbsence.absence_date >= from_date)
    if to_date:
        query = query.filter(TeacherAbsence.absence_date <= to_date)
    
    return query.order_by(TeacherAbsence.absence_date.desc()).all()


@router.get("/affected-allocations/{teacher_id}/{absence_date}")
def get_affected_allocations(
    teacher_id: int,
    absence_date: date,
    db: Session = Depends(get_db)
):
    """
    Get allocations affected by a teacher's absence on a specific date.
    """
    service = SubstitutionService(db)
    allocations = service.get_affected_allocations(teacher_id, absence_date)
    
    result = []
    for alloc in allocations:
        subject = db.query(Subject).filter(Subject.id == alloc.subject_id).first()
        result.append({
            "allocation_id": alloc.id,
            "day": alloc.day,
            "slot": alloc.slot,
            "subject_name": subject.name if subject else "Unknown",
            "semester_id": alloc.semester_id
        })
    
    return result


@router.get("/candidates/{allocation_id}/{substitution_date}", response_model=List[SubstitutionCandidate])
def get_substitute_candidates(
    allocation_id: int,
    substitution_date: date,
    db: Session = Depends(get_db)
):
    """
    Get ranked list of substitute candidates for an allocation.
    
    Returns candidates sorted by substitution score (highest first).
    The score considers:
    - Subject qualification match
    - Current workload (lower is better)
    - Teaching effectiveness for the subject
    - Experience score
    """
    allocation = db.query(Allocation).filter(Allocation.id == allocation_id).first()
    if not allocation:
        raise HTTPException(status_code=404, detail="Allocation not found")
    
    service = SubstitutionService(db)
    candidates = service.find_candidates(allocation, substitution_date)
    
    return candidates


@router.post("/assign", response_model=SubstitutionResponse)
def assign_substitute(
    request: SubstitutionRequest,
    substitute_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Assign a substitute teacher to an allocation.
    
    If substitute_teacher_id is not provided, automatically selects the best candidate.
    """
    service = SubstitutionService(db)
    
    substitution, message = service.assign_substitute(
        allocation_id=request.allocation_id,
        substitution_date=request.substitution_date,
        substitute_teacher_id=substitute_teacher_id,
        reason=request.reason
    )
    
    if not substitution:
        raise HTTPException(status_code=400, detail=message)
    
    # Get additional info for response
    allocation = db.query(Allocation).filter(Allocation.id == request.allocation_id).first()
    original_teacher = db.query(Teacher).filter(Teacher.id == substitution.original_teacher_id).first()
    substitute_teacher = db.query(Teacher).filter(Teacher.id == substitution.substitute_teacher_id).first()
    subject = db.query(Subject).filter(Subject.id == allocation.subject_id).first()
    
    return SubstitutionResponse(
        id=substitution.id,
        allocation_id=substitution.allocation_id,
        original_teacher_id=substitution.original_teacher_id,
        substitute_teacher_id=substitution.substitute_teacher_id,
        substitution_date=substitution.substitution_date,
        status=substitution.status,
        substitute_score=substitution.substitute_score,
        reason=substitution.reason,
        original_teacher_name=original_teacher.name if original_teacher else None,
        substitute_teacher_name=substitute_teacher.name if substitute_teacher else None,
        subject_name=subject.name if subject else None
    )


@router.post("/auto-substitute/{teacher_id}/{absence_date}")
def auto_substitute(
    teacher_id: int,
    absence_date: date,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Automatically create substitutions for all affected allocations of an absent teacher.
    
    This is the main automation endpoint that:
    1. Marks the teacher as absent
    2. Finds all affected allocations
    3. Assigns the best available substitute for each
    """
    # Verify teacher exists
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    service = SubstitutionService(db)
    results = service.auto_substitute_for_absence(teacher_id, absence_date, reason)
    
    response = []
    for sub, message in results:
        if sub:
            substitute_teacher = db.query(Teacher).filter(
                Teacher.id == sub.substitute_teacher_id
            ).first()
            allocation = db.query(Allocation).filter(
                Allocation.id == sub.allocation_id
            ).first()
            subject = db.query(Subject).filter(
                Subject.id == allocation.subject_id
            ).first() if allocation else None
            
            response.append({
                "substitution_id": sub.id,
                "allocation_id": sub.allocation_id,
                "slot": allocation.slot if allocation else None,
                "subject_name": subject.name if subject else None,
                "substitute_teacher_name": substitute_teacher.name if substitute_teacher else None,
                "score": sub.substitute_score,
                "message": message
            })
        else:
            response.append({
                "substitution_id": None,
                "message": message
            })
    
    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher.name,
        "absence_date": absence_date.isoformat(),
        "substitutions": response
    }


@router.get("/active", response_model=List[SubstitutionResponse])
def get_active_substitutions(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Get all active (pending or assigned) substitutions."""
    service = SubstitutionService(db)
    subs = service.get_active_substitutions(from_date, to_date)
    
    result = []
    for sub in subs:
        allocation = db.query(Allocation).filter(Allocation.id == sub.allocation_id).first()
        original_teacher = db.query(Teacher).filter(Teacher.id == sub.original_teacher_id).first()
        substitute_teacher = db.query(Teacher).filter(Teacher.id == sub.substitute_teacher_id).first()
        subject = db.query(Subject).filter(Subject.id == allocation.subject_id).first() if allocation else None
        
        result.append(SubstitutionResponse(
            id=sub.id,
            allocation_id=sub.allocation_id,
            original_teacher_id=sub.original_teacher_id,
            substitute_teacher_id=sub.substitute_teacher_id,
            substitution_date=sub.substitution_date,
            status=sub.status,
            substitute_score=sub.substitute_score,
            reason=sub.reason,
            original_teacher_name=original_teacher.name if original_teacher else None,
            substitute_teacher_name=substitute_teacher.name if substitute_teacher else None,
            subject_name=subject.name if subject else None
        ))
    
    return result


@router.delete("/{substitution_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_substitution(
    substitution_id: int,
    db: Session = Depends(get_db)
):
    """Cancel a substitution."""
    service = SubstitutionService(db)
    success = service.cancel_substitution(substitution_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Substitution not found")
    
    return None
