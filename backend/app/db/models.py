"""
Database models for the Timetable Generator.
Defines all entities: Teachers, Subjects, Classes, Rooms, Allocations, Substitutions.
"""
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import (
    String, Integer, Float, Boolean, ForeignKey, DateTime, Date,
    Enum as SQLEnum, UniqueConstraint, Table, Column
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


class SubjectType(str, enum.Enum):
    """Types of subjects/courses."""
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


# ============================================================================
# MODELS
# ============================================================================

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
    
    # Availability: JSON-like string or separate table (simplified here)
    # Format: "1,2,3,4,5" for Monday-Friday availability
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
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Subject(Base):
    """Subject/Course entity."""
    __tablename__ = "subjects"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    
    weekly_hours: Mapped[int] = mapped_column(Integer, default=3)
    subject_type: Mapped[SubjectType] = mapped_column(SQLEnum(SubjectType), default=SubjectType.THEORY)
    
    # For labs: consecutive slots needed
    consecutive_slots: Mapped[int] = mapped_column(Integer, default=1)  # 2 for labs
    
    # Scalability
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    teachers: Mapped[List["Teacher"]] = relationship(
        secondary=teacher_subjects, back_populates="subjects"
    )
    allocations: Mapped[List["Allocation"]] = relationship(back_populates="subject")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Semester(Base):
    """Class/Semester entity (e.g., 'CSE 3rd Sem Section A')."""
    __tablename__ = "semesters"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))  # e.g., "3rd Semester - Section A"
    code: Mapped[str] = mapped_column(String(20), unique=True)  # e.g., "CS3A"
    
    year: Mapped[int] = mapped_column(Integer, default=2)  # 1st, 2nd, 3rd, 4th year
    section: Mapped[str] = mapped_column(String(10), default="A")
    student_count: Mapped[int] = mapped_column(Integer, default=60)
    
    # Scalability
    dept_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    college_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
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
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    
    # Time slot info
    day: Mapped[int] = mapped_column(Integer)  # 0=Monday, 4=Friday
    slot: Mapped[int] = mapped_column(Integer)  # 0-7 (8 periods)
    
    # For multi-slot sessions (labs)
    is_lab_continuation: Mapped[bool] = mapped_column(Boolean, default=False)
    
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
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
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
    
    allocation_id: Mapped[int] = mapped_column(ForeignKey("allocations.id"))
    original_teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    substitute_teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    
    substitution_date: Mapped[date] = mapped_column(Date)
    status: Mapped[SubstitutionStatus] = mapped_column(
        SQLEnum(SubstitutionStatus), default=SubstitutionStatus.PENDING
    )
    
    # Scoring info (for transparency)
    substitute_score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relationships
    allocation: Mapped["Allocation"] = relationship(back_populates="substitutions")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# FIXED TEACHER ASSIGNMENT MODEL (Issue 1 Fix)
# ============================================================================

class ClassSubjectTeacher(Base):
    """
    Fixed one-to-one mapping of (semester, subject) -> teacher.
    
    HARD CONSTRAINT: For any (semester_id, subject_id) pair, EXACTLY ONE teacher
    is assigned for ALL slots throughout the week. This prevents the bug where
    different teachers teach the same subject to the same class on different days.
    
    This mapping is:
    - Created ONCE during the pre-assignment phase
    - NEVER changed during slot generation
    - NOT altered by mutation or GA optimization
    """
    __tablename__ = "class_subject_teachers"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    
    # Assignment metadata
    assignment_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Stores why this teacher was selected (e.g., "lowest_workload", "best_effectiveness")
    
    # Lock flag - once locked, cannot be changed
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Unique constraint: One teacher per (semester, subject)
    __table_args__ = (
        UniqueConstraint("semester_id", "subject_id", name="uq_semester_subject_teacher"),
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# ELECTIVE GROUP MODEL (Issue 2 Fix)
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
    Represents a shared elective subject taken by students from multiple semesters/departments.
    
    HARD CONSTRAINT: An elective subject MUST be scheduled as ONE COMMON EVENT
    shared by ALL participating semesters at the SAME day and SAME period.
    
    Elective scheduling happens BEFORE normal subject scheduling:
    1. Find a COMMON FREE SLOT where teacher AND all participating semesters are free
    2. Lock that slot across all semesters
    3. Inject into all semester timetables
    4. Normal scheduling then avoids these locked slots
    """
    __tablename__ = "elective_groups"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # The elective subject
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    
    # Fixed teacher for this elective (assigned once, never changed)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    
    # Optional: specific room for elective
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    
    # Hours per week for this elective
    hours_per_week: Mapped[int] = mapped_column(Integer, default=3)
    
    # Elective name/code for grouping
    elective_code: Mapped[str] = mapped_column(String(20), unique=True)
    elective_name: Mapped[str] = mapped_column(String(200))
    
    # Is this elective active for scheduling?
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Lock flag - once scheduled, slots are locked
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Scheduled slots stored as JSON-like string: "day:slot,day:slot,..."
    # e.g., "1:2,3:2" means Tuesday period 3 and Thursday period 3
    scheduled_slots: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Relationships
    subject: Mapped["Subject"] = relationship()
    teacher: Mapped["Teacher"] = relationship()
    room: Mapped[Optional["Room"]] = relationship()
    participating_semesters: Mapped[List["Semester"]] = relationship(
        secondary=elective_group_semesters
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
