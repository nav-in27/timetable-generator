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
