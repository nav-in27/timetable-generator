"""
Timetable API routes.
Handles generation and viewing of timetables.
"""
from typing import List, Optional, Dict, Any
from datetime import date
from io import BytesIO
import threading
import uuid
import time as time_module
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db, SessionLocal
from app.db.models import Allocation, Semester, Teacher, Subject, Room, Substitution, SubstitutionStatus
from app.schemas.schemas import (
    AllocationResponse, TimetableView, TimetableDay, TimetableSlot,
    GenerationRequest, GenerationResult, BatchAllocationData
)
from app.services.generator import TimetableGenerator
from app.services.pdf_service import TimetablePDFService
from app.core.config import get_settings

router = APIRouter(prefix="/timetable", tags=["Timetable"])
settings = get_settings()

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _is_effective_elective(allocation: Allocation) -> bool:
    """
    Determine elective status robustly even when legacy rows missed is_elective.
    """
    subject = getattr(allocation, "subject", None)
    subject_type = str(getattr(subject, "subject_type", "")).lower() if subject else ""
    return bool(
        getattr(allocation, "is_elective", False)
        or getattr(allocation, "elective_basket_id", None) is not None
        or (subject is not None and getattr(subject, "is_elective", False))
        or (subject is not None and getattr(subject, "elective_basket_id", None) is not None)
        or subject_type.endswith("elective")
    )

# In-memory generation task store (for async generation)
_generation_tasks: Dict[str, Dict[str, Any]] = {}


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
    try:
        generator = TimetableGenerator(db)

        success, message, allocations, gen_time = generator.generate(
            semester_ids=request.semester_ids,
            dept_id=request.dept_id,
            clear_existing=request.clear_existing,
            semester_type=request.semester_type
        )

        return GenerationResult(
            success=success,
            message=message,
            total_allocations=len(allocations),
            hard_constraint_violations=0 if success else -1,
            soft_constraint_score=100.0 if success else 0.0,
            generation_time_seconds=round(gen_time, 3)
        )
    except Exception as e:
        print(f"[ERROR] Timetable generation failed: {e}")
        import traceback
        traceback.print_exc()
        return GenerationResult(
            success=False,
            message=f"Generation error: {str(e)}",
            total_allocations=0,
            hard_constraint_violations=-1,
            soft_constraint_score=0.0,
            generation_time_seconds=0.0
        )


@router.get("/allocations", response_model=List[AllocationResponse])
def list_allocations(
    semester_id: Optional[int] = None,
    teacher_id: Optional[int] = None,
    day: Optional[int] = None,
    dept_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all allocations, optionally filtered. Supports dept_id for department isolation."""
    try:
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
        if dept_id:
            # Filter allocations via semester's department
            dept_sem_ids = [
                sid for (sid,) in
                db.query(Semester.id).filter(Semester.dept_id == dept_id).all()
            ]
            if dept_sem_ids:
                query = query.filter(Allocation.semester_id.in_(dept_sem_ids))
            else:
                return []

        return query.order_by(Allocation.day, Allocation.slot).all()
    except Exception as e:
        print(f"[ERROR] list_allocations failed: {e}")
        return []


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
        joinedload(Allocation.room),
        joinedload(Allocation.batch)
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
            # Find ALL allocations for this slot
            slot_allocs = [a for a in allocations if a.day == day_idx and a.slot == slot_idx]

            if slot_allocs:
                # Use the first allocation as the "primary" one for general slot info
                primary_alloc = slot_allocs[0]
                is_pure_elective_slot = all(_is_effective_elective(a) for a in slot_allocs)

                is_substituted = primary_alloc.id in substitutions_map
                sub_teacher_name = None

                if is_substituted:
                    sub = substitutions_map[primary_alloc.id]
                    sub_teacher = db.query(Teacher).filter(
                        Teacher.id == sub.substitute_teacher_id
                    ).first()
                    if sub_teacher:
                        sub_teacher_name = sub_teacher.name

                # Collect batch details if multiple or if batch_id exists
                batch_allocations = []
                for alloc in slot_allocs:
                    if alloc.batch_id or len(slot_allocs) > 1:
                        # Find the batch name directly or through db, fallback to batch_id or empty
                        if getattr(alloc, 'batch', None):
                            batch_name_str = alloc.batch.name
                        elif getattr(alloc, 'batch_id', None):
                            batch_name_str = f"B{alloc.batch_id}"
                        else:
                            batch_name_str = "Elective" if is_pure_elective_slot else "Batch"
                        batch_allocations.append(
                            {
                                "batch_id": alloc.batch_id,
                                "batch_name": batch_name_str,
                                "teacher_name": alloc.teacher.name,
                                "room_name": alloc.room.name if alloc.room else None,
                                "subject_name": alloc.subject.name,
                                "subject_code": alloc.subject.code
                            }
                        )

                # Build combined subject name for parallel multi-subject labs
                unique_subjects = list({a.subject_id: a for a in slot_allocs}.values())
                if is_pure_elective_slot:
                    basket_name = None
                    try:
                        basket = unique_subjects[0].subject.elective_basket if unique_subjects and unique_subjects[0].subject else None
                        if basket: basket_name = basket.name
                    except:
                        pass
                    
                    if not basket_name:
                        # Try SCB fallback if elective basket not found
                        try:
                            from app.db.models import StructuredCompositeBasketSubject
                            scb_link = db.query(StructuredCompositeBasketSubject).filter_by(subject_id=unique_subjects[0].subject_id).first()
                            if scb_link and scb_link.basket:
                                basket_name = scb_link.basket.name
                        except:
                            pass

                    if basket_name:
                        combined_name = basket_name
                        combined_code = basket_name
                    else:
                        # Check if multiple subjects exist, it might be SCB or something else
                        if len(unique_subjects) > 1:
                           combined_name = " / ".join(a.subject.name for a in unique_subjects) + " (Basket)"
                           combined_code = " / ".join(a.subject.code for a in unique_subjects)
                        else:
                           combined_name = "Elective"
                           combined_code = "ELECTIVE"
                elif len(unique_subjects) > 1:
                    # Check if this is an SCB scheduled class
                    scb_name = None
                    try:
                        from app.db.models import StructuredCompositeBasketSubject
                        scb_link = db.query(StructuredCompositeBasketSubject).filter_by(subject_id=unique_subjects[0].subject_id).first()
                        if scb_link and scb_link.basket:
                            scb_name = scb_link.basket.name
                    except:
                        pass
                        
                    if scb_name:
                        combined_name = scb_name
                        combined_code = scb_name
                    elif not any(_is_effective_elective(a) for a in slot_allocs):
                        # Parallel Lab format
                        combined_name = " / ".join(f"{a.subject.code}:{a.batch.name if a.batch else 'B'} (PL)" for a in unique_subjects)
                        combined_code = " / ".join(f"{a.subject.code} (PL)" for a in unique_subjects)
                    else:
                        combined_name = " / ".join(a.subject.name for a in unique_subjects) + " (Batch Split)"
                        combined_code = " / ".join(a.subject.code for a in unique_subjects)
                else:
                    combined_name = primary_alloc.subject.name
                    combined_code = primary_alloc.subject.code

                slot_data = TimetableSlot(
                    allocation_id=primary_alloc.id,
                    teacher_name=primary_alloc.teacher.name,
                    teacher_id=primary_alloc.teacher.id,
                    subject_name=combined_name,
                    subject_code=combined_code,
                    room_name=primary_alloc.room.name if primary_alloc.room else None,
                    batch_name=primary_alloc.batch.name if primary_alloc.batch else None,
                    batch_allocations=batch_allocations,
                    component_type=getattr(primary_alloc, 'component_type', None).value if hasattr(primary_alloc, 'component_type') and primary_alloc.component_type else "theory",
                    academic_component=getattr(primary_alloc, 'academic_component', None) or (primary_alloc.component_type.value if primary_alloc.component_type else None),
                    is_lab=(getattr(primary_alloc, 'academic_component', None) or (primary_alloc.component_type.value if primary_alloc.component_type else "")) == "lab",
                    is_elective=_is_effective_elective(primary_alloc),
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

    # Determine template type from the semester's actual semester_number
    # Odd semester numbers (1, 3, 5, 7) -> ODD template
    # Even semester numbers (2, 4, 6, 8) -> EVEN template
    preferred_type = "ODD" if (semester.semester_number % 2) != 0 else "EVEN"
    
    from app.db.models import SemesterTemplate
    import json
    template = db.query(SemesterTemplate).filter(SemesterTemplate.semester_type == preferred_type).first()
    
    break_slots = []
    lunch_slot = 3
    if template:
        try:
            break_slots = json.loads(template.break_slots)
        except:
            break_slots = []
        lunch_slot = template.lunch_slot

    return TimetableView(
        entity_type="semester",
        entity_id=semester.id,
        entity_name=f"{semester.name} ({semester.code})",
        days=days,
        break_slots=break_slots,
        lunch_slot=lunch_slot
    )


@router.get("/view/teacher/{teacher_id}", response_model=TimetableView)
def get_teacher_timetable(
    teacher_id: int,
    view_date: Optional[date] = None,
    dept_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get complete timetable for a teacher.
    Shows all classes they're assigned to teach.
    Optionally filtered by department.
    """
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Get all allocations for the teacher
    query = db.query(Allocation).options(
        joinedload(Allocation.subject),
        joinedload(Allocation.semester),
        joinedload(Allocation.room)
    ).filter(
        Allocation.teacher_id == teacher_id
    )

    # Department isolation: only show allocations for semesters in this department
    if dept_id:
        dept_sem_ids = [
            sid for (sid,) in
            db.query(Semester.id).filter(Semester.dept_id == dept_id).all()
        ]
        if dept_sem_ids:
            query = query.filter(Allocation.semester_id.in_(dept_sem_ids))
        else:
            query = query.filter(Allocation.id < 0)  # No results

    allocations = query.all()

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
                effective_is_elective = _is_effective_elective(alloc)
                slot_data = TimetableSlot(
                    allocation_id=alloc.id,
                    teacher_name=teacher.name,
                    teacher_id=teacher.id,
                    subject_name=f"{alloc.subject.name} ({alloc.semester.code})",
                    subject_code=alloc.subject.code,
                    room_name=alloc.room.name,
                    component_type=getattr(alloc, 'component_type', None).value if hasattr(alloc, 'component_type') and alloc.component_type else "theory",
                    academic_component=getattr(alloc, 'academic_component', None) or (alloc.component_type.value if alloc.component_type else None),
                    is_lab=(getattr(alloc, 'academic_component', None) or (alloc.component_type.value if alloc.component_type else "")) == "lab",
                    is_elective=effective_is_elective,
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

    # For teacher timetable, determine template from allocations' semesters
    # Use the most common semester type among the teacher's allocations
    from app.db.models import SemesterTemplate
    import json
    
    # Determine preferred type from the semesters this teacher teaches
    odd_count = 0
    even_count = 0
    for alloc in allocations:
        if hasattr(alloc, 'semester') and alloc.semester:
            if (alloc.semester.semester_number % 2) != 0:
                odd_count += 1
            else:
                even_count += 1
    preferred_type = "ODD" if odd_count >= even_count else "EVEN"
    
    template = db.query(SemesterTemplate).filter(SemesterTemplate.semester_type == preferred_type).first()
    
    break_slots = []
    lunch_slot = 3
    if template:
        try:
            break_slots = json.loads(template.break_slots)
        except:
            break_slots = []
        lunch_slot = template.lunch_slot

    return TimetableView(
        entity_type="teacher",
        entity_id=teacher.id,
        entity_name=teacher.name,
        days=days,
        break_slots=break_slots,
        lunch_slot=lunch_slot
    )


@router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
def clear_timetable(
    semester_id: Optional[int] = None,
    dept_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Clear timetable allocations.
    If semester_id is provided, only clears for that semester.
    If dept_id is provided, only clears for that department's semesters.
    NEVER clears across departments inadvertently.
    """
    try:
        query = db.query(Allocation)

        if semester_id:
            query = query.filter(Allocation.semester_id == semester_id)
        elif dept_id:
            # Only clear allocations for semesters in this department
            dept_sem_ids = [
                sid for (sid,) in
                db.query(Semester.id).filter(Semester.dept_id == dept_id).all()
            ]
            if dept_sem_ids:
                query = query.filter(Allocation.semester_id.in_(dept_sem_ids))
            else:
                return None  # Nothing to clear
        # If neither semester_id nor dept_id is provided, clear ALL (admin operation)

        query.delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[ERROR] clear_timetable failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear timetable: {str(e)}")

    return None


# ============================================================================
# PDF Export Endpoints (READ-ONLY)
# ============================================================================

@router.get("/export/pdf")
def export_timetable_pdf(
    dept_id: Optional[int] = None,
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
        filename = f"Class_Timetable_{date.today().year}_All.pdf"
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
        print(f"[ERROR] PDF export failed: {e}")
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
        print(f"[ERROR] PDF preview failed: {e}")
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
    try:
        pdf_service = TimetablePDFService(db)
        count = pdf_service.get_timetable_count()

        return {
            "has_timetable": count > 0,
            "timetable_count": count,
            "message": "Ready for export" if count > 0 else "Please generate a timetable first"
        }
    except Exception as e:
        print(f"[ERROR] export status check failed: {e}")
        return {
            "has_timetable": False,
            "timetable_count": 0,
            "message": "Error checking export status"
        }


# ============================================================================
# ASYNC GENERATION (Background Thread)
# ============================================================================

def _run_generation_task(task_id: str, request_data: dict):
    """Background thread function for async generation."""
    db = SessionLocal()
    try:
        _generation_tasks[task_id]["status"] = "running"
        _generation_tasks[task_id]["started_at"] = time_module.time()
        
        generator = TimetableGenerator(db)
        success, message, allocations, gen_time = generator.generate(
            semester_ids=request_data.get("semester_ids"),
            dept_id=request_data.get("dept_id"),
            clear_existing=request_data.get("clear_existing", True),
            semester_type=request_data.get("semester_type", "EVEN")
        )
        
        _generation_tasks[task_id].update({
            "status": "completed",
            "result": {
                "success": success,
                "message": message,
                "total_allocations": len(allocations),
                "hard_constraint_violations": 0 if success else -1,
                "soft_constraint_score": 100.0 if success else 0.0,
                "generation_time_seconds": round(gen_time, 3)
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        _generation_tasks[task_id].update({
            "status": "failed",
            "result": {
                "success": False,
                "message": f"Generation error: {str(e)}",
                "total_allocations": 0,
                "hard_constraint_violations": -1,
                "soft_constraint_score": 0.0,
                "generation_time_seconds": 0.0
            }
        })
    finally:
        db.close()


@router.post("/generate/async")
def generate_timetable_async(
    request: GenerationRequest,
    db: Session = Depends(get_db)
):
    """
    Start timetable generation in background thread.
    Returns immediately with a task_id to poll for status.
    """
    task_id = str(uuid.uuid4())[:8]
    _generation_tasks[task_id] = {
        "status": "queued",
        "started_at": None,
        "result": None
    }
    
    request_data = {
        "semester_ids": request.semester_ids,
        "dept_id": request.dept_id,
        "clear_existing": request.clear_existing,
        "semester_type": request.semester_type
    }
    
    thread = threading.Thread(
        target=_run_generation_task,
        args=(task_id, request_data),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued", "message": "Generation started in background"}


@router.get("/generate/status/{task_id}")
def get_generation_status(task_id: str):
    """Poll for async generation status."""
    task = _generation_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    response = {"task_id": task_id, "status": task["status"]}
    if task["result"]:
        response["result"] = task["result"]
    if task["started_at"]:
        response["elapsed_seconds"] = round(time_module.time() - task["started_at"], 1)
    
    # Clean up completed tasks after retrieval (keep memory clean)
    if task["status"] in ("completed", "failed"):
        # Don't delete immediately - let client poll a couple more times
        pass
    
    return response

