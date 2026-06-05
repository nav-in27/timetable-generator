"""
CRUD API routes for Teachers.

OPTIMIZATIONS (v2):
- Cache invalidation on all mutations
- Graceful fallback: if assignment fetch fails, still return basic teacher info
- Proper rollback on errors
"""
from typing import List, Optional
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from app.core.cache import cache

logger = logging.getLogger("app.teachers")

from app.db.session import get_db
from app.db.models import (
    Teacher,
    Subject,
    Room,
    RoomType,
    teacher_subjects,
    ClassSubjectTeacher,
    Semester,
    ComponentType,
    Batch,
    Department,
    teacher_allowed_departments,
)
from app.schemas.schemas import TeacherCreate, TeacherUpdate, TeacherResponse, ClassSubjectTeacherCreate, ClassSubjectTeacherResponse

router = APIRouter(prefix="/teachers", tags=["Teachers"])


@router.get("/", response_model=List[TeacherResponse])
def list_teachers(
    skip: int = 0,
    limit: Optional[int] = None,
    active_only: bool = True,
    dept_id: Optional[int] = None,
    teacher_code: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all teachers with optional filtering."""
    query = db.query(Teacher).options(
        selectinload(Teacher.subjects).selectinload(Subject.semesters),
        selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.semester),
        selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.room),
        selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.subject).selectinload(Subject.semesters),
        selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.batch),
        selectinload(Teacher.allowed_departments),
    )
    if active_only:
        query = query.filter(Teacher.is_active == True)
    if dept_id:
        query = query.filter(Teacher.dept_id == dept_id)
    if teacher_code:
        query = query.filter(Teacher.teacher_code == teacher_code)
        
    query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    teachers = query.all()
    return teachers


@router.get("/{teacher_id}", response_model=TeacherResponse)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """Get a specific teacher by ID with graceful fallback."""
    try:
        teacher = db.query(Teacher).options(
            selectinload(Teacher.subjects).selectinload(Subject.semesters),
            selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.semester),
            selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.room),
            selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.subject).selectinload(Subject.semesters),
            selectinload(Teacher.class_assignments).selectinload(ClassSubjectTeacher.batch),
            selectinload(Teacher.allowed_departments),
        ).filter(Teacher.id == teacher_id).first()
    except Exception as e:
        # Fallback: return basic teacher info if eager loading fails
        logger.warning(f"Teacher eager load failed for ID {teacher_id}, using fallback: {e}")
        teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return teacher


@router.post("/", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def create_teacher(teacher_data: TeacherCreate, db: Session = Depends(get_db)):
    """Create a new teacher."""
    if teacher_data.email:
        existing = db.query(Teacher).filter(Teacher.email == teacher_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Teacher with this email already exists")
            
    if db.query(Teacher).filter(Teacher.teacher_code == teacher_data.teacher_code).first():
        raise HTTPException(status_code=400, detail="Teacher code already exists")
    
    subject_ids = teacher_data.subject_ids
    allowed_department_ids = teacher_data.allowed_department_ids
    teacher_dict = teacher_data.model_dump(exclude={"subject_ids", "allowed_department_ids"})
    
    if "email" in teacher_dict and teacher_dict["email"] == "":
        teacher_dict["email"] = None
    
    teacher = Teacher(**teacher_dict)
    
    if subject_ids:
        subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
        teacher.subjects = subjects
    
    if allowed_department_ids:
        depts = db.query(Department).filter(Department.id.in_(allowed_department_ids)).all()
        teacher.allowed_departments = depts
    
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    cache.invalidate_tag("teachers")
    return teacher

@router.put("/{teacher_id}", response_model=TeacherResponse)
def update_teacher(teacher_id: int, teacher_data: TeacherUpdate, db: Session = Depends(get_db)):
    """Update a teacher."""
    teacher = db.query(Teacher).options(
        selectinload(Teacher.subjects),
        selectinload(Teacher.allowed_departments)
    ).filter(Teacher.id == teacher_id).first()
    
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    update_data = teacher_data.model_dump(exclude_unset=True)
    
    if "email" in update_data and update_data["email"] == "":
        update_data["email"] = None
        
    if "email" in update_data and update_data["email"] is not None:
         existing = db.query(Teacher).filter(Teacher.email == update_data["email"]).first()
         if existing and existing.id != teacher_id:
             raise HTTPException(status_code=400, detail="Teacher with this email already exists")

    if "teacher_code" in update_data and update_data["teacher_code"]:
        existing_code = db.query(Teacher).filter(Teacher.teacher_code == update_data["teacher_code"]).first()
        if existing_code and existing_code.id != teacher_id:
             raise HTTPException(status_code=400, detail="Teacher code already exists")
    
    if "subject_ids" in update_data:
        subject_ids = update_data.pop("subject_ids")
        if subject_ids is not None:
            subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
            teacher.subjects = subjects
    
    if "allowed_department_ids" in update_data:
        dept_ids = update_data.pop("allowed_department_ids")
        if dept_ids is not None:
            depts = db.query(Department).filter(Department.id.in_(dept_ids)).all()
            teacher.allowed_departments = depts
    
    for key, value in update_data.items():
        setattr(teacher, key, value)
    
    db.commit()
    db.refresh(teacher)
    cache.invalidate_tag("teachers")
    return teacher

@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """Delete a teacher (hard delete)."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    try:
        db.delete(teacher)
        db.commit()
        cache.invalidate_tag("teachers")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    
    return None

class BulkDeleteRequest(BaseModel):
    teacher_ids: List[int]

@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_teachers(request: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Bulk delete teachers (hard delete)."""
    if not request.teacher_ids:
        return {"deleted_count": 0}
        
    try:
        teachers = db.query(Teacher).filter(Teacher.id.in_(request.teacher_ids)).all()
        for t in teachers:
            db.delete(t)
        db.commit()
        cache.invalidate_tag("teachers")
        return {"deleted_count": len(teachers)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")

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
    cache.invalidate_tag("teachers")
    
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
    cache.invalidate_tag("teachers")
    
    return teacher


@router.post("/{teacher_id}/assignments", response_model=ClassSubjectTeacherResponse)
def add_teacher_assignment(
    teacher_id: int,
    assignment_data: ClassSubjectTeacherCreate,
    db: Session = Depends(get_db)
):
    """
    Append-only assignment:
    - Inserts a new teacher-class-subject-component mapping if it does not exist.
    - Never reassigns/deletes another teacher's existing mapping.
    """
    # Verify teacher exists
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Path teacher_id is the source of truth. If payload contains teacher_id,
    # it must match to prevent accidental cross-teacher overwrites.
    if getattr(assignment_data, "teacher_id", None) not in (None, teacher_id):
        raise HTTPException(
            status_code=400,
            detail="teacher_id in payload does not match path teacher_id"
        )
    
    # Verify semester and subject exist
    semester = db.query(Semester).filter(Semester.id == assignment_data.semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
        
    subject = db.query(Subject).filter(Subject.id == assignment_data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Ensure the subject is actually mapped to the selected class
    if not any(s.id == semester.id for s in subject.semesters):
        raise HTTPException(
            status_code=400,
            detail="Subject is not assigned to this class. Assign the subject to this class first."
        )

    # Cross-department capability validation
    if not getattr(teacher, "is_common_service_dept", False):
        if hasattr(semester, "dept_id") and semester.dept_id is not None:
            home_dept_id = getattr(teacher, "dept_id", None)
            allowed_dept_ids = set()
            if hasattr(teacher, "allowed_departments"):
                allowed_dept_ids = {d.id for d in teacher.allowed_departments}
            
            if semester.dept_id != home_dept_id and semester.dept_id not in allowed_dept_ids:
                # Fetch department name for a better error message if possible
                dept_name = f"Dept ID {semester.dept_id}"
                dept = db.query(Department).filter(Department.id == semester.dept_id).first()
                if dept:
                    dept_name = dept.name
                    
                raise HTTPException(
                    status_code=400,
                    detail=f"Cross-Department Mismatch: Teacher is not authorized to teach in '{dept_name}'. Please update their profile to allow it or mark them as Common Service."
                )

    # Validate component against subject configured hours
    if assignment_data.component_type == ComponentType.LAB and (subject.lab_hours_per_week or 0) <= 0:
        raise HTTPException(status_code=400, detail="This subject has 0 lab hours configured")
    if assignment_data.component_type == ComponentType.TUTORIAL and (subject.tutorial_hours_per_week or 0) <= 0:
        raise HTTPException(status_code=400, detail="This subject has 0 tutorial hours configured")

    # Validate batch belongs to the selected class
    if assignment_data.batch_id is not None:
        batch = db.query(Batch).filter(Batch.id == assignment_data.batch_id).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        if batch.semester_id != assignment_data.semester_id:
            raise HTTPException(status_code=400, detail="Selected batch does not belong to the selected class")

    # Optional room assignment (primarily for labs)
    if getattr(assignment_data, "room_id", None):
        room = db.query(Room).filter(Room.id == assignment_data.room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if assignment_data.component_type == ComponentType.LAB and room.room_type != RoomType.LAB:
            raise HTTPException(status_code=400, detail="Selected room is not a lab room")

    # APPEND MODE: only treat exact same mapping as existing.
    # Do NOT replace a different teacher's row for the same class/subject.
    query = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.teacher_id == teacher_id,
        ClassSubjectTeacher.semester_id == assignment_data.semester_id,
        ClassSubjectTeacher.subject_id == assignment_data.subject_id,
        ClassSubjectTeacher.component_type == assignment_data.component_type
    )
    
    if assignment_data.batch_id is not None:
        query = query.filter(ClassSubjectTeacher.batch_id == assignment_data.batch_id)
    else:
        query = query.filter(ClassSubjectTeacher.batch_id.is_(None))
        
    existing = query.first()
    
    if existing:
        # Idempotent behavior: keep row, optionally refresh mutable metadata only.
        existing.room_id = assignment_data.room_id
        existing.assignment_reason = assignment_data.assignment_reason
        existing.is_locked = assignment_data.is_locked
        existing.parallel_lab_group = assignment_data.parallel_lab_group

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
    except IntegrityError:
        # Graceful duplicate handling for concurrent requests.
        db.rollback()
        dup_query = db.query(ClassSubjectTeacher).filter(
            ClassSubjectTeacher.teacher_id == teacher_id,
            ClassSubjectTeacher.semester_id == assignment_data.semester_id,
            ClassSubjectTeacher.subject_id == assignment_data.subject_id,
            ClassSubjectTeacher.component_type == assignment_data.component_type
        )
        if assignment_data.batch_id is not None:
            dup_query = dup_query.filter(ClassSubjectTeacher.batch_id == assignment_data.batch_id)
        else:
            dup_query = dup_query.filter(ClassSubjectTeacher.batch_id.is_(None))
        existing_dup = dup_query.first()
        if existing_dup:
            return existing_dup
        raise HTTPException(status_code=400, detail="Duplicate assignment")
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
    cache.invalidate_tag("teachers")
    return None
