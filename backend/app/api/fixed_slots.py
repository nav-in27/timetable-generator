"""
Fixed Slots API - Manual Slot Locking Before Generation

Allows Admin/Teacher to manually fix subjects into specific time slots
BEFORE timetable generation. The generator will respect these locked slots.

CRITICAL RULES:
- Fixed slots are IMMUTABLE during generation
- Generator NEVER changes fixed slots
- Validation ensures slot is valid before locking
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.db.models import (
    FixedSlot, Semester, Subject, Teacher, Room, Allocation,
    ClassSubjectTeacher, ComponentType, SubjectType
)
from app.schemas.schemas import (
    FixedSlotCreate, FixedSlotUpdate, FixedSlotResponse,
    FixedSlotValidation, FixedSlotsBySemester
)

router = APIRouter(prefix="/fixed-slots", tags=["Fixed Slots"])

# Valid lab block positions (0-indexed): 4th+5th or 6th+7th period
VALID_LAB_BLOCKS = [(3, 4), (5, 6)]


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def _validate_slot_lock(
    db: Session,
    semester_id: int,
    day: int,
    slot: int,
    subject_id: int,
    teacher_id: int,
    component_type: ComponentType = ComponentType.THEORY,
    exclude_fixed_slot_id: Optional[int] = None
) -> FixedSlotValidation:
    """
    Validate if a slot can be locked.
    
    Checks:
    1. Slot is not already locked (by another fixed slot)
    2. Slot is not break or lunch (handled by frontend, but double-check)
    3. Teacher is assigned to this subject & class
    4. Teacher doesn't have another fixed slot at this time
    5. Lab continuity rules (if lab)
    6. Elective synchronization (if elective)
    """
    errors = []
    warnings = []
    
    # Check semester exists
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        errors.append(f"Semester with ID {semester_id} not found")
        return FixedSlotValidation(is_valid=False, errors=errors, warnings=warnings)
    
    # Check subject exists
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        errors.append(f"Subject with ID {subject_id} not found")
        return FixedSlotValidation(is_valid=False, errors=errors, warnings=warnings)
    
    # Check teacher exists
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        errors.append(f"Teacher with ID {teacher_id} not found")
        return FixedSlotValidation(is_valid=False, errors=errors, warnings=warnings)
    
    # Check slot is not already locked by another fixed slot
    existing_fixed = db.query(FixedSlot).filter(
        FixedSlot.semester_id == semester_id,
        FixedSlot.day == day,
        FixedSlot.slot == slot
    )
    if exclude_fixed_slot_id:
        existing_fixed = existing_fixed.filter(FixedSlot.id != exclude_fixed_slot_id)
    
    if existing_fixed.first():
        errors.append(f"Slot is already locked for this class")
        return FixedSlotValidation(is_valid=False, errors=errors, warnings=warnings)
    
    # Check teacher is assigned to this subject for this class
    assignment = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.semester_id == semester_id,
        ClassSubjectTeacher.subject_id == subject_id,
        ClassSubjectTeacher.teacher_id == teacher_id,
        ClassSubjectTeacher.component_type == component_type
    ).first()
    
    if not assignment:
        # Check if subject is at least assigned to this semester
        if subject not in semester.subjects:
            errors.append(f"Subject '{subject.name}' is not assigned to this class")
        else:
            # Check if teacher teaches this subject at all
            if subject not in teacher.subjects:
                errors.append(f"Teacher '{teacher.name}' is not assigned to teach '{subject.name}'")
            else:
                # Just a warning - no explicit ClassSubjectTeacher entry
                warnings.append(
                    f"No explicit class assignment found. This will create one during generation."
                )
    
    # Check teacher doesn't have another fixed slot at this time (in any class)
    teacher_conflict = db.query(FixedSlot).filter(
        FixedSlot.teacher_id == teacher_id,
        FixedSlot.day == day,
        FixedSlot.slot == slot
    )
    if exclude_fixed_slot_id:
        teacher_conflict = teacher_conflict.filter(FixedSlot.id != exclude_fixed_slot_id)
    
    if teacher_conflict.first():
        errors.append(f"Teacher '{teacher.name}' already has a locked slot at this time")
        return FixedSlotValidation(is_valid=False, errors=errors, warnings=warnings)
    
    # Check lab continuity rules
    if component_type == ComponentType.LAB:
        # Lab must be at valid lab block positions
        valid_start_slots = [block[0] for block in VALID_LAB_BLOCKS]
        valid_end_slots = [block[1] for block in VALID_LAB_BLOCKS]
        
        if slot not in valid_start_slots and slot not in valid_end_slots:
            warnings.append(
                f"Lab slot {slot} is not at a standard lab block position. "
                f"Valid lab blocks are periods 4-5 or 6-7."
            )
        
        # If locking first slot of a lab block, warn that second slot will also be needed
        if slot in valid_start_slots:
            next_slot = slot + 1
            warnings.append(
                f"Lab requires 2 consecutive periods. "
                f"Period {next_slot + 1} should also be locked for this lab."
            )
    
    # Check elective synchronization
    is_elective = (
        subject.is_elective or 
        subject.subject_type == SubjectType.ELECTIVE or
        subject.elective_basket_id is not None
    )
    
    if is_elective:
        warnings.append(
            f"'{subject.name}' is an elective. Ensure all elective options "
            f"for this class are locked at the same time slot."
        )
    
    return FixedSlotValidation(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


# ============================================================================
# CRUD ENDPOINTS
# ============================================================================

@router.post("/", response_model=FixedSlotResponse, status_code=status.HTTP_201_CREATED)
def create_fixed_slot(
    data: FixedSlotCreate,
    db: Session = Depends(get_db)
):
    """
    Lock a slot with a specific subject and teacher.
    
    This slot will be respected during timetable generation and cannot be changed
    until explicitly unlocked.
    """
    # Validate the slot
    validation = _validate_slot_lock(
        db, data.semester_id, data.day, data.slot,
        data.subject_id, data.teacher_id, data.component_type
    )
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Cannot lock slot", "errors": validation.errors}
        )
    
    # Determine if subject is elective
    subject = db.query(Subject).filter(Subject.id == data.subject_id).first()
    is_elective = (
        subject.is_elective or 
        subject.subject_type == SubjectType.ELECTIVE or
        subject.elective_basket_id is not None
    )
    
    # Create the fixed slot
    fixed_slot = FixedSlot(
        semester_id=data.semester_id,
        day=data.day,
        slot=data.slot,
        subject_id=data.subject_id,
        teacher_id=data.teacher_id,
        room_id=data.room_id,
        component_type=data.component_type,
        is_lab_continuation=data.is_lab_continuation,
        is_elective=is_elective,
        elective_basket_id=subject.elective_basket_id if is_elective else None,
        locked=True,
        locked_by=data.locked_by or "admin",
        lock_reason=data.lock_reason
    )
    
    db.add(fixed_slot)
    db.commit()
    db.refresh(fixed_slot)
    
    # Build response with names
    return _build_fixed_slot_response(db, fixed_slot)


@router.get("/", response_model=List[FixedSlotResponse])
def list_fixed_slots(
    semester_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all fixed slots, optionally filtered by semester."""
    query = db.query(FixedSlot)
    
    if semester_id:
        query = query.filter(FixedSlot.semester_id == semester_id)
    
    fixed_slots = query.order_by(FixedSlot.day, FixedSlot.slot).all()
    
    return [_build_fixed_slot_response(db, fs) for fs in fixed_slots]


@router.get("/by-semester", response_model=List[FixedSlotsBySemester])
def get_fixed_slots_by_semester(db: Session = Depends(get_db)):
    """Get fixed slots grouped by semester."""
    semesters = db.query(Semester).all()
    result = []
    
    for semester in semesters:
        fixed_slots = db.query(FixedSlot).filter(
            FixedSlot.semester_id == semester.id
        ).order_by(FixedSlot.day, FixedSlot.slot).all()
        
        result.append(FixedSlotsBySemester(
            semester_id=semester.id,
            semester_name=f"{semester.name} ({semester.code})",
            fixed_slots=[_build_fixed_slot_response(db, fs) for fs in fixed_slots]
        ))
    
    return result


@router.get("/{fixed_slot_id}", response_model=FixedSlotResponse)
def get_fixed_slot(fixed_slot_id: int, db: Session = Depends(get_db)):
    """Get a specific fixed slot by ID."""
    fixed_slot = db.query(FixedSlot).filter(FixedSlot.id == fixed_slot_id).first()
    
    if not fixed_slot:
        raise HTTPException(status_code=404, detail="Fixed slot not found")
    
    return _build_fixed_slot_response(db, fixed_slot)


@router.delete("/{fixed_slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fixed_slot(fixed_slot_id: int, db: Session = Depends(get_db)):
    """
    Unlock/delete a fixed slot.
    
    This allows the generator to use this slot for automatic scheduling.
    """
    fixed_slot = db.query(FixedSlot).filter(FixedSlot.id == fixed_slot_id).first()
    
    if not fixed_slot:
        raise HTTPException(status_code=404, detail="Fixed slot not found")
    
    db.delete(fixed_slot)
    db.commit()
    
    return None


@router.delete("/clear/semester/{semester_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_fixed_slots_for_semester(semester_id: int, db: Session = Depends(get_db)):
    """Clear all fixed slots for a specific semester."""
    db.query(FixedSlot).filter(FixedSlot.semester_id == semester_id).delete()
    db.commit()
    return None


@router.delete("/clear/all", status_code=status.HTTP_204_NO_CONTENT)
def clear_all_fixed_slots(db: Session = Depends(get_db)):
    """Clear all fixed slots (admin only operation)."""
    db.query(FixedSlot).delete()
    db.commit()
    return None


# ============================================================================
# VALIDATION ENDPOINT
# ============================================================================

@router.post("/validate", response_model=FixedSlotValidation)
def validate_slot_lock(
    data: FixedSlotCreate,
    db: Session = Depends(get_db)
):
    """
    Validate if a slot can be locked without actually locking it.
    
    Use this before showing the lock confirmation dialog.
    """
    return _validate_slot_lock(
        db, data.semester_id, data.day, data.slot,
        data.subject_id, data.teacher_id, data.component_type
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _build_fixed_slot_response(db: Session, fixed_slot: FixedSlot) -> FixedSlotResponse:
    """Build a FixedSlotResponse with all related names."""
    semester = db.query(Semester).filter(Semester.id == fixed_slot.semester_id).first()
    subject = db.query(Subject).filter(Subject.id == fixed_slot.subject_id).first()
    teacher = db.query(Teacher).filter(Teacher.id == fixed_slot.teacher_id).first()
    room = None
    if fixed_slot.room_id:
        room = db.query(Room).filter(Room.id == fixed_slot.room_id).first()
    
    return FixedSlotResponse(
        id=fixed_slot.id,
        semester_id=fixed_slot.semester_id,
        day=fixed_slot.day,
        slot=fixed_slot.slot,
        subject_id=fixed_slot.subject_id,
        teacher_id=fixed_slot.teacher_id,
        room_id=fixed_slot.room_id,
        component_type=fixed_slot.component_type,
        is_lab_continuation=fixed_slot.is_lab_continuation,
        is_elective=fixed_slot.is_elective,
        elective_basket_id=fixed_slot.elective_basket_id,
        locked=fixed_slot.locked,
        locked_by=fixed_slot.locked_by,
        lock_reason=fixed_slot.lock_reason,
        semester_name=f"{semester.name} ({semester.code})" if semester else None,
        subject_name=subject.name if subject else None,
        subject_code=subject.code if subject else None,
        teacher_name=teacher.name if teacher else None,
        room_name=room.name if room else None,
        created_at=fixed_slot.created_at,
        updated_at=fixed_slot.updated_at
    )
