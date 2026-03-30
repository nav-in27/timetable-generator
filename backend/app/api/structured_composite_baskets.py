from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import (
    StructuredCompositeBasket, 
    StructuredCompositeBasketSubject,
    Subject, 
    Department,
    Semester
)
from app.schemas.schemas import (
    StructuredCompositeBasketCreate, 
    StructuredCompositeBasketUpdate, 
    StructuredCompositeBasketResponse
)

router = APIRouter(prefix="/structured-composite-baskets", tags=["Structured Composite Baskets"])


def _basket_to_dict(b):
    """Convert a StructuredCompositeBasket ORM object to a response dict."""
    return {
        "id": b.id,
        "name": b.name,
        "semester": b.semester,
        "theory_hours": b.theory_hours,
        "lab_hours": b.lab_hours,
        "continuous_lab_periods": b.continuous_lab_periods,
        "same_slot_across_departments": b.same_slot_across_departments,
        "allow_lab_parallel": b.allow_lab_parallel,
        "is_scheduled": b.is_scheduled,
        "scheduled_slots": b.scheduled_slots,
        "departments_involved": b.departments_involved,
        "selected_classes": b.selected_classes,
        "linked_subjects": [link.subject for link in b.linked_subjects]
    }


@router.get("/", response_model=List[StructuredCompositeBasketResponse])
def list_scb(db: Session = Depends(get_db)):
    """Get all structured composite baskets."""
    baskets = db.query(StructuredCompositeBasket).all()
    return [_basket_to_dict(b) for b in baskets]


@router.get("/{basket_id}", response_model=StructuredCompositeBasketResponse)
def get_scb(basket_id: int, db: Session = Depends(get_db)):
    """Get a specific SCB."""
    basket = db.query(StructuredCompositeBasket).filter(StructuredCompositeBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Structured Composite Basket not found")
    return _basket_to_dict(basket)


@router.post("/", response_model=StructuredCompositeBasketResponse, status_code=status.HTTP_201_CREATED)
def create_scb(basket_data: StructuredCompositeBasketCreate, db: Session = Depends(get_db)):
    """Create a new Structured Composite Basket."""
    basket = StructuredCompositeBasket(
        name=basket_data.name,
        semester=basket_data.semester,
        theory_hours=basket_data.theory_hours,
        lab_hours=basket_data.lab_hours,
        continuous_lab_periods=basket_data.continuous_lab_periods,
        same_slot_across_departments=basket_data.same_slot_across_departments,
        allow_lab_parallel=basket_data.allow_lab_parallel
    )
    
    # Assign participating departments
    if basket_data.department_ids:
        depts = db.query(Department).filter(Department.id.in_(basket_data.department_ids)).all()
        basket.departments_involved = depts

    # Assign selected classes (validate they belong to selected departments)
    if basket_data.class_ids:
        classes = db.query(Semester).filter(Semester.id.in_(basket_data.class_ids)).all()
        if basket_data.department_ids:
            dept_set = set(basket_data.department_ids)
            classes = [c for c in classes if c.dept_id in dept_set]
        basket.selected_classes = classes
        
    db.add(basket)
    db.commit()
    db.refresh(basket)
    
    # Link subjects
    if basket_data.subject_ids:
        for subj_id in basket_data.subject_ids:
            subject = db.query(Subject).filter(Subject.id == subj_id).first()
            if subject:
                link = StructuredCompositeBasketSubject(basket_id=basket.id, subject_id=subject.id)
                db.add(link)
        db.commit()
        db.refresh(basket)

    return _basket_to_dict(basket)


@router.put("/{basket_id}", response_model=StructuredCompositeBasketResponse)
def update_scb(basket_id: int, basket_data: StructuredCompositeBasketUpdate, db: Session = Depends(get_db)):
    """Update a Structured Composite Basket."""
    basket = db.query(StructuredCompositeBasket).filter(StructuredCompositeBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Structured Composite Basket not found")
        
    update_data = basket_data.model_dump(exclude_unset=True)
    
    if 'department_ids' in update_data:
        dept_ids = update_data.pop('department_ids')
        if dept_ids is not None:
            depts = db.query(Department).filter(Department.id.in_(dept_ids)).all()
            basket.departments_involved = depts

    if 'class_ids' in update_data:
        class_ids = update_data.pop('class_ids')
        if class_ids is not None:
            classes = db.query(Semester).filter(Semester.id.in_(class_ids)).all()
            # Validate against current departments
            current_dept_ids = {d.id for d in basket.departments_involved}
            classes = [c for c in classes if c.dept_id in current_dept_ids]
            basket.selected_classes = classes
            
    if 'subject_ids' in update_data:
        subj_ids = update_data.pop('subject_ids')
        if subj_ids is not None:
            # Clear old
            db.query(StructuredCompositeBasketSubject).filter(
                StructuredCompositeBasketSubject.basket_id == basket_id
            ).delete()
            # Add new
            for subj_id in subj_ids:
                subject = db.query(Subject).filter(Subject.id == subj_id).first()
                if subject:
                    link = StructuredCompositeBasketSubject(basket_id=basket.id, subject_id=subject.id)
                    db.add(link)
    
    for key, value in update_data.items():
        setattr(basket, key, value)
        
    db.commit()
    db.refresh(basket)
    
    return _basket_to_dict(basket)


@router.delete("/{basket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scb(basket_id: int, db: Session = Depends(get_db)):
    """Delete a Structured Composite Basket."""
    basket = db.query(StructuredCompositeBasket).filter(StructuredCompositeBasket.id == basket_id).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Structured Composite Basket not found")
        
    db.delete(basket)
    db.commit()
    return None
