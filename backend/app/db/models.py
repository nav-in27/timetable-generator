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
    Enum as SQLEnum, UniqueConstraint, Table, Column, CheckConstraint
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


class Room(Base):
    """Physical room/classroom entity."""
    __tablename__ = "rooms"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    capacity: Mapped[int] = mapped_column(Integer)
    room_type: Mapped[RoomType] = mapped_column(SQLEnum(RoomType), default=RoomType.LECTURE)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Scalability: Future support for multiple departments/colleges
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="room")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Teacher(Base):
    """Teacher/Faculty entity."""
    __tablename__ = "teachers"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[Optional[str]] = mapped_column(String(200), unique=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Constraints & scoring
    max_hours_per_week: Mapped[int] = mapped_column(Integer, default=20)
    max_consecutive_classes: Mapped[int] = mapped_column(Integer, default=3)
    experience_years: Mapped[int] = mapped_column(Integer, default=1)
    experience_score: Mapped[float] = mapped_column(Float, default=0.5)  # 0.0 to 1.0
    
    # Availability: "0,1,2,3,4" for Monday-Friday
    available_days: Mapped[str] = mapped_column(String(50), default="0,1,2,3,4")
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Scalability
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    subjects: Mapped[List["Subject"]] = relationship(
        secondary=teacher_subjects, back_populates="teachers"
    )
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="teacher")
    absences: Mapped[List["TeacherAbsence"]] = relationship(back_populates="teacher")
    class_assignments: Mapped[List["ClassSubjectTeacher"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
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
    
    # Total weekly hours (computed from components)
    @property
    def total_weekly_hours(self) -> int:
        return self.theory_hours_per_week + self.lab_hours_per_week + self.tutorial_hours_per_week
    
    # Legacy compatibility field (deprecated, but kept for DB compatibility)
    weekly_hours: Mapped[int] = mapped_column(Integer, default=3)
    subject_type: Mapped[SubjectType] = mapped_column(SQLEnum(SubjectType), default=SubjectType.REGULAR)
    consecutive_slots: Mapped[int] = mapped_column(Integer, default=1)  # Deprecated
    
    # ELECTIVE FLAG (Critical for scheduling)
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Elective Basket reference (if this is an elective)
    elective_basket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("elective_baskets.id", ondelete="SET NULL"), 
        nullable=True
    )
    
    # Semester mapping (e.g. 3 for 3rd semester)
    semester: Mapped[int] = mapped_column(Integer, default=1)
    
    # Scalability
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
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
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    subjects: Mapped[List["Subject"]] = relationship(
        secondary=subject_semesters, back_populates="semesters"
    )
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="semester")
    
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
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    
    # Time slot info
    day: Mapped[int] = mapped_column(Integer)  # 0=Monday, 4=Friday
    slot: Mapped[int] = mapped_column(Integer)  # 0-6 (7 periods)
    
    # Component type for this allocation
    component_type: Mapped[ComponentType] = mapped_column(
        SQLEnum(ComponentType), default=ComponentType.THEORY
    )
    
    # For multi-slot sessions (labs)
    is_lab_continuation: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Elective tracking
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False)
    elective_basket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("elective_baskets.id", ondelete="SET NULL"), nullable=True
    )
    
    # Relationships
    teacher: Mapped["Teacher"] = relationship(back_populates="allocations")
    subject: Mapped["Subject"] = relationship(back_populates="allocations")
    semester: Mapped["Semester"] = relationship(back_populates="allocations")
    room: Mapped["Room"] = relationship(back_populates="allocations")
    substitutions: Mapped[List["Substitution"]] = relationship(back_populates="allocation")
    
    # Unique constraint: One class per semester per day/slot
    __table_args__ = (
        UniqueConstraint("semester_id", "day", "slot", name="uq_semester_day_slot"),
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
    Fixed one-to-one mapping of (semester, subject, component) -> teacher.
    
    HARD CONSTRAINT: For any (semester_id, subject_id, component_type) triplet, 
    EXACTLY ONE teacher is assigned for ALL slots throughout the week.
    """
    __tablename__ = "class_subject_teachers"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    component_type: Mapped[ComponentType] = mapped_column(
        SQLEnum(ComponentType), default=ComponentType.THEORY
    )
    
    # Assignment metadata
    assignment_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Lock flag - once locked, cannot be changed
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    teacher: Mapped["Teacher"] = relationship(back_populates="class_assignments")
    semester: Mapped["Semester"] = relationship()
    subject: Mapped["Subject"] = relationship()
    
    # Unique constraint: One teacher per (semester, subject, component)
    __table_args__ = (
        UniqueConstraint("semester_id", "subject_id", "component_type", 
                         name="uq_semester_subject_component_teacher"),
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
    
    # Total hours (COMMON for all subjects in basket)
    theory_hours_per_week: Mapped[int] = mapped_column(Integer, default=3)
    lab_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)  # 2 = 1 lab block
    tutorial_hours_per_week: Mapped[int] = mapped_column(Integer, default=0)
    
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
