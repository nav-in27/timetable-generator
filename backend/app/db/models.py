"""
Database models for the University Timetable Generator.
Implements the CORRECT ACADEMIC DATA MODEL:

A SUBJECT (including ELECTIVE) may have MULTIPLE COMPONENTS:
SUBJECT
 ├── THEORY component (weekly hours)
 ├── LAB component (weekly blocks)
 └── TUTORIAL component (optional)

ALL components share:
- Same course code
- Same subject name
- Same elective basket (if elective)
"""
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import (
    String, Integer, Float, Boolean, ForeignKey, DateTime, Date,
    Enum as SQLEnum, UniqueConstraint, Table, Column, CheckConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base


# ============================================================================
# ENUMS
# ============================================================================

class RoomType(str, enum.Enum):
    """Types of rooms available."""
    LECTURE = "lecture"
    LAB = "lab"
    SEMINAR = "seminar"


class ComponentType(str, enum.Enum):
    """Types of subject components (NOT subject types!)."""
    THEORY = "theory"
    LAB = "lab"
    TUTORIAL = "tutorial"
    SELF_STUDY = "self_study"


class SubjectType(str, enum.Enum):
    """
    Subject classification for scheduling purposes.
    NOTE: This determines HOW the subject is scheduled, not its components.
    """
    REGULAR = "regular"      # Normal subject (theory only or with components)
    ELECTIVE = "elective"    # Elective subject (needs cross-class sync)
    # Legacy compatibility
    THEORY = "theory"
    LAB = "lab"
    TUTORIAL = "tutorial"


class SubstitutionStatus(str, enum.Enum):
    """Status of a substitution request."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SemesterType(str, enum.Enum):
    ODD = "ODD"
    EVEN = "EVEN"


class ImportanceLevel(str, enum.Enum):
    """Academic importance level for scheduling priority bias."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


# ============================================================================
# ASSOCIATION TABLES
# ============================================================================

# Many-to-Many: Teachers <-> Subjects (with effectiveness score)
teacher_subjects = Table(
    "teacher_subjects",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", Integer, ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
    Column("effectiveness_score", Float, default=0.8),  # 0.0 to 1.0
)

# Many-to-Many: Subjects <-> Semesters (Classes)
subject_semesters = Table(
    "subject_semesters",
    Base.metadata,
    Column("subject_id", Integer, ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
    Column("semester_id", Integer, ForeignKey("semesters.id", ondelete="CASCADE"), primary_key=True),
)

# Association table for elective baskets and participating semesters
elective_basket_semesters = Table(
    "elective_basket_semesters",
    Base.metadata,
    Column("basket_id", Integer, ForeignKey("elective_baskets.id", ondelete="CASCADE"), primary_key=True),
    Column("semester_id", Integer, ForeignKey("semesters.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-Many: Rooms <-> Departments (shared labs across departments)
room_departments = Table(
    "room_departments",
    Base.metadata,
    Column("room_id", Integer, ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
    Column("dept_id", Integer, ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-Many: Teachers <-> Departments (cross-department teaching permissions)
# This tracks which departments a teacher is ALLOWED to teach in,
# beyond their home department (Teacher.dept_id).
teacher_allowed_departments = Table(
    "teacher_allowed_departments",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    Column("dept_id", Integer, ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)


# ============================================================================
# MODELS
# ============================================================================

class Department(Base):
    """Department entity."""
    __tablename__ = "departments"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DepartmentRuleToggle(Base):
    """Department-specific rule toggle configuration (soft rules by default)."""
    __tablename__ = "department_rule_toggles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dept_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"),
        unique=True
    )

    # Rule toggles (default OFF)
    lab_continuity_strict: Mapped[bool] = mapped_column(Boolean, default=False)
    teacher_gap_preference: Mapped[bool] = mapped_column(Boolean, default=False)
    max_consecutive_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_consecutive_limit: Mapped[int] = mapped_column(Integer, default=3)

    # Soft by default; can be marked hard explicitly
    lab_continuity_is_hard: Mapped[bool] = mapped_column(Boolean, default=False)
    teacher_gap_is_hard: Mapped[bool] = mapped_column(Boolean, default=False)
    max_consecutive_is_hard: Mapped[bool] = mapped_column(Boolean, default=False)

    department: Mapped["Department"] = relationship()

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Room(Base):
    """Physical room/classroom entity."""
    __tablename__ = "rooms"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    capacity: Mapped[int] = mapped_column(Integer)
    room_type: Mapped[RoomType] = mapped_column(SQLEnum(RoomType), default=RoomType.LECTURE)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Scalability: Future support for multiple departments/colleges
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Section-wise room assignment (optional)
    # When assigned_year + assigned_section + is_default_classroom are set,
    # this room becomes the DEFAULT classroom for that section's theory classes.
    # If not set, the room behaves as a shared resource (backward compatible).
    assigned_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assigned_section: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_default_classroom: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="room")
    departments: Mapped[List["Department"]] = relationship(
        secondary=room_departments, lazy="joined"
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Teacher(Base):
    """Teacher/Faculty entity."""
    __tablename__ = "teachers"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[Optional[str]] = mapped_column(String(200), unique=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # New mandatory unique code for identification
    teacher_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=True, index=True) # Populated via script
    
    # Constraints & scoring
    max_hours_per_week: Mapped[int] = mapped_column(Integer, default=20)
    max_consecutive_classes: Mapped[int] = mapped_column(Integer, default=3)
    experience_years: Mapped[int] = mapped_column(Integer, default=1)
    experience_score: Mapped[float] = mapped_column(Float, default=0.5)  # 0.0 to 1.0
    
    # Availability: "0,1,2,3,4" for Monday-Friday
    available_days: Mapped[str] = mapped_column(String(50), default="0,1,2,3,4")
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Scalability
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Cross-Department Teaching
    # When True, this teacher can teach in ALL departments (e.g. Maths, English, Placement)
    is_common_service_dept: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    subjects: Mapped[List["Subject"]] = relationship(
        secondary=teacher_subjects, back_populates="teachers"
    )
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="teacher")
    absences: Mapped[List["TeacherAbsence"]] = relationship(back_populates="teacher")
    class_assignments: Mapped[List["ClassSubjectTeacher"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )
    # Cross-department teaching permissions (beyond home dept_id)
    allowed_departments: Mapped[List["Department"]] = relationship(
        secondary=teacher_allowed_departments
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Subject(Base):
    """
    Subject/Course entity with COMPONENT-BASED STRUCTURE.
    
    CORRECT ACADEMIC MODEL:
    A single course code (e.g., EL402) can have:
    - Theory hours: 3 hours/week
    - Lab hours: 2 hours/week (1 lab block)
    - Tutorial hours: 1 hour/week (optional)
    
    All components are scheduled separately but tracked together.
    """
    __tablename__ = "subjects"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    
    # COMPONENT-BASED HOURS MODEL
    # Each subject can have multiple component types
    theory_hours_per_week: Mapped[int] = mapped_column(Integer, default=3)  # Theory periods
    lab_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)     # Lab periods (2 per block)
    tutorial_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)  # Tutorial periods

    # EXTENDED ACADEMIC COMPONENTS (Optional, backward-compatible)
    # These are treated as timetable-visible components when hours > 0.
    project_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)
    project_block_size: Mapped[int] = mapped_column(Integer, default=1)  # 1 or 2

    report_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)
    report_block_size: Mapped[int] = mapped_column(Integer, default=1)  # 1 or 2

    self_study_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)  # Single period sessions

    seminar_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)
    seminar_block_size: Mapped[int] = mapped_column(Integer, default=2)  # 1 or 2 (or 7 for day-based)
    seminar_day_based: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Total weekly hours (computed from components)
    @property
    def total_weekly_hours(self) -> int:
        return (
            self.theory_hours_per_week
            + self.lab_hours_per_week
            + self.tutorial_hours_per_week
            + (self.project_hours_per_week or 0)
            + (self.report_hours_per_week or 0)
            + (self.self_study_hours_per_week or 0)
            + (self.seminar_hours_per_week or 0)
        )
    
    # Legacy compatibility field (deprecated, but kept for DB compatibility)
    weekly_hours: Mapped[int] = mapped_column(Integer, default=3)
    subject_type: Mapped[SubjectType] = mapped_column(SQLEnum(SubjectType), default=SubjectType.REGULAR)
    consecutive_slots: Mapped[int] = mapped_column(Integer, default=1)  # Deprecated
    
    # ELECTIVE FLAG (Critical for scheduling)
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Elective Basket reference (if this is an elective)
    elective_basket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("elective_baskets.id", ondelete="SET NULL"), 
        nullable=True, index=True
    )
    
    # Semester mapping (e.g. 3 for 3rd semester)
    semester: Mapped[int] = mapped_column(Integer, default=1)
    
    # Year (1, 2, 3, 4) - Explicit field for filtering
    year: Mapped[int] = mapped_column(Integer, default=1)
    
    # ACADEMIC IMPORTANCE & PRIORITY (Optional, backward-compatible)
    # Used as soft scheduling weight for morning slot preference
    importance_level: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, default="NORMAL"
    )
    previous_year_pass_percentage: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    computed_priority_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0
    )
    
    @staticmethod
    def calculate_priority_score(
        importance_level: str = "NORMAL",
        pass_percentage: int = None
    ) -> int:
        """Compute scheduling priority weight.
        
        This is a SOFT WEIGHT, not a hard constraint.
        Higher score = prefer earlier (morning) slots.
        """
        if pass_percentage is not None:
            if pass_percentage < 50:
                return 3
            elif pass_percentage < 70:
                return 2
            elif pass_percentage < 85:
                return 1
            else:
                return 0
        return 0
    
    # Scalability
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    teachers: Mapped[List["Teacher"]] = relationship(
        secondary=teacher_subjects, back_populates="subjects"
    )
    semesters: Mapped[List["Semester"]] = relationship(
        secondary=subject_semesters, back_populates="subjects"
    )
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="subject")
    elective_basket: Mapped[Optional["ElectiveBasket"]] = relationship(back_populates="subjects")
    component_assignments: Mapped[List["SubjectComponentAssignment"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_lab_blocks_per_week(self) -> int:
        """Lab blocks = lab_hours / 2 (each block is 2 periods)."""
        return self.lab_hours_per_week // 2


class SubjectComponentAssignment(Base):
    """
    Tracks teacher/room assignments PER COMPONENT of a subject.
    
    This allows different teachers for theory/lab/tutorial of the same subject.
    E.g., Prof. A teaches CS301 Theory, Lab Assistant B runs CS301 Lab.
    """
    __tablename__ = "subject_component_assignments"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"))
    component_type: Mapped[ComponentType] = mapped_column(SQLEnum(ComponentType))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    
    # Lock flag - once assigned, cannot be auto-changed
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    subject: Mapped["Subject"] = relationship(back_populates="component_assignments")
    
    # Unique constraint: One teacher per (subject, semester, component_type)
    __table_args__ = (
        UniqueConstraint("subject_id", "semester_id", "component_type", 
                         name="uq_subject_semester_component"),
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Semester(Base):
    """Class/Semester entity (e.g., 'CSE 3rd Sem Section A')."""
    __tablename__ = "semesters"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))  # e.g., "3rd Semester - Section A"
    code: Mapped[str] = mapped_column(String(20), unique=True)  # e.g., "CS3A"
    
    year: Mapped[int] = mapped_column(Integer, default=2)  # 1st, 2nd, 3rd, 4th year
    semester_number: Mapped[int] = mapped_column(Integer, default=3)  # 1-8
    section: Mapped[str] = mapped_column(String(10), default="A")
    student_count: Mapped[int] = mapped_column(Integer, default=60)
    
    # Scalability
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    subjects: Mapped[List["Subject"]] = relationship(
        secondary=subject_semesters, back_populates="semesters"
    )
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="semester")
    batches: Mapped[List["Batch"]] = relationship(back_populates="semester", cascade="all, delete-orphan")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Batch(Base):
    """
    Represents a student batch within a semester (e.g., "Batch A", "Batch B").
    Used for practicals (labs) where the class is split into smaller groups.
    """
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50))  # e.g., "A", "B", "1"
    
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"))
    
    # Relationships
    semester: Mapped["Semester"] = relationship(back_populates="batches")
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="batch")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Allocation(Base):
    """
    Timetable allocation entity.
    Represents a single slot in the timetable: Teacher teaches Subject to Semester in Room at Day/Slot.
    """
    __tablename__ = "allocations"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign keys
    teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True, nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True, nullable=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True, nullable=True)
    
    # Time slot info
    day: Mapped[int] = mapped_column(Integer, index=True)  # 0=Monday, 4=Friday
    slot: Mapped[int] = mapped_column(Integer)  # 0-6 (7 periods)
    
    # Component type for this allocation
    component_type: Mapped[ComponentType] = mapped_column(
        SQLEnum(ComponentType), default=ComponentType.THEORY
    )

    # Extended academic component label (optional).
    # When set, this provides the "real" academic component type (project/report/self_study/seminar/etc)
    # while `component_type` continues to drive scheduling behavior (theory/lab/tutorial).
    academic_component: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # For multi-slot sessions (labs)
    is_lab_continuation: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Elective tracking
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False)
    elective_basket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("elective_baskets.id", ondelete="SET NULL"), nullable=True
    )
    
    batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("batches.id", ondelete="SET NULL"), nullable=True
    )
    
    # Relationships
    teacher: Mapped["Teacher"] = relationship(back_populates="allocations")
    subject: Mapped["Subject"] = relationship(back_populates="allocations")
    semester: Mapped["Semester"] = relationship(back_populates="allocations")
    room: Mapped["Room"] = relationship(back_populates="allocations")
    batch: Mapped[Optional["Batch"]] = relationship(back_populates="allocations")
    substitutions: Mapped[List["Substitution"]] = relationship(back_populates="allocation")
    
    # Unique constraint: One class per semester per day/slot (unless split by batches)
    # MODIFIED: Now we allow multiple allocations if they have different batch_ids (or if one is null and another is batch?)
    # Actually, if batch_id is NULL, it means the WHOLE class.
    # If batch_id is SET, it means a PART of the class.
    # Constraint: (semester_id, day, slot, batch_id) should be unique.
    # BUT: We also need to prevent "Whole Class" + "Batch A" overlap.
    # This is complex to enforce purely via SQL UniqueConstraint if NULLs are involved.
    # For now, we relax the strict SQL unique constraint and enforce logic in Generator.
    # However, to prevent duplicates:
    # We'll use a functional index or just rely on application logic + (teacher, day, slot) uniqueness.
    
    __table_args__ = (
        # We REMOVE the strict (semester, day, slot) unique constraint because parallel batches share this.
        # Instead, we rely on (teacher, day, slot) and (room, day, slot) uniqueness which are implicit via logic
        # OR we add batch_id to uniqueness.
        # UniqueConstraint("semester_id", "day", "slot", "batch_id", name="uq_semester_day_slot_batch"),
        Index('ix_allocations_sem_day_slot', 'semester_id', 'day', 'slot'),
        Index('ix_allocations_teacher_day_slot', 'teacher_id', 'day', 'slot'),
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TeacherAbsence(Base):
    """Records teacher absences for substitution triggering."""
    __tablename__ = "teacher_absences"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    absence_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Full day or specific slots
    is_full_day: Mapped[bool] = mapped_column(Boolean, default=True)
    absent_slots: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g., "0,1,2"
    
    # Relationships
    teacher: Mapped["Teacher"] = relationship(back_populates="absences")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Substitution(Base):
    """
    Substitution record.
    Tracks when a substitute teacher is assigned to cover for an absent teacher.
    """
    __tablename__ = "substitutions"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    allocation_id: Mapped[int] = mapped_column(ForeignKey("allocations.id", ondelete="CASCADE"))
    original_teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    substitute_teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    
    substitution_date: Mapped[date] = mapped_column(Date)
    status: Mapped[SubstitutionStatus] = mapped_column(
        SQLEnum(SubstitutionStatus), default=SubstitutionStatus.PENDING
    )
    
    # Scoring info (for transparency)
    substitute_score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relationships
    allocation: Mapped["Allocation"] = relationship(back_populates="substitutions")
    original_teacher: Mapped["Teacher"] = relationship(foreign_keys=[original_teacher_id])
    substitute_teacher: Mapped["Teacher"] = relationship(foreign_keys=[substitute_teacher_id])
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# FIXED TEACHER ASSIGNMENT MODEL (Issue 1 Fix)
# ============================================================================

class ClassSubjectTeacher(Base):
    """
    Fixed mapping of teacher -> (semester, subject, component, optional batch).

    APPEND MODE:
    - Multiple teachers can be mapped to the same (semester, subject, component)
      without overwriting existing rows.
    - Exact duplicate mappings are blocked.
    """
    __tablename__ = "class_subject_teachers"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    # Optional preferred/assigned room (primarily for lab components).
    # When set, the generator will prefer this room for scheduling.
    room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )
    component_type: Mapped[ComponentType] = mapped_column(
        SQLEnum(ComponentType), default=ComponentType.THEORY
    )
    
    # Batch support
    batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), nullable=True
    )
    
    # Assignment metadata
    assignment_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Parallel multi-subject lab group.
    # When multiple CST lab entries for the SAME semester share this group string,
    # they are co-scheduled in the same time slot with different teachers/rooms/batches.
    # Example: "IT2A-parallel-1" links DBMS Lab + OS Lab for IT 2nd Year Section A.
    parallel_lab_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Lock flag - once locked, cannot be changed
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    teacher: Mapped["Teacher"] = relationship(back_populates="class_assignments")
    semester: Mapped["Semester"] = relationship()
    subject: Mapped["Subject"] = relationship()
    room: Mapped[Optional["Room"]] = relationship()
    batch: Mapped[Optional["Batch"]] = relationship()
    
    # Prevent exact duplicate mapping rows.
    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "semester_id",
            "subject_id",
            "component_type",
            "batch_id",
            name="uq_cst_teacher_sem_subj_comp_batch",
        ),
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)




# ============================================================================
# ELECTIVE BASKET MODEL (Correct Academic Structure)
# ============================================================================

class ElectiveBasket(Base):
    """
    Represents an elective basket for a semester.
    
    CRITICAL ACADEMIC RULES:
    1. All subjects in the basket are ALTERNATIVES (student picks one)
    2. All subjects must be scheduled at the SAME COMMON SLOTS
    3. Theory components: Same slot across ALL classes of that semester
    4. Lab components: Same lab block slots across ALL classes
    
    Example:
        Basket: "Open Elective 1 - 5th Semester"
        Subjects: [AI, ML, Cloud Computing]
        All 3 must have theory at the same time (e.g., Mon 2nd period)
        All 3 must have lab at the same time (e.g., Wed 4th-5th period)
    """
    __tablename__ = "elective_baskets"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    name: Mapped[str] = mapped_column(String(200))  # e.g., "Open Elective 1"
    code: Mapped[str] = mapped_column(String(20), unique=True)  # e.g., "OE1-S5"
    
    # Semester this basket belongs to (e.g., 5 for 5th semester)
    semester_number: Mapped[int] = mapped_column(Integer)
    
    # Year (1-4) for college-wide grouping — multiple baskets per year allowed
    year: Mapped[int] = mapped_column(Integer, default=2)
    
    # Total hours (COMMON for all subjects in basket)
    theory_hours_per_week: Mapped[int] = mapped_column(Integer, default=3)
    lab_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)  # 2 = 1 lab block
    tutorial_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)
    self_study_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)
    
    # Scheduling state
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Scheduled common slots stored as JSON-like string
    # Format: "component:day:slot,component:day:slot,..."
    # e.g., "theory:0:2,theory:2:2,lab:1:3,lab:1:4"
    scheduled_slots: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relationships
    subjects: Mapped[List["Subject"]] = relationship(back_populates="elective_basket")
    participating_semesters: Mapped[List["Semester"]] = relationship(
        secondary=elective_basket_semesters
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_lab_blocks_per_week(self) -> int:
        """Lab blocks = lab_hours / 2."""
        return self.lab_hours_per_week // 2


# ============================================================================
# LEGACY ELECTIVE GROUP MODEL (For backward compatibility)
# ============================================================================

# Association table for elective groups and participating semesters
elective_group_semesters = Table(
    "elective_group_semesters",
    Base.metadata,
    Column("elective_group_id", Integer, ForeignKey("elective_groups.id", ondelete="CASCADE"), primary_key=True),
    Column("semester_id", Integer, ForeignKey("semesters.id", ondelete="CASCADE"), primary_key=True),
)


class ElectiveGroup(Base):
    """
    DEPRECATED: Use ElectiveBasket instead.
    Kept for backward compatibility with existing data.
    """
    __tablename__ = "elective_groups"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    
    hours_per_week: Mapped[int] = mapped_column(Integer, default=3)
    elective_code: Mapped[str] = mapped_column(String(20), unique=True)
    elective_name: Mapped[str] = mapped_column(String(200))
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_slots: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    subject: Mapped["Subject"] = relationship()
    teacher: Mapped["Teacher"] = relationship()
    room: Mapped[Optional["Room"]] = relationship()
    participating_semesters: Mapped[List["Semester"]] = relationship(
        secondary=elective_group_semesters
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# FIXED SLOT MODEL (MANUAL SLOT LOCKING BEFORE GENERATION)
# ============================================================================

class FixedSlot(Base):
    """
    Pre-fixed/locked slot for manual scheduling BEFORE timetable generation.
    
    CRITICAL RULES:
    1. Fixed slots are created BEFORE generation
    2. Fixed slots are IMMUTABLE during generation
    3. Generator treats fixed slots as OCCUPIED and NEVER changes them
    4. Fixed slots are stored SEPARATELY from allocations
    5. Clearing timetable does NOT clear fixed slots (unless explicitly requested)
    
    User Flow:
    1. Admin/Teacher clicks on empty timetable cell
    2. Selects subject + teacher from filtered dropdowns
    3. Slot is validated (teacher free, subject assignment exists, not break/lunch)
    4. Slot is locked and marked with lock indicator
    5. Generator respects this locked slot during generation
    """
    __tablename__ = "fixed_slots"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Location in timetable
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(Integer)  # 0-4 = Monday-Friday
    slot: Mapped[int] = mapped_column(Integer)  # 0-6 = 7 periods
    
    # What is scheduled
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    
    # Component type (theory/lab/tutorial)
    component_type: Mapped[ComponentType] = mapped_column(
        SQLEnum(ComponentType), default=ComponentType.THEORY
    )

    # Extended academic component label (optional).
    academic_component: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # For lab blocks that span 2 periods
    is_lab_continuation: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Elective tracking
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False)
    elective_basket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("elective_baskets.id", ondelete="SET NULL"), nullable=True
    )
    
    # Lock metadata
    locked: Mapped[bool] = mapped_column(Boolean, default=True)  # Always true for fixed slots
    locked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # "admin" or teacher name
    lock_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relationships
    semester: Mapped["Semester"] = relationship()
    subject: Mapped["Subject"] = relationship()
    teacher: Mapped["Teacher"] = relationship()
    room: Mapped[Optional["Room"]] = relationship()
    
    # Unique constraint: Only one fixed slot per (semester, day, slot)
    __table_args__ = (
        UniqueConstraint("semester_id", "day", "slot", name="uq_fixed_slot_position"),
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# SEMESTER TEMPLATE MODEL
# ============================================================================

class SemesterTemplate(Base):
    """
    Template for time slots and breaks based on semester type (Odd/Even).
    """
    __tablename__ = "semester_templates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    semester_type: Mapped[SemesterType] = mapped_column(SQLEnum(SemesterType), unique=True)
    total_periods: Mapped[int] = mapped_column(Integer, default=7)
    
    # Store JSON-like string arrays: "[1, 3]" means breaks after period 2 and 4 (0-indexed 1 and 3)
    # Actually, as per requirement, "Break after period 2" -> break_slots=[1]
    break_slots: Mapped[str] = mapped_column(String(50), default="[]")
    lunch_slot: Mapped[int] = mapped_column(Integer, default=3) # e.g. after period 4, array index 3
    
    # E.g. [{"start": "09:00", "end": "09:55"}, ...] stored as string (can be parsed later if needed)
    timing_structure: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# PARALLEL LAB BASKET MODEL
# ============================================================================

class ParallelLabBasket(Base):
    """
    Groups multiple lab subjects to be scheduled in the SAME period for the SAME class.
    Behaves similar to ElectiveBasket but for regular labs running in parallel batches.
    """
    __tablename__ = "parallel_lab_baskets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    dept_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(10))
    
    # Time slot
    slot_day: Mapped[int] = mapped_column(Integer)    # 0=Monday, 4=Friday
    slot_period_start: Mapped[int] = mapped_column(Integer)
    slot_period_count: Mapped[int] = mapped_column(Integer, default=2)

    # Relationships
    basket_subjects: Mapped[List["ParallelLabBasketSubject"]] = relationship(
        back_populates="basket", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ParallelLabBasketSubject(Base):
    """
    A specific subject and batch within a Parallel Lab Basket.
    """
    __tablename__ = "parallel_lab_basket_subjects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    basket_id: Mapped[int] = mapped_column(ForeignKey("parallel_lab_baskets.id", ondelete="CASCADE"), index=True)
    
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    batch_name: Mapped[str] = mapped_column(String(50)) # e.g. B1, B2
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)

    basket: Mapped["ParallelLabBasket"] = relationship(back_populates="basket_subjects")
    subject: Mapped["Subject"] = relationship()
    teacher: Mapped["Teacher"] = relationship()
    room: Mapped[Optional["Room"]] = relationship()


# ============================================================================
# STRUCTURED COMPOSITE BASKET MODEL (SCB)
# ============================================================================

scb_departments = Table(
    "scb_departments",
    Base.metadata,
    Column("scb_id", Integer, ForeignKey("structured_composite_baskets.id", ondelete="CASCADE"), primary_key=True),
    Column("dept_id", Integer, ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)

scb_classes = Table(
    "scb_classes",
    Base.metadata,
    Column("scb_id", Integer, ForeignKey("structured_composite_baskets.id", ondelete="CASCADE"), primary_key=True),
    Column("semester_id", Integer, ForeignKey("semesters.id", ondelete="CASCADE"), primary_key=True),
)

class StructuredCompositeBasket(Base):
    """
    Structured Composite Basket (SCB) for mixed Theory + Lab multi-day handling.
    """
    __tablename__ = "structured_composite_baskets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    name: Mapped[str] = mapped_column(String(200)) # e.g. "PP Basket"
    semester: Mapped[int] = mapped_column(Integer) # e.g. 5
    
    theory_hours: Mapped[int] = mapped_column(Integer, default=3)
    lab_hours: Mapped[int] = mapped_column(Integer, default=2)
    continuous_lab_periods: Mapped[int] = mapped_column(Integer, default=2)
    
    same_slot_across_departments: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_lab_parallel: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # State
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_slots: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Relationships
    departments_involved: Mapped[List["Department"]] = relationship(secondary=scb_departments)
    selected_classes: Mapped[List["Semester"]] = relationship(secondary=scb_classes)
    linked_subjects: Mapped[List["StructuredCompositeBasketSubject"]] = relationship(
        back_populates="basket", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StructuredCompositeBasketSubject(Base):
    """
    Links subjects (like Survey, Survey Lab) to an SCB.
    """
    __tablename__ = "scb_subjects"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    basket_id: Mapped[int] = mapped_column(ForeignKey("structured_composite_baskets.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    
    # Relationships
    basket: Mapped["StructuredCompositeBasket"] = relationship(back_populates="linked_subjects")
    subject: Mapped["Subject"] = relationship()



# ============================================================================
# MODULE: ALLOCATION MODE SETTING
# ============================================================================

class SystemSetting(Base):
    """
    System-wide key-value settings.
    Used to store allocation_mode (manual / preference) and other config.
    """
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

