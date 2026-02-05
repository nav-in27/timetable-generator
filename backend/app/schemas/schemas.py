"""
Pydantic schemas for API request/response validation.
Updated to support the CORRECT ACADEMIC DATA MODEL with component-based subjects.
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


class ComponentType(str, Enum):
    """Types of subject components."""
    THEORY = "theory"
    LAB = "lab"
    TUTORIAL = "tutorial"


class SubjectType(str, Enum):
    """Subject classification for scheduling."""
    REGULAR = "regular"
    ELECTIVE = "elective"
    # Legacy compatibility
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
# SUBJECT SCHEMAS (Updated for Component-Based Model)
# ============================================================================

class SubjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=20)
    
    # Component-based hours (NEW - Correct Academic Model)
    theory_hours_per_week: int = Field(default=3, ge=0, le=25, description="Theory periods per week")
    lab_hours_per_week: int = Field(default=0, ge=0, le=10, description="Lab periods per week (2 = 1 block)")
    tutorial_hours_per_week: int = Field(default=0, ge=0, le=4, description="Tutorial periods per week")
    
    # Elective flag (NEW)
    is_elective: bool = Field(default=False, description="Is this an elective subject?")
    
    # Legacy compatibility (deprecated but kept for UI)
    weekly_hours: int = Field(default=3, ge=1, le=35)
    subject_type: SubjectType = SubjectType.REGULAR
    consecutive_slots: int = Field(default=1, ge=1, le=4)


class SubjectCreate(SubjectBase):
    semester_ids: List[int] = []
    elective_basket_id: Optional[int] = None


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    
    # Component hours
    theory_hours_per_week: Optional[int] = Field(None, ge=0, le=25)
    lab_hours_per_week: Optional[int] = Field(None, ge=0, le=10)
    tutorial_hours_per_week: Optional[int] = Field(None, ge=0, le=4)
    
    is_elective: Optional[bool] = None
    
    # Legacy
    weekly_hours: Optional[int] = Field(None, ge=1, le=35)
    subject_type: Optional[SubjectType] = None
    consecutive_slots: Optional[int] = Field(None, ge=1, le=4)
    semester_ids: Optional[List[int]] = None
    elective_basket_id: Optional[int] = None


class SubjectResponse(SubjectBase):
    id: int
    semesters: List["SemesterResponse"] = []
    elective_basket_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SubjectWithTeachers(SubjectResponse):
    teachers: List["TeacherBrief"] = []


class SubjectSummary(BaseModel):
    """Brief subject info for lists."""
    id: int
    name: str
    code: str
    theory_hours_per_week: int = 0
    lab_hours_per_week: int = 0
    is_elective: bool = False
    
    class Config:
        from_attributes = True


# ============================================================================
# ELECTIVE BASKET SCHEMAS (NEW)
# ============================================================================

class ElectiveBasketBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=20)
    semester_number: int = Field(..., ge=1, le=8)
    
    theory_hours_per_week: int = Field(default=3, ge=0, le=10)
    lab_hours_per_week: int = Field(default=0, ge=0, le=10)
    tutorial_hours_per_week: int = Field(default=0, ge=0, le=4)


class ElectiveBasketCreate(ElectiveBasketBase):
    subject_ids: List[int] = []  # Subjects in this basket
    semester_ids: List[int] = []  # Classes participating


class ElectiveBasketUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    theory_hours_per_week: Optional[int] = None
    lab_hours_per_week: Optional[int] = None
    subject_ids: Optional[List[int]] = None
    semester_ids: Optional[List[int]] = None


class ElectiveBasketResponse(ElectiveBasketBase):
    id: int
    is_scheduled: bool
    scheduled_slots: Optional[str]
    subjects: List[SubjectSummary] = []
    participating_semesters: List["SemesterResponse"] = []
    created_at: datetime
    
    class Config:
        from_attributes = True


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


# ============================================================================
# SEMESTER (CLASS) SCHEMAS
# ============================================================================

class SemesterBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=20)
    year: int = Field(default=2, ge=1, le=6)
    semester_number: int = Field(default=3, ge=1, le=8)  # Added for clarity
    section: str = Field(default="A", max_length=10)
    student_count: int = Field(default=60, ge=1, le=200)


class SemesterCreate(SemesterBase):
    pass


class SemesterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    year: Optional[int] = Field(None, ge=1, le=6)
    semester_number: Optional[int] = Field(None, ge=1, le=8)
    section: Optional[str] = Field(None, max_length=10)
    student_count: Optional[int] = Field(None, ge=1, le=200)


class SemesterResponse(SemesterBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SemesterWithHours(SemesterResponse):
    """Semester with computed hourly breakdown."""
    total_theory_hours: int = 0
    total_lab_hours: int = 0
    total_tutorial_hours: int = 0
    total_elective_hours: int = 0
    total_hours: int = 0
    available_slots: int = 35  # 7 periods × 5 days
    hours_deficit: int = 0  # How many free periods


# ============================================================================
# FIXED TEACHER ASSIGNMENT SCHEMAS
# ============================================================================

class ClassSubjectTeacherBase(BaseModel):
    semester_id: int
    subject_id: int
    teacher_id: int
    component_type: ComponentType = ComponentType.THEORY
    assignment_reason: Optional[str] = None
    is_locked: bool = True

class ClassSubjectTeacherCreate(ClassSubjectTeacherBase):
    pass

class ClassSubjectTeacherResponse(ClassSubjectTeacherBase):
    id: int
    semester: Optional[SemesterResponse] = None
    subject: Optional[SubjectResponse] = None
    
    class Config:
        from_attributes = True


class TeacherResponse(TeacherBase):
    id: int
    subjects: List[SubjectResponse] = []
    class_assignments: List[ClassSubjectTeacherResponse] = []
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
    slot: int = Field(..., ge=0, le=6)  # 7 periods (0-6)
    component_type: ComponentType = ComponentType.THEORY
    is_lab_continuation: bool = False


class AllocationCreate(AllocationBase):
    pass


class AllocationResponse(AllocationBase):
    id: int
    teacher: TeacherBrief
    subject: SubjectResponse
    semester: SemesterResponse
    room: RoomResponse
    is_elective: bool = False
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
    component_type: Optional[str] = None  # theory/lab/tutorial
    is_lab: bool = False
    is_elective: bool = False
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
# GENERATION SCHEMAS (Enhanced with Validation)
# ============================================================================

class GenerationRequest(BaseModel):
    """Request to generate timetable."""
    semester_ids: Optional[List[int]] = None  # If None, generate for all
    clear_existing: bool = True


class HourValidationError(BaseModel):
    """Validation error for a semester's hours."""
    semester_id: int
    semester_name: str
    total_theory_hours: int
    total_lab_hours: int
    total_tutorial_hours: int
    total_elective_hours: int
    total_required_hours: int
    available_slots: int
    error_message: str


class GenerationResult(BaseModel):
    """Result of timetable generation."""
    success: bool
    message: str
    total_allocations: int
    
    # Validation info
    validation_errors: List[HourValidationError] = []
    
    # Phase breakdown
    phase_results: dict = {}  # e.g., {"elective_theory": 6, "elective_lab": 4, "labs": 20, "theory": 100}
    
    # Soft constraint metrics
    hard_constraint_violations: int = 0
    soft_constraint_score: float = 0.0
    generation_time_seconds: float = 0.0


# ============================================================================
# VALIDATION SCHEMAS (NEW - For Phase 0)
# ============================================================================

class DataValidationRequest(BaseModel):
    """Request to validate data before generation."""
    semester_ids: Optional[List[int]] = None


class SemesterHoursBreakdown(BaseModel):
    """Detailed hours breakdown for a semester."""
    semester_id: int
    semester_name: str
    
    # Regular subjects
    regular_theory_hours: int = 0
    regular_lab_hours: int = 0
    regular_tutorial_hours: int = 0
    
    # Elective subjects (counted as common slots)
    elective_theory_slots: int = 0  # NOT multiplied by subject count
    elective_lab_slots: int = 0     # NOT multiplied by subject count
    
    # Totals
    total_required_slots: int = 0
    available_slots: int = 35
    
    # Status
    is_valid: bool = True
    deficit_or_excess: int = 0
    validation_message: str = ""


class DataValidationResult(BaseModel):
    """Result of data validation."""
    is_valid: bool
    overall_message: str
    semester_breakdowns: List[SemesterHoursBreakdown] = []
    errors: List[str] = []
    warnings: List[str] = []


# ============================================================================
# FIXED SLOT SCHEMAS (MANUAL SLOT LOCKING)
# ============================================================================

class FixedSlotBase(BaseModel):
    """Base schema for fixed/locked slots."""
    semester_id: int
    day: int = Field(..., ge=0, le=4, description="Day of week (0=Monday, 4=Friday)")
    slot: int = Field(..., ge=0, le=6, description="Period number (0-6)")
    subject_id: int
    teacher_id: int
    room_id: Optional[int] = None
    component_type: ComponentType = ComponentType.THEORY
    is_lab_continuation: bool = False
    is_elective: bool = False
    elective_basket_id: Optional[int] = None
    locked_by: Optional[str] = None
    lock_reason: Optional[str] = None


class FixedSlotCreate(FixedSlotBase):
    """Schema for creating a fixed slot."""
    pass


class FixedSlotUpdate(BaseModel):
    """Schema for updating a fixed slot (limited updates allowed)."""
    room_id: Optional[int] = None
    lock_reason: Optional[str] = None


class FixedSlotResponse(FixedSlotBase):
    """Response schema for fixed slot."""
    id: int
    locked: bool = True
    semester_name: Optional[str] = None
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    teacher_name: Optional[str] = None
    room_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class FixedSlotValidation(BaseModel):
    """Validation result for attempting to lock a slot."""
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []


class FixedSlotsBySemester(BaseModel):
    """Fixed slots grouped by semester for UI display."""
    semester_id: int
    semester_name: str
    fixed_slots: List[FixedSlotResponse] = []


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
    total_elective_baskets: int = 0
    total_fixed_slots: int = 0  # NEW: Count of locked slots
    active_substitutions: int
    teachers_absent_today: int


# Update forward references
SubjectWithTeachers.model_rebuild()
SubjectResponse.model_rebuild()
ElectiveBasketResponse.model_rebuild()
SemesterWithHours.model_rebuild()
