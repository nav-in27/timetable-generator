"""
Timetable API routes.
Handles generation and viewing of timetables.
"""
from typing import List, Optional
from datetime import date
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.db.models import Allocation, Semester, Teacher, Subject, Room, Substitution, SubstitutionStatus
from app.schemas.schemas import (
    AllocationResponse, TimetableView, TimetableDay, TimetableSlot,
    GenerationRequest, GenerationResult
)
from app.services.generator import TimetableGenerator
from app.services.pdf_service import TimetablePDFService
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
                    component_type=getattr(alloc, 'component_type', None).value if hasattr(alloc, 'component_type') and alloc.component_type else "theory",
                    is_lab=getattr(alloc, 'component_type', None) and alloc.component_type.value == "lab",
                    is_elective=getattr(alloc, 'is_elective', False),
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
                    component_type=getattr(alloc, 'component_type', None).value if hasattr(alloc, 'component_type') and alloc.component_type else "theory",
                    is_lab=getattr(alloc, 'component_type', None) and alloc.component_type.value == "lab",
                    is_elective=getattr(alloc, 'is_elective', False),
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


# ============================================================================
# PDF Export Endpoints (READ-ONLY)
# ============================================================================

@router.get("/export/pdf")
def export_timetable_pdf(
    db: Session = Depends(get_db)
):
    """
    Export all timetables as PDF.
    READ-ONLY operation - uses existing allocation data only.
    Does not modify or regenerate any timetable data.
    """
    try:
        pdf_service = TimetablePDFService(db)
        
        # Check if timetables exist
        if pdf_service.get_timetable_count() == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No timetable generated. Please generate a timetable first."
            )
        
        # Generate PDF
        pdf_bytes = pdf_service.generate_all_timetables_pdf()
        
        # Return as downloadable file - Institutional naming format
        filename = f"Class_Timetable_AIDS_{date.today().year}_All.pdf"
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate PDF. Please try again."
        )


@router.get("/export/pdf/preview")
def preview_timetable_pdf(
    db: Session = Depends(get_db)
):
    """
    Get PDF for preview (inline display).
    READ-ONLY operation - uses existing allocation data only.
    """
    try:
        pdf_service = TimetablePDFService(db)
        
        # Check if timetables exist
        if pdf_service.get_timetable_count() == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No timetable generated. Please generate a timetable first."
            )
        
        # Generate PDF
        pdf_bytes = pdf_service.generate_all_timetables_pdf()
        
        # Return for inline display (not download)
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline; filename=timetable_preview.pdf"
            }
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate PDF. Please try again."
        )


@router.get("/export/status")
def get_export_status(
    db: Session = Depends(get_db)
):
    """
    Check if timetable export is available.
    Returns status indicating if PDF export is possible.
    """
    pdf_service = TimetablePDFService(db)
    count = pdf_service.get_timetable_count()
    
    return {
        "has_timetable": count > 0,
        "timetable_count": count,
        "message": "Ready for export" if count > 0 else "Please generate a timetable first"
    }
