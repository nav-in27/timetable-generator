"""
AI Dept Timetable Generator - FastAPI Backend

Main application entry point.
Configures CORS, includes all API routes, and initializes the database.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine

# Import all routers
from app.api import rooms, subjects, teachers, semesters, timetable, substitution, dashboard

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
