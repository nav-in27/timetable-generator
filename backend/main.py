"""
AI Dept Timetable Generator - FastAPI Backend

Main application entry point.
Configures CORS, includes all API routes, and initializes the database.
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

# Force UTF-8 encoding for logs
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    # Python < 3.7 or some environments
    pass

# Import all routers
from app.api import rooms, subjects, teachers, semesters, timetable, substitution, dashboard, elective_baskets, fixed_slots

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    # Create all database tables
    Base.metadata.create_all(bind=engine)
    print("[INFO] Database tables created/verified")
    
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
    allow_origins=["*"],  # Allow all origins for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    """Health check endpoint."""
    return {"status": "healthy"}


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
