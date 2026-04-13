"""
API endpoints for bulk Subject Excel/CSV import.

Endpoints:
  POST /subjects/import/upload      — Upload + validate (no DB write)
  POST /subjects/import/commit      — Commit validated import
  GET  /subjects/import/template    — Download Excel template
  GET  /subjects/import/health      — Post-import health check
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
import json

from app.db.session import get_db
from app.services.subject_import_service import SubjectImportService

router = APIRouter(prefix="/subjects/import", tags=["Subject Import"])

# Store the last parse result in-memory (per-process; fine for single-server)
# In production with multiple workers, use Redis or a temp table.
_pending_imports: dict = {}


@router.post("/upload")
async def upload_and_validate(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload an Excel (.xlsx) or CSV file and validate it.
    Returns a preview of all rows with validation status.
    Does NOT write to the database — call /commit after review.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = (".xlsx", ".xls", ".csv")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed)}"
        )

    # Read file bytes (limit to 10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    service = SubjectImportService(db)
    result = service.parse_and_validate(contents, file.filename)

    # Store for later commit
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
    Commit a previously validated import batch.
    The batch_id is returned from the /upload endpoint.
    """
    pending = _pending_imports.get(batch_id)
    if not pending:
        # Re-parse if batch not found (could be lost due to server restart)
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

    # Re-create service with fresh db session
    service = SubjectImportService(db)
    # Re-parse to ensure fresh state against current DB
    reparsed = service.parse_and_validate(pending["file_bytes"], pending["filename"])

    if reparsed.schema_errors:
        return reparsed.to_dict()

    final = service.commit_import(reparsed)

    # Clean up pending
    _pending_imports.pop(batch_id, None)

    return final.to_dict()


@router.get("/template")
async def download_template():
    """
    Download the standard Excel import template with headers and example data.
    """
    template_bytes = SubjectImportService.generate_template()
    return StreamingResponse(
        io.BytesIO(template_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=subject_import_template.xlsx"
        },
    )


@router.get("/health")
async def import_health_check(db: Session = Depends(get_db)):
    """
    Run post-import health check on current subject data.
    """
    service = SubjectImportService(db)
    service._warm_caches()
    return service._run_health_check()
