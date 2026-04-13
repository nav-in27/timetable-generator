"""
CRUD API routes for Subjects.
Updated to support the CORRECT ACADEMIC DATA MODEL with component-based subjects.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.db.models import (
    Subject, Semester, SubjectType, ComponentType,
    ClassSubjectTeacher, Allocation, SubjectComponentAssignment,
    ElectiveBasket
)
from app.schemas.schemas import SubjectCreate, SubjectUpdate, SubjectResponse, SubjectWithTeachers

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get("/", response_model=List[SubjectResponse])
def list_subjects(
    skip: int = 0,
    limit: int = 100,
    dept_id: Optional[int] = None,
    year: Optional[int] = None,
    semester: Optional[int] = None,
    is_elective: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get all subjects with department-aware filtering."""
    query = db.query(Subject).options(
        selectinload(Subject.semesters)
    )
    
    # Department Filtering Rule:
    # - When a department is selected, show ONLY that department's subjects.
    # - Electives are college-level, but visibility is department-filtered using participating classes.
    if dept_id:
        from sqlalchemy import and_, or_

        elective_in_dept = and_(
            Subject.is_elective == True,
            Subject.semesters.any(Semester.dept_id == dept_id)
        )

        if is_elective is True:
            query = query.filter(elective_in_dept)
        elif is_elective is False:
            query = query.filter(Subject.dept_id == dept_id).filter(Subject.is_elective == False)
        else:
            query = query.filter(or_(Subject.dept_id == dept_id, elective_in_dept))
    
    if year:
        query = query.filter(Subject.year == year)
    if semester:
        query = query.filter(Subject.semester == semester)
        
    subjects = query.offset(skip).limit(limit).all()
    return subjects


@router.get("/{subject_id}", response_model=SubjectWithTeachers)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    """Get a specific subject by ID with its qualified teachers."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.post("/", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def create_subject(subject_data: SubjectCreate, db: Session = Depends(get_db)):
    """
    Create a new subject with the component-based model.
    
    Supports:
    - theory_hours_per_week
    - lab_hours_per_week  
    - tutorial_hours_per_week
    - is_elective flag
    
    Academic Rule: Non-elective subjects can only be assigned to classes of the same semester.
    """
    # Check for duplicate code
    existing = db.query(Subject).filter(Subject.code == subject_data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Subject with this code already exists")
    
    # Handle semester mapping
    data = subject_data.model_dump(exclude={'semester_ids', 'elective_basket_id'})
    
    # Calculate legacy weekly_hours for backward compatibility
    def _validate_block(component_name: str, hours: int, block_size: int):
        if hours <= 0:
            return
        if block_size == 2 and hours % 2 != 0:
            raise HTTPException(
                status_code=400,
                detail=f"{component_name} hours must be even when block size is 2 (continuous)."
            )

    _validate_block("Project", subject_data.project_hours_per_week, subject_data.project_block_size)
    _validate_block("Report", subject_data.report_hours_per_week, subject_data.report_block_size)
    _validate_block("Seminar", subject_data.seminar_hours_per_week, subject_data.seminar_block_size)

    if subject_data.seminar_day_based and subject_data.seminar_hours_per_week > 0:
        if subject_data.seminar_hours_per_week < 7:
            raise HTTPException(
                status_code=400,
                detail="Seminar day-based mode requires at least 7 periods per week."
            )

    total_hours = (
        subject_data.theory_hours_per_week
        + subject_data.lab_hours_per_week
        + subject_data.tutorial_hours_per_week
        + subject_data.project_hours_per_week
        + subject_data.report_hours_per_week
        + subject_data.self_study_hours_per_week
        + subject_data.seminar_hours_per_week
    )
    if total_hours > 0:
        data['weekly_hours'] = total_hours
    
    # Auto-compute priority score (never user-editable)
    importance = data.get('importance_level', 'NORMAL') or 'NORMAL'
    pass_pct = data.get('previous_year_pass_percentage')
    data['computed_priority_score'] = Subject.calculate_priority_score(importance, pass_pct)
    
    subject = Subject(**data)
    
    if subject_data.semester_ids:
        semesters = db.query(Semester).filter(Semester.id.in_(subject_data.semester_ids)).all()
        
        # VALIDATION: Ensure all classes belong to the same semester (Academic Constraint)
        # Exception: Electives can span multiple semesters
        is_elective = subject_data.is_elective or subject_data.subject_type in [SubjectType.ELECTIVE]
        
        unique_sem_nums = {s.semester_number for s in semesters}
        if not is_elective and len(unique_sem_nums) > 1:
            raise HTTPException(
                status_code=400, 
                detail=f"Academic Rule Violation: A non-elective subject cannot be assigned to classes from different semesters (Found semesters: {unique_sem_nums}). Mark as 'Elective' to allow this."
            )
        
        subject.semesters = semesters
        
        # AUTO-ASSIGN DEPT_ID if not provided
        if not subject.dept_id and semesters:
            # Use the department of the first assigned semester
            subject.dept_id = semesters[0].dept_id
    
    # Handle elective basket
    if subject_data.elective_basket_id:
        basket = db.query(ElectiveBasket).filter(
            ElectiveBasket.id == subject_data.elective_basket_id
        ).first()
        if basket:
            subject.elective_basket_id = basket.id
            subject.is_elective = True
    
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.put("/{subject_id}", response_model=SubjectResponse)
def update_subject(subject_id: int, subject_data: SubjectUpdate, db: Session = Depends(get_db)):
    """Update a subject and its semester assignments."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    update_data = subject_data.model_dump(exclude_unset=True)
    
    # Handle semester mapping update if provided
    if 'semester_ids' in update_data:
        sem_ids = update_data.pop('semester_ids')
        if sem_ids is not None:
            semesters = db.query(Semester).filter(Semester.id.in_(sem_ids)).all()
            
            # Check if it is (or becoming) an elective
            current_is_elective = update_data.get('is_elective', subject.is_elective)
            current_type = update_data.get('subject_type', subject.subject_type)
            is_elective = current_is_elective or current_type == SubjectType.ELECTIVE
            
            # VALIDATION: Ensure all classes belong to the same semester
            unique_sem_nums = {s.semester_number for s in semesters}
            if not is_elective and len(unique_sem_nums) > 1:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Academic Rule Violation: A non-elective subject cannot be assigned to classes from different semesters (Found semesters: {unique_sem_nums}). Mark as 'Elective' to allow this."
                )
            
            subject.semesters = semesters

            # AUTO-ASSIGN DEPT_ID if it was missing and we now have semesters
            if not subject.dept_id and semesters:
                subject.dept_id = semesters[0].dept_id
    
    # Handle elective basket
    if 'elective_basket_id' in update_data:
        basket_id = update_data.pop('elective_basket_id')
        subject.elective_basket_id = basket_id
        if basket_id:
            subject.is_elective = True
    
    # Update remaining fields
    for key, value in update_data.items():
        setattr(subject, key, value)
    
    # Recalculate legacy weekly_hours
    def _validate_block(component_name: str, hours: int, block_size: int):
        if hours <= 0:
            return
        if block_size == 2 and hours % 2 != 0:
            raise HTTPException(
                status_code=400,
                detail=f"{component_name} hours must be even when block size is 2 (continuous)."
            )

    _validate_block("Project", subject.project_hours_per_week or 0, subject.project_block_size or 1)
    _validate_block("Report", subject.report_hours_per_week or 0, subject.report_block_size or 1)
    _validate_block("Seminar", subject.seminar_hours_per_week or 0, subject.seminar_block_size or 2)

    if getattr(subject, "seminar_day_based", False) and (subject.seminar_hours_per_week or 0) > 0:
        if (subject.seminar_hours_per_week or 0) < 7:
            raise HTTPException(
                status_code=400,
                detail="Seminar day-based mode requires at least 7 periods per week."
            )

    total_hours = (
        (subject.theory_hours_per_week or 0)
        + (subject.lab_hours_per_week or 0)
        + (subject.tutorial_hours_per_week or 0)
        + (subject.project_hours_per_week or 0)
        + (subject.report_hours_per_week or 0)
        + (subject.self_study_hours_per_week or 0)
        + (subject.seminar_hours_per_week or 0)
    )
    if total_hours > 0:
        subject.weekly_hours = total_hours
    
    # Auto-compute priority score
    importance = getattr(subject, 'importance_level', 'NORMAL') or 'NORMAL'
    pass_pct = getattr(subject, 'previous_year_pass_percentage', None)
    subject.computed_priority_score = Subject.calculate_priority_score(importance, pass_pct)
    
    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    """
    Delete a subject with COMPLETE CLEANUP.
    
    According to academic rules, deleting a subject MUST:
    1. Remove all allocations for this subject
    2. Remove all class-subject-teacher mappings
    3. Remove all component assignments
    4. Remove from elective baskets (if applicable)
    5. Recalculate available hours (happens at validation)
    """
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    subject_name = subject.name
    
    # 1. Delete all allocations for this subject
    deleted_allocations = db.query(Allocation).filter(
        Allocation.subject_id == subject_id
    ).delete(synchronize_session=False)
    
    # 2. Delete all class-subject-teacher mappings
    deleted_assignments = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.subject_id == subject_id
    ).delete(synchronize_session=False)
    
    # 3. Delete all component assignments
    deleted_components = db.query(SubjectComponentAssignment).filter(
        SubjectComponentAssignment.subject_id == subject_id
    ).delete(synchronize_session=False)
    
    # 4. Clear semester associations (handled by ORM cascade)
    subject.semesters = []
    
    # 5. Delete the subject itself
    db.delete(subject)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to delete subject: {str(e)}"
        )
    
    print(f"[Subject Deleted] '{subject_name}' (ID: {subject_id})")
    print(f"  - Removed {deleted_allocations} allocations")
    print(f"  - Removed {deleted_assignments} teacher assignments")
    print(f"  - Removed {deleted_components} component assignments")
    
    return None


# ============================================================================
# ADDITIONAL ENDPOINTS FOR COMPONENT-BASED SUBJECTS
# ============================================================================

@router.get("/{subject_id}/components")
def get_subject_components(subject_id: int, db: Session = Depends(get_db)):
    """Get detailed component breakdown for a subject."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    components = []
    
    if subject.theory_hours_per_week > 0:
        components.append({
            "type": "theory",
            "hours_per_week": subject.theory_hours_per_week,
            "description": f"{subject.theory_hours_per_week} theory periods/week"
        })
    
    if subject.lab_hours_per_week > 0:
        blocks = subject.lab_hours_per_week // 2
        components.append({
            "type": "lab",
            "hours_per_week": subject.lab_hours_per_week,
            "blocks_per_week": blocks,
            "description": f"{blocks} lab block(s)/week ({subject.lab_hours_per_week} periods)"
        })
    
    if subject.tutorial_hours_per_week > 0:
        components.append({
            "type": "tutorial",
            "hours_per_week": subject.tutorial_hours_per_week,
            "description": f"{subject.tutorial_hours_per_week} tutorial period(s)/week"
        })

    if getattr(subject, "project_hours_per_week", 0) > 0:
        components.append({
            "type": "project",
            "hours_per_week": subject.project_hours_per_week,
            "block_size": getattr(subject, "project_block_size", 1),
            "description": f"{subject.project_hours_per_week} project period(s)/week"
        })

    if getattr(subject, "report_hours_per_week", 0) > 0:
        components.append({
            "type": "report",
            "hours_per_week": subject.report_hours_per_week,
            "block_size": getattr(subject, "report_block_size", 1),
            "description": f"{subject.report_hours_per_week} report period(s)/week"
        })

    if getattr(subject, "self_study_hours_per_week", 0) > 0:
        components.append({
            "type": "self_study",
            "hours_per_week": subject.self_study_hours_per_week,
            "description": f"{subject.self_study_hours_per_week} self-study period(s)/week"
        })
    
    if getattr(subject, "seminar_hours_per_week", 0) > 0:
        components.append({
            "type": "seminar",
            "hours_per_week": subject.seminar_hours_per_week,
            "block_size": getattr(subject, "seminar_block_size", 2),
            "day_based": getattr(subject, "seminar_day_based", False),
            "description": f"{subject.seminar_hours_per_week} seminar period(s)/week"
        })
    
    return {
        "subject_id": subject.id,
        "subject_name": subject.name,
        "subject_code": subject.code,
        "is_elective": subject.is_elective,
        "total_hours_per_week": subject.total_weekly_hours,
        "components": components
    }


@router.put("/{subject_id}/components")
def update_subject_components(
    subject_id: int, 
    theory_hours: int = 0,
    lab_hours: int = 0,
    tutorial_hours: int = 0,
    db: Session = Depends(get_db)
):
    """Update component hours for a subject."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    subject.theory_hours_per_week = theory_hours
    subject.lab_hours_per_week = lab_hours
    subject.tutorial_hours_per_week = tutorial_hours
    subject.weekly_hours = theory_hours + lab_hours + tutorial_hours
    
    db.commit()
    db.refresh(subject)
    
    return {
        "message": "Components updated",
        "subject_id": subject.id,
        "theory_hours": subject.theory_hours_per_week,
        "lab_hours": subject.lab_hours_per_week,
        "tutorial_hours": subject.tutorial_hours_per_week,
        "total_hours": subject.weekly_hours
    }
