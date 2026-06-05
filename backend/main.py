"""
AI Dept Timetable Generator - FastAPI Backend

Main application entry point.
Configures CORS, includes all API routes, and initializes the database.

OPTIMIZATIONS (v2):
- Startup repair: indexes, orphan cleanup, integrity checks
- Structured error responses with diagnostics
- Cache management endpoints
- Connection stability improvements
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
import sys
import os
import logging
import traceback as tb_module
import time

# Run static checks before doing anything else
from app.startup_check import run_startup_validation
run_startup_validation()

# Configure logging: reduce noise in localhost
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logging.getLogger('app').setLevel(logging.INFO)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Force UTF-8 encoding for logs
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    # Python < 3.7 or some environments
    pass

# Import all routers
from app.api import (
    rooms,
    subjects,
    teachers,
    semesters,
    timetable,
    substitution,
    dashboard,
    elective_baskets,
    fixed_slots,
    departments,
    reports,
    rule_toggles,
    parallel_lab_baskets,
    room_availability,
    structured_composite_baskets,
    allocation,
    feasibility,
    subject_import,
    teacher_import,
    department_import,
    class_import,
    room_import,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    # Create all database tables
    Base.metadata.create_all(bind=engine)
    print("[INFO] Database tables created/verified")

    # Safe schema updates for backward-compatible columns (SQLite)
    try:
        from update_db_schema import update_schema
        update_schema()
        print("[INFO] Database schema updates applied (if needed)")
    except Exception as e:
        print(f"[WARN] Schema update failed (non-critical): {e}")
    
    # Auto-seed if needed (wrapped in try-except to prevent crash)
    try:
        from seed_data import seed_database
        print("[INFO] Checking for seed data...")
        seed_database()
        print("[INFO] Database check/seed completed")
    except ImportError:
        print("[WARN] Could not import seed_data. Skipping auto-seed.")
    except Exception as e:
        print(f"[WARN] Auto-seeding failed (non-critical): {e}")

    # Startup repair: indexes, orphans, integrity
    try:
        from app.db.startup_repair import run_startup_repair
        from app.db.session import SessionLocal
        repair_db = SessionLocal()
        try:
            run_startup_repair(repair_db)
            print("[INFO] Startup repair completed")
        finally:
            repair_db.close()
    except Exception as e:
        print(f"[WARN] Startup repair failed (non-critical): {e}")

    yield
    # Cleanup (if needed)
    print("[INFO] Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="""
    ## AI Dept Timetable Generator with Automated Teacher Substitution
    
    A modern, scalable solution for:
    - **Resource Management**: Teachers, Subjects, Classes, Rooms
    - **Automatic Timetable Generation**: CSP + Genetic Algorithm
    - **Intelligent Teacher Substitution**: Score-based candidate selection
    - **Free Periods**: 1-2 free periods per class per week
    
    ### Features:
    - Hard constraint validation (no conflicts)
    - Soft constraint optimization (balanced workload)
    - Real-time substitution workflow
    - View timetables by class or teacher
    """,
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend (allow all origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler - NEVER crash the server
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch all unhandled exceptions and return structured JSON error.
    
    Response format:
    {
        "success": false,
        "message": "Human-readable error description",
        "data": null,
        "errors": ["Detailed error info"],
        "diagnostics": {"path": ..., "type": ..., "method": ...}
    }
    """
    error_detail = str(exc)
    tb_str = tb_module.format_exc()
    logging.getLogger('app').error(f"Unhandled error on {request.url.path}: {error_detail}\n{tb_str}")
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Internal server error: {error_detail}",
            "data": None,
            "errors": [error_detail],
            "diagnostics": {
                "path": str(request.url.path),
                "type": type(exc).__name__,
                "method": request.method,
            }
        }
    )

# Include API routers
app.include_router(dashboard.router, prefix="/api")
app.include_router(rooms.router, prefix="/api")
app.include_router(subjects.router, prefix="/api")
app.include_router(teachers.router, prefix="/api")
app.include_router(semesters.router, prefix="/api")
app.include_router(timetable.router, prefix="/api")
app.include_router(substitution.router, prefix="/api")
app.include_router(elective_baskets.router, prefix="/api")
app.include_router(fixed_slots.router, prefix="/api")
app.include_router(departments.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(rule_toggles.router, prefix="/api")
app.include_router(parallel_lab_baskets.router, prefix="/api")
app.include_router(room_availability.router, prefix="/api")
app.include_router(structured_composite_baskets.router, prefix="/api")
app.include_router(allocation.router, prefix="/api")
app.include_router(feasibility.router, prefix="/api")
app.include_router(subject_import.router, prefix="/api")
app.include_router(teacher_import.router, prefix="/api")
app.include_router(department_import.router, prefix="/api")
app.include_router(class_import.router, prefix="/api")
app.include_router(room_import.router, prefix="/api")


@app.get("/")
def root():
    """Root endpoint with API information."""
    return {
        "message": "AI Dept Timetable Generator API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
def health_check():
    """Health check endpoint with diagnostics."""
    from app.core.cache import cache
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
            db_status = "healthy"
        except Exception as e:
            db_status = f"unhealthy: {e}"
        finally:
            db.close()
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "cache": cache.stats(),
    }


@app.post("/api/cache/clear")
def clear_cache():
    """Clear all cached data. Useful after bulk imports or manual DB changes."""
    from app.core.cache import cache
    cache.clear()
    return {"success": True, "message": "Cache cleared"}


@app.get("/api/cache/stats")
def cache_stats():
    """Get cache statistics."""
    from app.core.cache import cache
    return {"success": True, "data": cache.stats()}


# --- Static File Serving (for production) ---
# This allows serving the React frontend from the backend server
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    # Mount assets folder for direct file access
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Prevent shadowing API routes
        if full_path.startswith("api") or full_path.startswith("docs") or full_path.startswith("redoc"):
            return None
            
        file_path = os.path.join(static_dir, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # Single Page Application: Fallback to index.html
        return FileResponse(os.path.join(static_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    import os
    import socket

    def is_port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # Use 0.0.0.0 for checking to be consistent with binding
            return s.connect_ex(("127.0.0.1", port)) == 0

    def find_available_port(start_port: int, max_tries: int = 20) -> int:
        port = start_port
        for _ in range(max_tries):
            if not is_port_in_use(port):
                return port
            port += 1
        raise RuntimeError(f"No free port found starting from {start_port}")

    # For deployment (Render/Vercel/Docker), we want to bind to 0.0.0.0
    # For local dev, 127.0.0.1 is fine, but 0.0.0.0 is more flexible
    port_env = os.getenv("PORT")
    if port_env:
        # In production environments (like Render), PORT is provided
        selected_port = int(port_env)
        host = "0.0.0.0"
        reload = False # Disable reload in production
        print(f"[INFO] Production mode: binding to {host}:{selected_port}")
    else:
        # In local development
        default_port = 8000
        selected_port = find_available_port(default_port)
        host = "127.0.0.1"
        reload = True
        if selected_port != default_port:
            print(f"[WARN] Port {default_port} is in use. Using {selected_port} instead.")
        print(f"[INFO] Local development mode: binding to {host}:{selected_port}")

    uvicorn.run("main:app", host=host, port=selected_port, reload=reload)
