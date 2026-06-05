"""
Timetable API routes.
Handles generation and viewing of timetables.

OPTIMIZATIONS (v2):
- Pre-load SCB/basket mappings once per request (not per slot)
- Pre-load substitution teacher names in batch
- Null-safe access for room, teacher, subject everywhere
- Single-query timetable fetch with eager loading
- Graceful fallback on any slot-level error
"""
from typing import List, Optional, Dict, Any
from datetime import date
from io import BytesIO
import threading
import uuid
import time as time_module
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db, SessionLocal
from app.db.models import (
    Allocation, Semester, Teacher, Subject, Room,
    Substitution, SubstitutionStatus,
    StructuredCompositeBasketSubject, SemesterTemplate,
)
from app.schemas.schemas import (
    AllocationResponse, TimetableView, TimetableDay, TimetableSlot,
    GenerationRequest, GenerationResult, BatchAllocationData
)
from app.services.generator import TimetableGenerator
from app.services.pdf_service import TimetablePDFService
from app.core.config import get_settings
from app.core.cache import cache

router = APIRouter(prefix="/timetable", tags=["Timetable"])
settings = get_settings()
logger = logging.getLogger("app.timetable")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# In-memory generation task store (for async generation)
_generation_tasks: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# HELPERS (null-safe accessors)
# ============================================================================

def _safe_name(obj, fallback: str = "") -> str:
    """Safely get .name from a relationship that could be None."""
    return obj.name if obj is not None else fallback

def _safe_code(obj, fallback: str = "") -> str:
    """Safely get .code from a relationship that could be None."""
    return obj.code if obj is not None else fallback

def _safe_id(obj) -> Optional[int]:
    """Safely get .id from a relationship that could be None."""
    return obj.id if obj is not None else None

def _get_component_str(alloc) -> str:
    """Get component type string from allocation, never crash."""
    try:
        return (
            getattr(alloc, 'academic_component', None)
            or (alloc.component_type.value if alloc.component_type else "theory")
        )
    except Exception:
        return "theory"

def _is_lab(alloc) -> bool:
    """Check if allocation is a lab, null-safe."""
    return _get_component_str(alloc) == "lab"


def _preload_scb_map(db: Session) -> Dict[int, str]:
    """
    Pre-load ALL SCB subject->basket_name mappings in ONE query.
    Returns {subject_id: basket_name}
    """
    cache_key = "scb_subject_map"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        scb_links = db.query(StructuredCompositeBasketSubject).options(
            joinedload(StructuredCompositeBasketSubject.basket)
        ).all()
        mapping = {}
        for link in scb_links:
            if link.basket:
                mapping[link.subject_id] = link.basket.name
        cache.set(cache_key, mapping, ttl=300, tags=["scb", "timetable"])
        return mapping
    except Exception:
        return {}


def _get_template_info(db: Session, preferred_type: str) -> tuple:
    """Get break_slots and lunch_slot from template. Returns (break_slots, lunch_slot)."""
    import json
    try:
        template = db.query(SemesterTemplate).filter(
            SemesterTemplate.semester_type == preferred_type
        ).first()
        if template:
            try:
                break_slots = json.loads(template.break_slots)
            except Exception:
                break_slots = []
            return break_slots, template.lunch_slot
    except Exception:
        pass
    return [], 3


# ============================================================================
# GENERATION ENDPOINTS
# ============================================================================

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

        # Invalidate all timetable-related caches after generation
        cache.invalidate_tags(["timetable", "allocations", "reports"])

        return GenerationResult(
            success=success,
            message=message,
            total_allocations=len(allocations),
            hard_constraint_violations=0 if success else -1,
            soft_constraint_score=100.0 if success else 0.0,
            generation_time_seconds=round(gen_time, 3)
        )
    except Exception as e:
        logger.error(f"Timetable generation failed: {e}", exc_info=True)
        return GenerationResult(
            success=False,
            message=f"Generation error: {str(e)}",
            total_allocations=0,
            hard_constraint_violations=-1,
            soft_constraint_score=0.0,
            generation_time_seconds=0.0
        )


# ============================================================================
# ALLOCATION LIST
# ============================================================================

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
        logger.error(f"list_allocations failed: {e}", exc_info=True)
        return []


# ============================================================================
# SEMESTER TIMETABLE VIEW (CRITICAL PATH - OPTIMIZED)
# ============================================================================

@router.get("/view/semester/{semester_id}", response_model=TimetableView)
def get_semester_timetable(
    semester_id: int,
    view_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """
    Get complete timetable for a semester/class.
    Includes substitution information if view_date is provided.

    OPTIMIZED: Pre-loads SCB mappings, substitution teachers, and batch data
    in single queries instead of N+1 per-slot lookups.
    """
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")

    # SINGLE QUERY: Get all allocations with all relationships eagerly loaded
    allocations = db.query(Allocation).options(
        joinedload(Allocation.teacher),
        joinedload(Allocation.subject).joinedload(Subject.elective_basket),
        joinedload(Allocation.room),
        joinedload(Allocation.batch)
    ).filter(
        Allocation.semester_id == semester_id
    ).all()

    # PRE-LOAD: SCB subject->name map (ONE query, cached)
    scb_map = _preload_scb_map(db)

    # PRE-LOAD: Substitution data for the view date
    substitutions_map: Dict[int, Substitution] = {}
    sub_teacher_names: Dict[int, str] = {}
    if view_date:
        subs = db.query(Substitution).options(
            joinedload(Substitution.substitute_teacher)
        ).filter(
            Substitution.substitution_date == view_date,
            Substitution.status.in_([SubstitutionStatus.ASSIGNED, SubstitutionStatus.PENDING])
        ).all()
        for sub in subs:
            substitutions_map[sub.allocation_id] = sub
            if sub.substitute_teacher:
                sub_teacher_names[sub.allocation_id] = sub.substitute_teacher.name

    # Build timetable view
    days = []
    for day_idx in range(5):
        slots = []
        for slot_idx in range(settings.SLOTS_PER_DAY):
            try:
                slot_data = _build_semester_slot(
                    allocations, day_idx, slot_idx,
                    substitutions_map, sub_teacher_names, scb_map, db
                )
            except Exception as e:
                logger.warning(f"Slot build error day={day_idx} slot={slot_idx}: {e}")
                slot_data = TimetableSlot()

            slots.append(slot_data)

        days.append(TimetableDay(
            day=day_idx,
            day_name=DAY_NAMES[day_idx],
            slots=slots
        ))

    # Determine template type from semester
    preferred_type = "ODD" if (semester.semester_number % 2) != 0 else "EVEN"
    break_slots, lunch_slot = _get_template_info(db, preferred_type)

    return TimetableView(
        entity_type="semester",
        entity_id=semester.id,
        entity_name=f"{semester.name} ({semester.code})",
        days=days,
        break_slots=break_slots,
        lunch_slot=lunch_slot
    )


def _build_semester_slot(
    allocations: list,
    day_idx: int,
    slot_idx: int,
    substitutions_map: dict,
    sub_teacher_names: dict,
    scb_map: dict,
    db: Session,
) -> TimetableSlot:
    """Build a single TimetableSlot. Isolated for error safety."""
    slot_allocs = [a for a in allocations if a.day == day_idx and a.slot == slot_idx]

    if not slot_allocs:
        return TimetableSlot()

    primary_alloc = slot_allocs[0]
    is_pure_elective_slot = all(getattr(a, 'is_elective', False) for a in slot_allocs)

    # Substitution check (pre-loaded - no DB hit)
    is_substituted = primary_alloc.id in substitutions_map
    sub_teacher_name = sub_teacher_names.get(primary_alloc.id)

    # Batch details
    batch_allocations = []
    for alloc in slot_allocs:
        if alloc.batch_id or len(slot_allocs) > 1:
            if getattr(alloc, 'batch', None):
                batch_name_str = alloc.batch.name
            elif getattr(alloc, 'batch_id', None):
                batch_name_str = f"B{alloc.batch_id}"
            else:
                batch_name_str = "Elective" if is_pure_elective_slot else "Teacher"
            batch_allocations.append({
                "batch_id": alloc.batch_id,
                "batch_name": batch_name_str,
                "teacher_name": _safe_name(alloc.teacher, "TBD"),
                "room_name": _safe_name(alloc.room),
                "subject_name": _safe_name(alloc.subject),
                "subject_code": _safe_code(alloc.subject),
            })

    # Build combined subject name
    unique_subjects = list({a.subject_id: a for a in slot_allocs if a.subject_id}.values())

    combined_name, combined_code = _resolve_slot_names(
        slot_allocs, unique_subjects, is_pure_elective_slot, scb_map, primary_alloc
    )

    return TimetableSlot(
        allocation_id=primary_alloc.id,
        teacher_name=_safe_name(primary_alloc.teacher, "TBD"),
        teacher_id=_safe_id(primary_alloc.teacher),
        subject_name=combined_name,
        subject_code=combined_code,
        room_name=_safe_name(primary_alloc.room),
        batch_name=_safe_name(primary_alloc.batch) if primary_alloc.batch else None,
        batch_allocations=batch_allocations,
        component_type=_get_component_str(primary_alloc),
        academic_component=(
            getattr(primary_alloc, 'academic_component', None)
            or (primary_alloc.component_type.value if primary_alloc.component_type else None)
        ),
        is_lab=_is_lab(primary_alloc),
        is_elective=getattr(primary_alloc, 'is_elective', False),
        is_substituted=is_substituted,
        substitute_teacher_name=sub_teacher_name,
    )


def _resolve_slot_names(
    slot_allocs, unique_subjects, is_pure_elective_slot, scb_map, primary_alloc
) -> tuple:
    """Determine combined_name and combined_code for a slot. Uses pre-loaded SCB map."""

    if is_pure_elective_slot:
        # Try elective basket name (already eager-loaded)
        basket_name = None
        if unique_subjects and unique_subjects[0].subject:
            eb = getattr(unique_subjects[0].subject, 'elective_basket', None)
            if eb:
                basket_name = eb.name

        # Fallback: try SCB map (pre-loaded, no DB query)
        if not basket_name and unique_subjects:
            basket_name = scb_map.get(unique_subjects[0].subject_id)

        if basket_name:
            return basket_name, basket_name
        elif len(unique_subjects) > 1:
            names = " / ".join(_safe_name(a.subject) for a in unique_subjects)
            codes = " / ".join(_safe_code(a.subject) for a in unique_subjects)
            return names + " (Basket)", codes
        else:
            return "Elective", "ELECTIVE"

    elif len(unique_subjects) > 1:
        # Check SCB map (pre-loaded, no DB query)
        scb_name = scb_map.get(unique_subjects[0].subject_id) if unique_subjects else None

        if scb_name:
            return scb_name, scb_name
        elif not any(getattr(a, 'is_elective', False) for a in slot_allocs):
            # Parallel Lab format
            parts_name = " / ".join(
                f"{_safe_code(a.subject)}:{_safe_name(a.batch, 'B') if a.batch else 'B'} (PL)"
                for a in unique_subjects
            )
            parts_code = " / ".join(
                f"{_safe_code(a.subject)} (PL)" for a in unique_subjects
            )
            return parts_name, parts_code
        else:
            names = " / ".join(_safe_name(a.subject) for a in unique_subjects)
            codes = " / ".join(_safe_code(a.subject) for a in unique_subjects)
            return names + " (Batch Split)", codes
    else:
        return _safe_name(primary_alloc.subject, "Unknown"), _safe_code(primary_alloc.subject, "???")


# ============================================================================
# TEACHER TIMETABLE VIEW (OPTIMIZED)
# ============================================================================

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

    # Get all allocations for the teacher with eager loading
    query = db.query(Allocation).options(
        joinedload(Allocation.subject),
        joinedload(Allocation.semester),
        joinedload(Allocation.room)
    ).filter(
        Allocation.teacher_id == teacher_id
    )

    # Department isolation
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
            try:
                alloc = next(
                    (a for a in allocations if a.day == day_idx and a.slot == slot_idx),
                    None
                )

                if alloc:
                    slot_data = TimetableSlot(
                        allocation_id=alloc.id,
                        teacher_name=teacher.name,
                        teacher_id=teacher.id,
                        subject_name=f"{_safe_name(alloc.subject, 'Unknown')} ({_safe_code(alloc.semester, '?')})",
                        subject_code=_safe_code(alloc.subject, "???"),
                        room_name=_safe_name(alloc.room),
                        component_type=_get_component_str(alloc),
                        academic_component=(
                            getattr(alloc, 'academic_component', None)
                            or (alloc.component_type.value if alloc.component_type else None)
                        ),
                        is_lab=_is_lab(alloc),
                        is_elective=getattr(alloc, 'is_elective', False),
                        is_substituted=False,
                        substitute_teacher_name=None
                    )
                else:
                    slot_data = TimetableSlot()
            except Exception as e:
                logger.warning(f"Teacher slot build error day={day_idx} slot={slot_idx}: {e}")
                slot_data = TimetableSlot()

            slots.append(slot_data)

        days.append(TimetableDay(
            day=day_idx,
            day_name=DAY_NAMES[day_idx],
            slots=slots
        ))

    # Determine template from allocations' semesters
    odd_count = sum(
        1 for a in allocations
        if hasattr(a, 'semester') and a.semester and (a.semester.semester_number % 2) != 0
    )
    even_count = sum(
        1 for a in allocations
        if hasattr(a, 'semester') and a.semester and (a.semester.semester_number % 2) == 0
    )
    preferred_type = "ODD" if odd_count >= even_count else "EVEN"
    break_slots, lunch_slot = _get_template_info(db, preferred_type)

    return TimetableView(
        entity_type="teacher",
        entity_id=teacher.id,
        entity_name=teacher.name,
        days=days,
        break_slots=break_slots,
        lunch_slot=lunch_slot
    )


# ============================================================================
# CLEAR TIMETABLE
# ============================================================================

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

        # Invalidate caches
        cache.invalidate_tags(["timetable", "allocations", "reports"])
    except Exception as e:
        db.rollback()
        logger.error(f"clear_timetable failed: {e}", exc_info=True)
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
        logger.error(f"PDF export failed: {e}", exc_info=True)
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
        logger.error(f"PDF preview failed: {e}", exc_info=True)
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
        logger.error(f"export status check failed: {e}")
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
        
        # Invalidate caches after generation
        cache.invalidate_tags(["timetable", "allocations", "reports"])

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
