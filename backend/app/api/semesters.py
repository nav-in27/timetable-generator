"""
CRUD API routes for Semesters (Classes).
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Semester
from app.schemas.schemas import SemesterCreate, SemesterUpdate, SemesterResponse

router = APIRouter(prefix="/semesters", tags=["Semesters/Classes"])


@router.get("/", response_model=List[SemesterResponse])
def list_semesters(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all semesters/classes."""
    semesters = db.query(Semester).offset(skip).limit(limit).all()
    return semesters


@router.get("/{semester_id}", response_model=SemesterResponse)
def get_semester(semester_id: int, db: Session = Depends(get_db)):
    """Get a specific semester by ID."""
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
    return semester


@router.post("/", response_model=SemesterResponse, status_code=status.HTTP_201_CREATED)
def create_semester(semester_data: SemesterCreate, db: Session = Depends(get_db)):
    """Create a new semester/class."""
    # Check for duplicate code
    existing = db.query(Semester).filter(Semester.code == semester_data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Semester with this code already exists")
    
    semester = Semester(**semester_data.model_dump())
    db.add(semester)
    db.commit()
    db.refresh(semester)
    return semester


@router.put("/{semester_id}", response_model=SemesterResponse)
def update_semester(semester_id: int, semester_data: SemesterUpdate, db: Session = Depends(get_db)):
    """Update a semester."""
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
    
    update_data = semester_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(semester, key, value)
    
    db.commit()
    db.refresh(semester)
    return semester


@router.delete("/{semester_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_semester(semester_id: int, db: Session = Depends(get_db)):
    """Delete a semester."""
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
    
    db.delete(semester)
    db.commit()
    return None
