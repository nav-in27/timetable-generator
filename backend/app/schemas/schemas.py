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


class AcademicComponentType(str, Enum):
    """
    Extended academic component labels (timetable-visible).

    NOTE: These labels can be stored alongside `component_type` for reporting/UI without
    changing scheduling behavior.
    """
    THEORY = "theory"
    LAB = "lab"
    TUTORIAL = "tutorial"
    PROJECT = "project"
    REPORT = "report"
    SELF_STUDY = "self_study"
    SEMINAR = "seminar"


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


class ImportanceLevel(str, Enum):
    """Academic importance level for scheduling priority bias."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


# ============================================================================
# DEPARTMENT SCHEMAS
# ============================================================================

class DepartmentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=20)

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=20)

class DepartmentResponse(DepartmentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# ROOM SCHEMAS
# ============================================================================

class RoomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    capacity: int = Field(..., ge=1, le=500)
    room_type: RoomType = RoomType.LECTURE
    is_available: bool = True
    dept_id: Optional[int] = None  # Legacy single-department (backward compat)
    dept_ids: List[int] = Field(default_factory=list, description="Departments that share this room")
    # Section-wise assignment (optional)
    assigned_year: Optional[int] = Field(None, ge=1, le=6, description="Year this room is assigned to")
    assigned_section: Optional[str] = Field(None, max_length=10, description="Section this room is assigned to")
    is_default_classroom: bool = Field(False, description="If true, room is auto-used for this section's theory classes")


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    capacity: Optional[int] = Field(None, ge=1, le=500)
    room_type: Optional[RoomType] = None
    is_available: Optional[bool] = None
    dept_id: Optional[int] = None
    dept_ids: Optional[List[int]] = None
    assigned_year: Optional[int] = Field(None, ge=1, le=6)
    assigned_section: Optional[str] = Field(None, max_length=10)
    is_default_classroom: Optional[bool] = None


class RoomResponse(BaseModel):
    id: int
    name: str
    capacity: int
    room_type: RoomType
    is_available: bool
    dept_id: Optional[int] = None
    dept_ids: List[int] = Field(default_factory=list)
    assigned_year: Optional[int] = None
    assigned_section: Optional[str] = None
    is_default_classroom: bool = False
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
    lab_hours_per_week: int = Field(default=0, ge=0, le=20, description="Lab periods per week (2 = 1 block)")
    tutorial_hours_per_week: int = Field(default=0, ge=0, le=10, description="Tutorial periods per week")

    # Extended academic components (Optional)
    project_hours_per_week: int = Field(default=0, ge=0, le=26, description="Project periods per week")
    project_block_size: int = Field(default=1, ge=1, le=2, description="Project block size (1 or 2)")

    report_hours_per_week: int = Field(default=0, ge=0, le=26, description="Report periods per week")
    report_block_size: int = Field(default=1, ge=1, le=2, description="Report block size (1 or 2)")

    self_study_hours_per_week: int = Field(default=0, ge=0, le=26, description="Self Study periods per week")

    seminar_hours_per_week: int = Field(default=0, ge=0, le=35, description="Seminar periods per week")
    seminar_block_size: int = Field(default=2, ge=1, le=7, description="Seminar block size (1, 2, or 7 for day-based)")
    seminar_day_based: bool = Field(default=False, description="Prefer day-based seminar scheduling when enabled")
    
    # Elective flag (NEW)
    is_elective: bool = Field(default=False, description="Is this an elective subject?")
    
    # Legacy compatibility (deprecated but kept for UI)
    weekly_hours: int = Field(default=3, ge=1, le=35)
    subject_type: SubjectType = SubjectType.REGULAR
    consecutive_slots: int = Field(default=1, ge=1, le=4)
    
    # New Fields for Filtering
    dept_id: Optional[int] = None
    year: int = Field(default=1, ge=1, le=4)
    semester: int = Field(default=1, ge=1, le=8)
    
    # Academic Importance & Priority (Optional, backward-compatible)
    importance_level: Optional[str] = Field(default="NORMAL", description="LOW / NORMAL / HIGH")
    previous_year_pass_percentage: Optional[int] = Field(default=None, ge=0, le=100, description="Previous year pass %")
    computed_priority_score: Optional[int] = Field(default=0, description="Auto-calculated, not user editable")


class SubjectCreate(SubjectBase):
    semester_ids: List[int] = []
    elective_basket_id: Optional[int] = None


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    
    # Component hours
    theory_hours_per_week: Optional[int] = Field(None, ge=0, le=25)
    lab_hours_per_week: Optional[int] = Field(None, ge=0, le=20)
    tutorial_hours_per_week: Optional[int] = Field(None, ge=0, le=10)

    project_hours_per_week: Optional[int] = Field(None, ge=0, le=26)
    project_block_size: Optional[int] = Field(None, ge=1, le=2)

    report_hours_per_week: Optional[int] = Field(None, ge=0, le=26)
    report_block_size: Optional[int] = Field(None, ge=1, le=2)

    self_study_hours_per_week: Optional[int] = Field(None, ge=0, le=26)

    seminar_hours_per_week: Optional[int] = Field(None, ge=0, le=35)
    seminar_block_size: Optional[int] = Field(None, ge=1, le=7)
    seminar_day_based: Optional[bool] = None
    
    is_elective: Optional[bool] = None

    # Department context + academic level (optional)
    dept_id: Optional[int] = None
    year: Optional[int] = Field(None, ge=1, le=4)
    semester: Optional[int] = Field(None, ge=1, le=8)
    
    # Academic Importance (optional)
    importance_level: Optional[str] = None
    previous_year_pass_percentage: Optional[int] = Field(None, ge=0, le=100)
    
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
    importance_level: Optional[str] = "NORMAL"
    previous_year_pass_percentage: Optional[int] = None
    computed_priority_score: Optional[int] = 0
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
    importance_level: Optional[str] = "NORMAL"
    previous_year_pass_percentage: Optional[int] = None
    computed_priority_score: Optional[int] = 0
    
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
    self_study_hours_per_week: int = Field(default=0, ge=0, le=10)


class ElectiveBasketCreate(ElectiveBasketBase):
    subject_ids: List[int] = []  # Subjects in this basket
    semester_ids: List[int] = []  # Classes participating


class ElectiveBasketUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    theory_hours_per_week: Optional[int] = None
    lab_hours_per_week: Optional[int] = None
    self_study_hours_per_week: Optional[int] = None
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
    
    # New Fields
    teacher_code: Optional[str] = None
    dept_id: Optional[int] = None


class TeacherCreate(TeacherBase):
    teacher_code: str = Field(..., min_length=1, max_length=20)
    dept_id: Optional[int] = None
    subject_ids: List[int] = []


class TeacherUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    teacher_code: Optional[str] = Field(None, min_length=1, max_length=20)
    email: Optional[str] = None
    phone: Optional[str] = None
    max_hours_per_week: Optional[int] = Field(None, ge=1, le=40)
    max_consecutive_classes: Optional[int] = Field(None, ge=1, le=8)
    experience_years: Optional[int] = Field(None, ge=0, le=50)
    experience_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    available_days: Optional[str] = None
    is_active: Optional[bool] = None
    dept_id: Optional[int] = None
    subject_ids: Optional[List[int]] = None


class TeacherBrief(BaseModel):
    id: int
    name: str
    teacher_code: Optional[str] = None
    
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
    dept_id: Optional[int] = None


class SemesterCreate(SemesterBase):
    pass


class SemesterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    year: Optional[int] = Field(None, ge=1, le=6)
    semester_number: Optional[int] = Field(None, ge=1, le=8)
    section: Optional[str] = Field(None, max_length=10)
    student_count: Optional[int] = Field(None, ge=1, le=200)
    dept_id: Optional[int] = None


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
# BATCH SCHEMAS (NEW)
# ============================================================================

class BatchBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    size: Optional[int] = Field(None, ge=1)

class BatchCreate(BatchBase):
    pass

class BatchResponse(BatchBase):
    id: int
    semester_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SemesterResponseWithBatches(SemesterResponse):
    batches: List[BatchResponse] = []


# ============================================================================
# FIXED TEACHER ASSIGNMENT SCHEMAS
# ============================================================================

class ClassSubjectTeacherWrite(BaseModel):
    semester_id: int
    subject_id: int
    room_id: Optional[int] = None
    batch_id: Optional[int] = None
    component_type: ComponentType = ComponentType.THEORY
    assignment_reason: Optional[str] = None
    parallel_lab_group: Optional[str] = None
    is_locked: bool = True

class ClassSubjectTeacherCreate(ClassSubjectTeacherWrite):
    pass

class ClassSubjectTeacherBase(ClassSubjectTeacherWrite):
    teacher_id: int

class ClassSubjectTeacherResponse(ClassSubjectTeacherBase):
    id: int
    semester: Optional[SemesterResponse] = None
    subject: Optional[SubjectResponse] = None
    room: Optional[RoomResponse] = None
    batch: Optional[BatchResponse] = None
    
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
    teacher_id: Optional[int] = None
    subject_id: Optional[int] = None
    semester_id: int
    room_id: Optional[int] = None
    batch_id: Optional[int] = None  # NEW
    day: int = Field(..., ge=0, le=4)  # 0=Monday, 4=Friday
    slot: int = Field(..., ge=0, le=6)  # 7 periods (0-6)
    component_type: ComponentType = ComponentType.THEORY
    academic_component: Optional[AcademicComponentType] = None
    is_lab_continuation: bool = False


class AllocationCreate(AllocationBase):
    pass


class AllocationResponse(AllocationBase):
    id: int
    teacher: Optional[TeacherBrief] = None
    subject: Optional[SubjectResponse] = None
    semester: SemesterResponse
    room: Optional[RoomResponse] = None
    batch: Optional[BatchResponse] = None
    is_elective: bool = False
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class BatchAllocationData(BaseModel):
    """Details for a specific batch in a slot."""
    batch_id: Optional[int] = None
    batch_name: Optional[str] = None
    teacher_name: str
    room_name: Optional[str] = None
    subject_name: Optional[str] = None  # NEW: For parallel multi-subject labs
    subject_code: Optional[str] = None  # NEW: For parallel multi-subject labs


class TimetableSlot(BaseModel):
    """Single slot in a timetable view."""
    allocation_id: Optional[int] = None
    teacher_name: Optional[str] = None
    teacher_id: Optional[int] = None
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    room_name: Optional[str] = None
    batch_name: Optional[str] = None  # NEW
    batch_allocations: List[BatchAllocationData] = []  # NEW: For parallel batches
    component_type: Optional[str] = None  # theory/lab/tutorial
    academic_component: Optional[str] = None  # extended label (project/report/self_study/seminar)
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
    break_slots: List[int] = []
    lunch_slot: Optional[int] = None


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
    """A potential substitute teacher (strict same-class policy)."""
    teacher_id: int
    teacher_name: str
    teacher_code: str = ''
    score: float
    subject_match: bool
    current_load: int
    effectiveness: float
    experience_score: float
    class_subjects: List[str] = []  # Subjects they already handle for this class


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
    dept_id: Optional[int] = None # Department-wise generation
    semester_type: Optional[str] = "EVEN"
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
    total_batches_scheduled: int = 0  # NEW
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
    academic_component: Optional[AcademicComponentType] = None
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


# ============================================================================
# RULE TOGGLES (DEPARTMENT-SPECIFIC)
# ============================================================================

class DepartmentSummary(BaseModel):
    id: int
    name: str
    code: str

    class Config:
        from_attributes = True


class DepartmentRuleToggleBase(BaseModel):
    lab_continuity_strict: bool = False
    teacher_gap_preference: bool = False
    max_consecutive_enabled: bool = False
    max_consecutive_limit: int = Field(default=3, ge=1, le=8)
    lab_continuity_is_hard: bool = False
    teacher_gap_is_hard: bool = False
    max_consecutive_is_hard: bool = False


class DepartmentRuleToggleUpdate(BaseModel):
    lab_continuity_strict: Optional[bool] = None
    teacher_gap_preference: Optional[bool] = None
    max_consecutive_enabled: Optional[bool] = None
    max_consecutive_limit: Optional[int] = Field(default=None, ge=1, le=8)
    lab_continuity_is_hard: Optional[bool] = None
    teacher_gap_is_hard: Optional[bool] = None
    max_consecutive_is_hard: Optional[bool] = None


class DepartmentRuleToggleResponse(DepartmentRuleToggleBase):
    id: Optional[int] = None
    dept_id: int
    department: Optional[DepartmentSummary] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# STRUCTURED COMPOSITE BASKET (SCB) SCHEMAS
# ============================================================================

class StructuredCompositeBasketBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    semester: int = Field(..., ge=1, le=8)
    theory_hours: int = Field(default=3, ge=0, le=10)
    lab_hours: int = Field(default=2, ge=0, le=10)
    continuous_lab_periods: int = Field(default=2, ge=1, le=4)
    same_slot_across_departments: bool = True
    allow_lab_parallel: bool = False


class StructuredCompositeBasketCreate(StructuredCompositeBasketBase):
    department_ids: List[int] = []
    class_ids: List[int] = []  # Specific semester/class IDs within selected departments
    subject_ids: List[int] = []


class StructuredCompositeBasketUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    theory_hours: Optional[int] = Field(None, ge=0, le=10)
    lab_hours: Optional[int] = Field(None, ge=0, le=10)
    continuous_lab_periods: Optional[int] = Field(None, ge=1, le=4)
    same_slot_across_departments: Optional[bool] = None
    allow_lab_parallel: Optional[bool] = None
    department_ids: Optional[List[int]] = None
    class_ids: Optional[List[int]] = None  # Specific semester/class IDs
    subject_ids: Optional[List[int]] = None


class StructuredCompositeBasketResponse(StructuredCompositeBasketBase):
    id: int
    is_scheduled: bool = False
    scheduled_slots: Optional[str] = None
    departments_involved: List[DepartmentSummary] = []
    selected_classes: List[SemesterResponse] = []
    linked_subjects: List[SubjectSummary] = []
    
    class Config:
        from_attributes = True


# ============================================================================
# REPORTING SCHEMAS (READ-ONLY)
# ============================================================================

class TeacherWorkloadReportRow(BaseModel):
    teacher_id: int
    teacher_name: str
    teacher_code: Optional[str] = None
    total_hours: int
    theory_hours: int
    lab_hours: int
    tutorial_hours: int
    project_hours: int = 0
    report_hours: int = 0
    self_study_hours: int = 0
    seminar_hours: int = 0
    elective_hours: int
    max_consecutive_periods: int
    free_periods: int
    departments: List[DepartmentSummary] = []


class TeacherWorkloadReport(BaseModel):
    generated_at: datetime
    dept_id: Optional[int] = None
    department: Optional[DepartmentSummary] = None
    total_teachers: int
    rows: List[TeacherWorkloadReportRow] = []


class RoomUtilizationReportRow(BaseModel):
    room_id: int
    room_name: str
    room_type: RoomType
    total_available_periods: int
    periods_used: int
    utilization_percent: float
    peak_usage_days: List[str] = []


class RoomUtilizationReport(BaseModel):
    generated_at: datetime
    dept_id: Optional[int] = None
    department: Optional[DepartmentSummary] = None
    total_rooms: int
    rows: List[RoomUtilizationReportRow] = []


class SubjectCoverageReportRow(BaseModel):
    subject_id: int
    subject_code: str
    subject_name: str
    required_hours: int
    assigned_hours: int
    status: str
    teacher_names: List[str] = []
    teacher_codes: List[str] = []
    dept_id: Optional[int] = None
    department: Optional[str] = None
    year: Optional[int] = None
    section: Optional[str] = None
    semester_id: Optional[int] = None
    semester_name: Optional[str] = None
    semester_code: Optional[str] = None


class SubjectCoverageReport(BaseModel):
    generated_at: datetime
    dept_id: Optional[int] = None
    department: Optional[DepartmentSummary] = None
    total_subjects: int
    rows: List[SubjectCoverageReportRow] = []


# ============================================================================
# TEACHER LOAD DASHBOARD (READ-ONLY)
# ============================================================================

class TeacherLoadRow(BaseModel):
    teacher_id: int
    teacher_name: str
    teacher_code: Optional[str] = None
    total_hours: int
    theory_hours: int
    lab_hours: int
    tutorial_hours: int = 0
    project_hours: int = 0
    report_hours: int = 0
    seminar_hours: int = 0
    internship_hours: int = 0
    elective_hours: int
    max_consecutive_periods: int
    days_with_overload: int
    max_hours_per_week: int
    max_consecutive_allowed: int
    load_ratio: float
    status: str  # normal | high | overload
    consecutive_overload: bool
    departments: List[DepartmentSummary] = []


class TeacherLoadDashboard(BaseModel):
    generated_at: datetime
    dept_id: Optional[int] = None
    year: Optional[int] = None
    department: Optional[DepartmentSummary] = None
    total_teachers: int
    rows: List[TeacherLoadRow] = []


# Update forward references
SubjectWithTeachers.model_rebuild()
SubjectResponse.model_rebuild()
ElectiveBasketResponse.model_rebuild()
SemesterWithHours.model_rebuild()
