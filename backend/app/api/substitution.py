"""
Substitution API routes.
Handles teacher absences and substitution management.

OPTIMIZATIONS (v2):
- Batch-load related entities instead of N+1 per-substitution queries
- Eager-load allocations, teachers, subjects in list endpoints
- Null-safe access throughout
- Proper error isolation
"""
from typing import List, Optional, Dict
from datetime import date
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db
from app.db.models import Teacher, Allocation, Substitution, TeacherAbsence, Subject
from app.schemas.schemas import (
    TeacherAbsenceCreate, TeacherAbsenceResponse,
    SubstitutionRequest, SubstitutionResponse, SubstitutionCandidate
)
from app.services.substitution import SubstitutionService

router = APIRouter(prefix="/substitution", tags=["Substitution"])
logger = logging.getLogger("app.substitution")


# ============================================================================
# HELPERS
# ============================================================================

def _build_substitution_response(sub: Substitution, extra: dict = None) -> SubstitutionResponse:
    """Build a SubstitutionResponse with null-safe relationship access."""
    # Access eagerly-loaded relationships (no extra queries)
    original_name = None
    substitute_name = None
    subject_name = None

    if extra:
        original_name = extra.get("original_teacher_name")
        substitute_name = extra.get("substitute_teacher_name")
        subject_name = extra.get("subject_name")

    if original_name is None and hasattr(sub, 'original_teacher') and sub.original_teacher:
        original_name = sub.original_teacher.name
    if substitute_name is None and hasattr(sub, 'substitute_teacher') and sub.substitute_teacher:
        substitute_name = sub.substitute_teacher.name
    if subject_name is None and hasattr(sub, 'allocation') and sub.allocation:
        if sub.allocation.subject:
            subject_name = sub.allocation.subject.name

    return SubstitutionResponse(
        id=sub.id,
        allocation_id=sub.allocation_id,
        original_teacher_id=sub.original_teacher_id,
        substitute_teacher_id=sub.substitute_teacher_id,
        substitution_date=sub.substitution_date,
        status=sub.status,
        substitute_score=sub.substitute_score,
        reason=sub.reason,
        original_teacher_name=original_name,
        substitute_teacher_name=substitute_name,
        subject_name=subject_name,
    )


# ============================================================================
# ABSENCE ENDPOINTS
# ============================================================================

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


# ============================================================================
# AFFECTED ALLOCATIONS
# ============================================================================

@router.get("/affected-allocations/{teacher_id}/{absence_date}")
def get_affected_allocations(
    teacher_id: int,
    absence_date: date,
    db: Session = Depends(get_db)
):
    """
    Get allocations affected by a teacher's absence on a specific date.
    OPTIMIZED: uses eager-loaded subject relationship.
    """
    service = SubstitutionService(db)
    allocations = service.get_affected_allocations(teacher_id, absence_date)
    
    # Batch-load all subject IDs at once instead of per-allocation
    subject_ids = list({a.subject_id for a in allocations if a.subject_id})
    subjects_map: Dict[int, Subject] = {}
    if subject_ids:
        subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
        subjects_map = {s.id: s for s in subjects}

    result = []
    for alloc in allocations:
        subject = subjects_map.get(alloc.subject_id)
        result.append({
            "allocation_id": alloc.id,
            "day": alloc.day,
            "slot": alloc.slot,
            "subject_name": subject.name if subject else "Unknown",
            "semester_id": alloc.semester_id
        })
    
    return result


# ============================================================================
# CANDIDATES
# ============================================================================

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


# ============================================================================
# ASSIGN SUBSTITUTE
# ============================================================================

@router.post("/assign", response_model=SubstitutionResponse)
def assign_substitute(
    request: SubstitutionRequest,
    substitute_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Assign a substitute teacher to an allocation.
    If substitute_teacher_id is not provided, automatically selects the best candidate.
    
    OPTIMIZED: single batch query for all related entities.
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
    
    # Batch-load all needed entities in minimal queries
    teacher_ids = list({substitution.original_teacher_id, substitution.substitute_teacher_id})
    teachers_map = {
        t.id: t for t in db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()
    }

    allocation = db.query(Allocation).options(
        joinedload(Allocation.subject)
    ).filter(Allocation.id == request.allocation_id).first()

    original_teacher = teachers_map.get(substitution.original_teacher_id)
    substitute_teacher = teachers_map.get(substitution.substitute_teacher_id)

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
        subject_name=allocation.subject.name if allocation and allocation.subject else None
    )


# ============================================================================
# AUTO-SUBSTITUTE
# ============================================================================

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
    
    # Batch-load all substitute teachers and allocations at once
    sub_teacher_ids = set()
    allocation_ids = set()
    for sub, message in results:
        if sub:
            sub_teacher_ids.add(sub.substitute_teacher_id)
            allocation_ids.add(sub.allocation_id)

    teachers_map = {}
    if sub_teacher_ids:
        teachers_map = {
            t.id: t for t in db.query(Teacher).filter(Teacher.id.in_(sub_teacher_ids)).all()
        }

    allocations_map = {}
    if allocation_ids:
        allocs = db.query(Allocation).options(
            joinedload(Allocation.subject)
        ).filter(Allocation.id.in_(allocation_ids)).all()
        allocations_map = {a.id: a for a in allocs}

    response = []
    for sub, message in results:
        if sub:
            substitute_teacher = teachers_map.get(sub.substitute_teacher_id)
            allocation = allocations_map.get(sub.allocation_id)
            subject = allocation.subject if allocation else None
            
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


# ============================================================================
# ACTIVE SUBSTITUTIONS (CRITICAL N+1 FIX)
# ============================================================================

@router.get("/active", response_model=List[SubstitutionResponse])
def get_active_substitutions(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """
    Get all active (pending or assigned) substitutions.
    
    OPTIMIZED: Single query with eager loading replaces N+1 pattern
    (was: per-substitution queries for allocation, original_teacher, substitute_teacher, subject).
    """
    service = SubstitutionService(db)
    subs = service.get_active_substitutions(from_date, to_date)

    if not subs:
        return []

    # Batch-load all needed entities in TWO queries max (teachers + allocations)
    teacher_ids = set()
    allocation_ids = set()
    for sub in subs:
        teacher_ids.add(sub.original_teacher_id)
        teacher_ids.add(sub.substitute_teacher_id)
        allocation_ids.add(sub.allocation_id)

    teachers_map = {
        t.id: t for t in db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()
    } if teacher_ids else {}

    allocations_map = {}
    if allocation_ids:
        allocs = db.query(Allocation).options(
            joinedload(Allocation.subject)
        ).filter(Allocation.id.in_(allocation_ids)).all()
        allocations_map = {a.id: a for a in allocs}

    result = []
    for sub in subs:
        allocation = allocations_map.get(sub.allocation_id)
        original_teacher = teachers_map.get(sub.original_teacher_id)
        substitute_teacher = teachers_map.get(sub.substitute_teacher_id)
        subject = allocation.subject if allocation else None

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


# ============================================================================
# CANCEL
# ============================================================================

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
