"""
CRUD API routes for Teachers.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.db.models import Teacher, Subject, teacher_subjects, ClassSubjectTeacher, Semester, ComponentType
from app.schemas.schemas import TeacherCreate, TeacherUpdate, TeacherResponse, ClassSubjectTeacherCreate, ClassSubjectTeacherResponse

router = APIRouter(prefix="/teachers", tags=["Teachers"])


@router.get("/", response_model=List[TeacherResponse])
def list_teachers(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """Get all teachers."""
    query = db.query(Teacher).options(
        selectinload(Teacher.subjects).selectinload(Subject.semesters),
        selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.semester),
        selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.subject).selectinload(Subject.semesters)
    )
    if active_only:
        query = query.filter(Teacher.is_active == True)
    teachers = query.offset(skip).limit(limit).all()
    return teachers


@router.get("/{teacher_id}", response_model=TeacherResponse)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """Get a specific teacher by ID."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return teacher


@router.post("/", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def create_teacher(teacher_data: TeacherCreate, db: Session = Depends(get_db)):
    """Create a new teacher."""
    # Check for duplicate email if provided
    if teacher_data.email:
        existing = db.query(Teacher).filter(Teacher.email == teacher_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Teacher with this email already exists")
    
    # Extract subject_ids
    subject_ids = teacher_data.subject_ids
    teacher_dict = teacher_data.model_dump(exclude={"subject_ids"})
    
    # Fix: Convert empty string email to None to avoid unique constraint violation
    if "email" in teacher_dict and teacher_dict["email"] == "":
        teacher_dict["email"] = None
    
    teacher = Teacher(**teacher_dict)
    
    # Add subjects
    if subject_ids:
        subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
        teacher.subjects = subjects
    
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherResponse)
def update_teacher(teacher_id: int, teacher_data: TeacherUpdate, db: Session = Depends(get_db)):
    """Update a teacher."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    update_data = teacher_data.model_dump(exclude_unset=True)
    
    # Fix: Convert empty string email to None
    if "email" in update_data and update_data["email"] == "":
        update_data["email"] = None
        
    # Check for duplicate email if changing email
    if "email" in update_data and update_data["email"] is not None:
         # simplified check: if email is being set to something that isn't None
         existing = db.query(Teacher).filter(Teacher.email == update_data["email"]).first()
         if existing and existing.id != teacher_id:
             raise HTTPException(status_code=400, detail="Teacher with this email already exists")
    
    # Handle subject_ids separately
    if "subject_ids" in update_data:
        subject_ids = update_data.pop("subject_ids")
        if subject_ids is not None:
            subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
            teacher.subjects = subjects
    
    for key, value in update_data.items():
        setattr(teacher, key, value)
    
    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """Delete a teacher (soft delete - marks as inactive)."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    # Soft delete
    try:
        teacher.is_active = False
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    
    return None


@router.post("/{teacher_id}/subjects/{subject_id}", response_model=TeacherResponse)
def add_subject_to_teacher(
    teacher_id: int,
    subject_id: int,
    effectiveness_score: float = 0.8,
    db: Session = Depends(get_db)
):
    """Add a subject to a teacher's qualifications."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Check if already assigned
    if subject in teacher.subjects:
        raise HTTPException(status_code=400, detail="Subject already assigned to teacher")
    
    # Add with effectiveness score
    stmt = teacher_subjects.insert().values(
        teacher_id=teacher_id,
        subject_id=subject_id,
        effectiveness_score=effectiveness_score
    )
    db.execute(stmt)
    db.commit()
    db.refresh(teacher)
    
    return teacher


@router.delete("/{teacher_id}/subjects/{subject_id}", response_model=TeacherResponse)
def remove_subject_from_teacher(
    teacher_id: int,
    subject_id: int,
    db: Session = Depends(get_db)
):
    """Remove a subject from a teacher's qualifications."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    if subject not in teacher.subjects:
        raise HTTPException(status_code=400, detail="Subject not assigned to teacher")
    
    teacher.subjects.remove(subject)
    db.commit()
    db.refresh(teacher)
    
    return teacher
@router.post("/{teacher_id}/assignments", response_model=ClassSubjectTeacherResponse)
def add_teacher_assignment(
    teacher_id: int,
    assignment_data: ClassSubjectTeacherCreate,
    db: Session = Depends(get_db)
):
    """Assign a teacher to a specific class (semester), subject, and component."""
    # Verify teacher exists
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    # Verify semester and subject exist
    semester = db.query(Semester).filter(Semester.id == assignment_data.semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
        
    subject = db.query(Subject).filter(Subject.id == assignment_data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Check for existing assignment (Unique constraint)
    existing = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.semester_id == assignment_data.semester_id,
        ClassSubjectTeacher.subject_id == assignment_data.subject_id,
        ClassSubjectTeacher.component_type == assignment_data.component_type
    ).first()
    
    if existing:
        # Update existing assignment
        existing.teacher_id = teacher_id
        existing.assignment_reason = assignment_data.assignment_reason
        existing.is_locked = assignment_data.is_locked
        
        # Sync qualification
        if subject not in teacher.subjects:
            teacher.subjects.append(subject)
            
        db.commit()
        db.refresh(existing)
        return existing
    
    # Create new assignment
    db_assignment = ClassSubjectTeacher(
        **assignment_data.model_dump()
    )
    db_assignment.teacher_id = teacher_id # Ensure correct teacher ID
    
    # Sync qualification
    if subject not in teacher.subjects:
        teacher.subjects.append(subject)
    
    db.add(db_assignment)
    try:
        db.commit()
        db.refresh(db_assignment)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
        
    return db_assignment


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teacher_assignment(assignment_id: int, db: Session = Depends(get_db)):
    """Remove a teacher-class-subject assignment."""
    assignment = db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    db.delete(assignment)
    db.commit()
    return None
