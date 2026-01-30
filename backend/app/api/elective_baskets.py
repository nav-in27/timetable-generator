"""
CRUD API routes for Elective Baskets.
Manages elective groups that share common scheduling slots.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import ElectiveBasket, Subject, Semester, elective_basket_semesters
from app.schemas.schemas import (
    ElectiveBasketCreate, 
    ElectiveBasketUpdate, 
    ElectiveBasketResponse
)

router = APIRouter(prefix="/elective-baskets", tags=["Elective Baskets"])


@router.get("/", response_model=List[ElectiveBasketResponse])
def list_elective_baskets(db: Session = Depends(get_db)):
    """Get all elective baskets."""
    baskets = db.query(ElectiveBasket).all()
    return baskets


@router.get("/{basket_id}", response_model=ElectiveBasketResponse)
def get_elective_basket(basket_id: int, db: Session = Depends(get_db)):
    """Get a specific elective basket."""
    basket = db.query(ElectiveBasket).filter(ElectiveBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Elective basket not found")
    return basket


@router.post("/", response_model=ElectiveBasketResponse, status_code=status.HTTP_201_CREATED)
def create_elective_basket(basket_data: ElectiveBasketCreate, db: Session = Depends(get_db)):
    """
    Create a new elective basket.
    
    An elective basket groups subjects that are alternatives for students.
    All subjects in a basket are scheduled at the same common slots.
    """
    # Check for duplicate code
    existing = db.query(ElectiveBasket).filter(ElectiveBasket.code == basket_data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Elective basket with this code already exists")
    
    # Create basket
    basket = ElectiveBasket(
        name=basket_data.name,
        code=basket_data.code,
        semester_number=basket_data.semester_number,
        theory_hours_per_week=basket_data.theory_hours_per_week,
        lab_hours_per_week=basket_data.lab_hours_per_week,
        tutorial_hours_per_week=basket_data.tutorial_hours_per_week
    )
    
    # Assign participating semesters
    if basket_data.semester_ids:
        sems = db.query(Semester).filter(Semester.id.in_(basket_data.semester_ids)).all()
        basket.participating_semesters = sems
    
    db.add(basket)
    db.commit()  # Commit first to get the basket ID
    db.refresh(basket)
    
    # Now assign subjects to basket using the real basket ID
    if basket_data.subject_ids:
        subjects = db.query(Subject).filter(Subject.id.in_(basket_data.subject_ids)).all()
        for subject in subjects:
            subject.elective_basket_id = basket.id
            subject.is_elective = True
            # CRITICAL: Synchronize subject semesters with basket semesters
            if basket.participating_semesters:
                subject.semesters = basket.participating_semesters
        db.commit()
        db.refresh(basket)
    
    return basket


@router.put("/{basket_id}", response_model=ElectiveBasketResponse)
def update_elective_basket(
    basket_id: int, 
    basket_data: ElectiveBasketUpdate, 
    db: Session = Depends(get_db)
):
    """Update an elective basket."""
    basket = db.query(ElectiveBasket).filter(ElectiveBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Elective basket not found")
    
    update_data = basket_data.model_dump(exclude_unset=True)
    
    # Handle subject assignment update
    if 'subject_ids' in update_data:
        subject_ids = update_data.pop('subject_ids')
        if subject_ids is not None:
            # Remove old assignments
            old_subjects = db.query(Subject).filter(
                Subject.elective_basket_id == basket_id
            ).all()
            for subj in old_subjects:
                subj.elective_basket_id = None
                subj.is_elective = False
            
            # Add new assignments
            new_subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
            for subj in new_subjects:
                subj.elective_basket_id = basket_id
                subj.is_elective = True
                # Synchronize
                if basket.participating_semesters:
                    subj.semesters = basket.participating_semesters
    
    # Handle semester assignment update
    if 'semester_ids' in update_data:
        sem_ids = update_data.pop('semester_ids')
        if sem_ids is not None:
            sems = db.query(Semester).filter(Semester.id.in_(sem_ids)).all()
            basket.participating_semesters = sems
            
            # Synchronize all subjects in this basket to these new semesters
            for subj in basket.subjects:
                subj.semesters = sems
    
    # Update remaining fields
    for key, value in update_data.items():
        setattr(basket, key, value)
    
    db.commit()
    db.refresh(basket)
    return basket


@router.delete("/{basket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_elective_basket(basket_id: int, db: Session = Depends(get_db)):
    """
    Delete an elective basket.
    This will unlink subjects but NOT delete them.
    """
    basket = db.query(ElectiveBasket).filter(ElectiveBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Elective basket not found")
    
    # Unlink subjects
    subjects = db.query(Subject).filter(Subject.elective_basket_id == basket_id).all()
    for subj in subjects:
        subj.elective_basket_id = None
        subj.is_elective = False
    
    # Clear semester associations
    basket.participating_semesters = []
    
    db.delete(basket)
    db.commit()
    
    return None


@router.get("/{basket_id}/subjects")
def get_basket_subjects(basket_id: int, db: Session = Depends(get_db)):
    """Get all subjects in an elective basket."""
    basket = db.query(ElectiveBasket).filter(ElectiveBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Elective basket not found")
    
    subjects = db.query(Subject).filter(Subject.elective_basket_id == basket_id).all()
    
    return {
        "basket_id": basket_id,
        "basket_name": basket.name,
        "semester_number": basket.semester_number,
        "subjects": [
            {
                "id": s.id,
                "name": s.name,
                "code": s.code,
                "theory_hours": s.theory_hours_per_week,
                "lab_hours": s.lab_hours_per_week
            } for s in subjects
        ]
    }


@router.post("/{basket_id}/add-subject/{subject_id}")
def add_subject_to_basket(basket_id: int, subject_id: int, db: Session = Depends(get_db)):
    """Add a subject to an elective basket."""
    basket = db.query(ElectiveBasket).filter(ElectiveBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Elective basket not found")
    
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Check if already in a basket
    if subject.elective_basket_id and subject.elective_basket_id != basket_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Subject is already in another elective basket (ID: {subject.elective_basket_id})"
        )
    
    subject.elective_basket_id = basket_id
    subject.is_elective = True
    
    # Synchronize
    if basket.participating_semesters:
        subject.semesters = basket.participating_semesters
    
    db.commit()
    
    return {"message": f"Subject '{subject.name}' added to basket '{basket.name}'"}


@router.delete("/{basket_id}/remove-subject/{subject_id}")
def remove_subject_from_basket(basket_id: int, subject_id: int, db: Session = Depends(get_db)):
    """Remove a subject from an elective basket."""
    subject = db.query(Subject).filter(
        Subject.id == subject_id, 
        Subject.elective_basket_id == basket_id
    ).first()
    
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found in this basket")
    
    subject.elective_basket_id = None
    subject.is_elective = False
    
    db.commit()
    
    return {"message": f"Subject '{subject.name}' removed from basket"}
