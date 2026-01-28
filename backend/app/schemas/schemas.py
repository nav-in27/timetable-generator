"""
Pydantic schemas for API request/response validation.
Provides type-safe data transfer objects.
"""
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


# ============================================================================
# ENUMS (matching DB enums)
# ============================================================================

class RoomType(str, Enum):
    LECTURE = "lecture"
    LAB = "lab"
    SEMINAR = "seminar"


class SubjectType(str, Enum):
    THEORY = "theory"
    LAB = "lab"
    TUTORIAL = "tutorial"


class SubstitutionStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ============================================================================
# ROOM SCHEMAS
# ============================================================================

class RoomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    capacity: int = Field(..., ge=1, le=500)
    room_type: RoomType = RoomType.LECTURE
    is_available: bool = True


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    capacity: Optional[int] = Field(None, ge=1, le=500)
    room_type: Optional[RoomType] = None
    is_available: Optional[bool] = None


class RoomResponse(RoomBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# SUBJECT SCHEMAS
# ============================================================================

class SubjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=20)
    weekly_hours: int = Field(default=3, ge=1, le=10)
    subject_type: SubjectType = SubjectType.THEORY
    consecutive_slots: int = Field(default=1, ge=1, le=4)


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    weekly_hours: Optional[int] = Field(None, ge=1, le=10)
    subject_type: Optional[SubjectType] = None
    consecutive_slots: Optional[int] = Field(None, ge=1, le=4)


class SubjectResponse(SubjectBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SubjectWithTeachers(SubjectResponse):
    teachers: List["TeacherBrief"] = []


# ============================================================================
# TEACHER SCHEMAS
# ============================================================================

class TeacherBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    email: Optional[str] = None
    phone: Optional[str] = None
    max_hours_per_week: int = Field(default=20, ge=1, le=40)
    max_consecutive_classes: int = Field(default=3, ge=1, le=8)
    experience_years: int = Field(default=1, ge=0, le=50)
    experience_score: float = Field(default=0.5, ge=0.0, le=1.0)
    available_days: str = Field(default="0,1,2,3,4")
    is_active: bool = True


class TeacherCreate(TeacherBase):
    subject_ids: List[int] = []


class TeacherUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    email: Optional[str] = None
    phone: Optional[str] = None
    max_hours_per_week: Optional[int] = Field(None, ge=1, le=40)
    max_consecutive_classes: Optional[int] = Field(None, ge=1, le=8)
    experience_years: Optional[int] = Field(None, ge=0, le=50)
    experience_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    available_days: Optional[str] = None
    is_active: Optional[bool] = None
    subject_ids: Optional[List[int]] = None


class TeacherBrief(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True


class TeacherResponse(TeacherBase):
    id: int
    subjects: List[SubjectResponse] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# SEMESTER (CLASS) SCHEMAS
# ============================================================================

class SemesterBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=20)
    year: int = Field(default=2, ge=1, le=6)
    section: str = Field(default="A", max_length=10)
    student_count: int = Field(default=60, ge=1, le=200)


class SemesterCreate(SemesterBase):
    pass


class SemesterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    year: Optional[int] = Field(None, ge=1, le=6)
    section: Optional[str] = Field(None, max_length=10)
    student_count: Optional[int] = Field(None, ge=1, le=200)


class SemesterResponse(SemesterBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# ALLOCATION SCHEMAS
# ============================================================================

class AllocationBase(BaseModel):
    teacher_id: int
    subject_id: int
    semester_id: int
    room_id: int
    day: int = Field(..., ge=0, le=4)  # 0=Monday, 4=Friday
    slot: int = Field(..., ge=0, le=7)  # 8 periods
    is_lab_continuation: bool = False


class AllocationCreate(AllocationBase):
    pass


class AllocationResponse(AllocationBase):
    id: int
    teacher: TeacherBrief
    subject: SubjectResponse
    semester: SemesterResponse
    room: RoomResponse
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TimetableSlot(BaseModel):
    """Single slot in a timetable view."""
    allocation_id: Optional[int] = None
    teacher_name: Optional[str] = None
    teacher_id: Optional[int] = None
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    room_name: Optional[str] = None
    is_lab: bool = False
    is_substituted: bool = False
    substitute_teacher_name: Optional[str] = None


class TimetableDay(BaseModel):
    """One day's worth of slots."""
    day: int
    day_name: str
    slots: List[TimetableSlot]


class TimetableView(BaseModel):
    """Complete timetable for a class or teacher."""
    entity_type: str  # "semester" or "teacher"
    entity_id: int
    entity_name: str
    days: List[TimetableDay]


# ============================================================================
# ABSENCE & SUBSTITUTION SCHEMAS
# ============================================================================

class TeacherAbsenceCreate(BaseModel):
    teacher_id: int
    absence_date: date
    reason: Optional[str] = None
    is_full_day: bool = True
    absent_slots: Optional[str] = None  # e.g., "0,1,2"


class TeacherAbsenceResponse(TeacherAbsenceCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class SubstitutionCandidate(BaseModel):
    """A potential substitute teacher."""
    teacher_id: int
    teacher_name: str
    score: float
    subject_match: bool
    current_load: int
    effectiveness: float
    experience_score: float


class SubstitutionRequest(BaseModel):
    """Request to find and assign a substitute."""
    allocation_id: int
    substitution_date: date
    reason: Optional[str] = None


class SubstitutionResponse(BaseModel):
    id: int
    allocation_id: int
    original_teacher_id: int
    substitute_teacher_id: int
    substitution_date: date
    status: SubstitutionStatus
    substitute_score: float
    reason: Optional[str] = None
    original_teacher_name: Optional[str] = None
    substitute_teacher_name: Optional[str] = None
    subject_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# GENERATION SCHEMAS
# ============================================================================

class GenerationRequest(BaseModel):
    """Request to generate timetable."""
    semester_ids: Optional[List[int]] = None  # If None, generate for all
    clear_existing: bool = True


class GenerationResult(BaseModel):
    """Result of timetable generation."""
    success: bool
    message: str
    total_allocations: int
    hard_constraint_violations: int
    soft_constraint_score: float
    generation_time_seconds: float


# ============================================================================
# DASHBOARD SCHEMAS
# ============================================================================

class DashboardStats(BaseModel):
    """Dashboard statistics."""
    total_teachers: int
    total_subjects: int
    total_semesters: int
    total_rooms: int
    total_allocations: int
    active_substitutions: int
    teachers_absent_today: int


# Update forward references
SubjectWithTeachers.model_rebuild()
