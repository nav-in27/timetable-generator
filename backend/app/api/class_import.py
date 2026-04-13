"""
API endpoints for bulk Class/Semester Excel/CSV import.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.db.session import get_db
from app.services.class_import_service import ClassImportService

router = APIRouter(prefix="/semesters/import", tags=["Class Import"])

_pending_imports: dict = {}

@router.post("/upload")
async def upload_and_validate(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = (".xlsx", ".xls", ".csv")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(allowed)}")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    service = ClassImportService(db)
    result = service.parse_and_validate(contents, file.filename)

    if result.batch_id and not result.schema_errors:
        _pending_imports[result.batch_id] = {
            "result": result,
            "file_bytes": contents,
            "filename": file.filename,
        }

    return result.to_dict()

@router.post("/commit")
async def commit_import(batch_id: str, db: Session = Depends(get_db)):
    pending = _pending_imports.get(batch_id)
    if not pending:
        raise HTTPException(status_code=404, detail=f"Import batch '{batch_id}' not found. Please re-upload.")

    result = pending["result"]
    if result.schema_errors:
        raise HTTPException(status_code=400, detail={"message": "Cannot commit", "errors": result.schema_errors})

    service = ClassImportService(db)
    reparsed = service.parse_and_validate(pending["file_bytes"], pending["filename"])

    if reparsed.schema_errors:
        return reparsed.to_dict()

    final = service.commit_import(reparsed)
    _pending_imports.pop(batch_id, None)

    return final.to_dict()

@router.get("/template")
async def download_template():
    template_bytes = ClassImportService.generate_template()
    return StreamingResponse(
        io.BytesIO(template_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=class_import_template.xlsx"},
    )

@router.get("/health")
async def import_health_check(db: Session = Depends(get_db)):
    service = ClassImportService(db)
    service._warm_caches()
    return service._run_health_check()
