"""
API endpoints for bulk Teacher Mapping Excel/CSV import.

Endpoints:
  POST /teachers/import/upload      — Upload + validate (no DB write)
  POST /teachers/import/commit      — Commit validated import
  GET  /teachers/import/template    — Download Excel template
  GET  /teachers/import/health      — Post-import health check
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.db.session import get_db
from app.services.teacher_mapping_import_service import TeacherMappingImportService

router = APIRouter(prefix="/teachers/import", tags=["Teacher Mapping Import"])

_pending_imports: dict = {}


@router.post("/upload")
async def upload_and_validate(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload an Excel (.xlsx) or CSV file and validate teacher mappings.
    Returns a preview of all rows with validation status.
    Does NOT write to the database.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = (".xlsx", ".xls", ".csv")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed)}"
        )

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    service = TeacherMappingImportService(db)
    result = service.parse_and_validate(contents, file.filename)

    if result.batch_id and not result.schema_errors:
        _pending_imports[result.batch_id] = {
            "result": result,
            "file_bytes": contents,
            "filename": file.filename,
        }

    return result.to_dict()


@router.post("/commit")
async def commit_import(
    batch_id: str,
    db: Session = Depends(get_db),
):
    """
    Commit a previously validated teacher mapping import batch.
    """
    pending = _pending_imports.get(batch_id)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=f"Import batch '{batch_id}' not found. Please re-upload."
        )

    result = pending["result"]

    if result.schema_errors:
        raise HTTPException(status_code=400, detail={
            "message": "Cannot commit — schema errors exist",
            "errors": result.schema_errors,
        })

    # Re-parse with fresh db session
    service = TeacherMappingImportService(db)
    reparsed = service.parse_and_validate(pending["file_bytes"], pending["filename"])

    if reparsed.schema_errors:
        return reparsed.to_dict()

    final = service.commit_import(reparsed)
    _pending_imports.pop(batch_id, None)

    # Invalidate caches to ensure Dashboard and UI show fresh numbers
    from app.core.cache import cache
    cache.invalidate_tag("teachers")
    cache.invalidate_tag("dashboard")
    cache.invalidate_tag("reports")

    return final.to_dict()


@router.get("/template")
async def download_template():
    """Download the standard Excel teacher mapping template."""
    template_bytes = TeacherMappingImportService.generate_template()
    return StreamingResponse(
        io.BytesIO(template_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=teacher_mapping_template.xlsx"
        },
    )


@router.get("/health")
async def import_health_check(db: Session = Depends(get_db)):
    """Run health check on current teacher mapping data."""
    service = TeacherMappingImportService(db)
    service._warm_caches()
    return service._run_health_check()


@router.post("/repair-dependencies")
async def repair_dependencies(db: Session = Depends(get_db)):
    """
    Auto-repair missing dependencies in teacher mapping data.
    
    Actions performed:
    - Create missing subject-class links (subject_semesters entries)
    - Normalize teacher codes (strip leading zeros)
    - Remove exact duplicate CST mappings
    
    Safe to run multiple times (idempotent).
    """
    service = TeacherMappingImportService(db)
    result = service.repair_dependencies()
    
    # Invalidate caches after repairs
    from app.core.cache import cache
    cache.invalidate_tag("teachers")
    cache.invalidate_tag("subjects")
    cache.invalidate_tag("dashboard")
    
    return result
