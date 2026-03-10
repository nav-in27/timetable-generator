"""
READ-ONLY COLLEGE TIMETABLE GENERATION ENGINE
==============================================

CRITICAL SAFETY RULE (ABSOLUTE):
- DO NOT delete, recreate, overwrite, or modify any existing data
- DO NOT change existing teachers, subjects, classes, or assignments
- ONLY READ existing data and ENFORCE rules during timetable generation

GENERATION FLOW:
1. READ existing teacher-subject-class mappings
2. BUILD temporary elective time locks (in-memory only)
3. ALLOCATE slots using ONLY existing mappings
4. SAVE allocations to database (new records only)
5. NEVER modify source data
"""
import random
import time
import os
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from app.db.models import (
    Teacher, Subject, Semester, Room, Allocation, FixedSlot,
    RoomType, SubjectType, ComponentType, ClassSubjectTeacher,
    ElectiveBasket, teacher_subjects
)

# ============================================================
# CONSTANTS
# ============================================================
DAYS_PER_WEEK = 5
SLOTS_PER_DAY = 7
TOTAL_WEEKLY_SLOTS = DAYS_PER_WEEK * SLOTS_PER_DAY  # 35

# Valid lab block positions (0-indexed):
# Morning: 1st+2nd (0,1) or 2nd+3rd (1,2)
# After Lunch: 4th+5th (3,4), 5th+6th (4,5), or 6th+7th (5,6)
VALID_LAB_BLOCKS = [(0, 1), (1, 2), (3, 4), (4, 5), (5, 6)]


# ============================================================
# DATA STRUCTURES (IN-MEMORY ONLY - NO DATABASE WRITES)
# ============================================================

@dataclass
class ComponentRequirement:
    """A single component that needs to be scheduled (READ from DB)."""
    # Required fields (non-default arguments)
    semester_id: int
    subject_id: int
    subject_name: str
    subject_code: str
    component_type: ComponentType
    hours_per_week: int
    min_room_capacity: int
    is_elective: bool
    elective_basket_id: Optional[int]
    year: int  # Semester number / year for elective grouping

    # Optional fields (default arguments)
    academic_component: str = "theory"  # extended label (project/report/self_study/seminar/etc)
    block_size: int = 1  # 1 (single), 2 (continuous), 7 (day-based seminar preference)
    preferred_room_types: Optional[List[RoomType]] = None
    assigned_teacher_id: Optional[int] = None  # READ from existing mapping (default/primary)
    assigned_room_id: Optional[int] = None  # Optional preferred/assigned room (e.g., lab room)
    
    # NEW: PARALLEL BATCH SUPPORT
    # Mapping of batch_id -> teacher_id for split classes
    # If populated, this requirement should be scheduled as PARALLEL BATCHES
    batch_allocations: Dict[int, int] = field(default_factory=dict)
    batch_room_allocations: Dict[int, int] = field(default_factory=dict)  # batch_id -> room_id
    parallel_lab_group: Optional[str] = None  # Links multi-subject parallel labs
    priority_weight: int = 0  # Soft scheduling weight for morning slot preference


@dataclass
class AllocationEntry:
    """A single allocation in the timetable (NEW records to be created)."""
    semester_id: int
    subject_id: Optional[int]
    teacher_id: Optional[int]
    room_id: Optional[int]
    day: int
    slot: int
    component_type: ComponentType = ComponentType.THEORY
    academic_component: Optional[str] = None
    is_lab_continuation: bool = False
    is_elective: bool = False
    elective_basket_id: Optional[int] = None
    batch_id: Optional[int] = None


@dataclass
class TimetableState:
    """
    IN-MEMORY state for constraint checking.
    NO DATA IS WRITTEN BACK - this is purely for generation logic.
    
    EXTENDED: Now supports MULTIPLE elective groups per year.
    Each (year, basket_id) combination is tracked independently.
    """
    allocations: List[AllocationEntry] = field(default_factory=list)
    
    # Lookup tables (in-memory only)
    teacher_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    room_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    semester_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    
    # READ-ONLY teacher assignment map: (semester_id, subject_id, component_type) -> teacher_id
    # This is READ from database, NEVER modified
    teacher_assignment_map: Dict[Tuple[int, int, str], int] = field(default_factory=dict)
    
    # TEMPORARY elective locks (in-memory, cleared after generation)
    # (day, slot) -> Set[teacher_ids] locked for elective
    elective_teacher_locks: Dict[Tuple[int, int], Set[int]] = field(default_factory=dict)
    
    # EXTENDED: Elective locks by group - tracks which group owns which slot
    # (day, slot) -> (year, basket_id) - indicates which group owns this slot
    # NOTE: keyed by (year, day, slot) so different student years can share the same time slot.
    elective_slot_ownership: Dict[Tuple[int, int, int], Tuple[int, Optional[int]]] = field(default_factory=dict)
    
    # EXTENDED: Elective slots by group: (year, basket_id) -> List[(day, slot)]
    # Each group tracks its own reserved slots independently
    elective_slots_by_group: Dict[Tuple[int, Optional[int]], List[Tuple[int, int]]] = field(default_factory=dict)
    
    # Legacy compatibility: elective_slots_by_year (for backward compatibility)
    elective_slots_by_year: Dict[int, List[Tuple[int, int]]] = field(default_factory=dict)
    
    # Subject daily counts (in-memory tracking)
    subject_daily_counts: Dict[Tuple[int, int], Dict[int, int]] = field(default_factory=dict)
    
    # EXTENDED: Track which teachers are assigned to which elective groups
    # (teacher_id) -> Set[(year, basket_id)] - groups this teacher belongs to
    teacher_elective_groups: Dict[int, Set[Tuple[int, Optional[int]]]] = field(default_factory=dict)
    
    # NEW: Fixed/locked slots - slots that are pre-filled and IMMUTABLE during generation
    # (semester_id, day, slot) -> True if this slot is fixed and cannot be changed
    fixed_slots: Set[Tuple[int, int, int]] = field(default_factory=set)
    
    # NEW: Blocked slots across all entities (e.g. breaks, lunch)
    # Set of integers representing blocked slot indices (0-6)
    global_blocked_slots: Set[int] = field(default_factory=set)
    
    def is_slot_fixed(self, semester_id: int, day: int, slot: int) -> bool:
        """Check if a slot is fixed/locked and cannot be modified."""
        if slot in self.global_blocked_slots:
            return True
        return (semester_id, day, slot) in self.fixed_slots
    
    def mark_slot_as_fixed(self, semester_id: int, day: int, slot: int):
        """Mark a slot as fixed/locked."""
        self.fixed_slots.add((semester_id, day, slot))
    
    def add_allocation(self, entry: AllocationEntry, force_parallel: bool = False) -> bool:
        """Add allocation to in-memory state. Returns False if slot taken.
        
        force_parallel: If True, allows co-scheduling in the same semester slot
            even without batch_id (used for parallel labs and elective baskets
            where multiple subjects run simultaneously with different teachers).
        """
        slot_key = (entry.day, entry.slot)
        
        # Check for collision
        if entry.semester_id in self.semester_slots:
            if slot_key in self.semester_slots[entry.semester_id]:
                existing_in_slot = [a for a in self.allocations 
                                    if a.semester_id == entry.semester_id 
                                    and a.day == entry.day and a.slot == entry.slot]
                
                for existing in existing_in_slot:
                    # Parallel/elective entries with different subjects are allowed
                    if force_parallel and existing.subject_id != entry.subject_id:
                        continue
                    # Collision check:
                    # 1. Different batches -> Allowed (parallel batch scheduling)
                    # 2. Same batch or no batch -> Collision
                    if entry.batch_id is None or existing.batch_id is None or entry.batch_id == existing.batch_id:
                        return False
        
        self.allocations.append(entry)
        
        # Update in-memory lookups
        if entry.teacher_id is not None:
            if entry.teacher_id not in self.teacher_slots:
                self.teacher_slots[entry.teacher_id] = set()
            self.teacher_slots[entry.teacher_id].add(slot_key)
        
        if entry.room_id is not None:
            if entry.room_id not in self.room_slots:
                self.room_slots[entry.room_id] = set()
            self.room_slots[entry.room_id].add(slot_key)
        
        if entry.semester_id not in self.semester_slots:
            self.semester_slots[entry.semester_id] = set()
        self.semester_slots[entry.semester_id].add(slot_key)
        
        # Track subject daily count
        day_key = (entry.semester_id, entry.day)
        if day_key not in self.subject_daily_counts:
            self.subject_daily_counts[day_key] = {}
        current = self.subject_daily_counts[day_key].get(entry.subject_id, 0)
        self.subject_daily_counts[day_key][entry.subject_id] = current + 1
        
        return True
    
    def remove_allocation(self, entry: AllocationEntry):
        """Remove an allocation from in-memory state, reversing all tracking."""
        slot_key = (entry.day, entry.slot)
        
        # Remove from allocations list
        self.allocations = [
            a for a in self.allocations
            if not (a.semester_id == entry.semester_id
                    and a.subject_id == entry.subject_id
                    and a.teacher_id == entry.teacher_id
                    and a.day == entry.day
                    and a.slot == entry.slot)
        ]
        
        # Only remove from lookup sets if no other allocation uses same slot
        remaining_at_slot = [
            a for a in self.allocations
            if a.day == entry.day and a.slot == entry.slot
        ]
        
        # Remove teacher slot if no other allocation has this teacher at this slot
        if entry.teacher_id is not None and entry.teacher_id in self.teacher_slots:
            if not any(a.teacher_id == entry.teacher_id for a in remaining_at_slot):
                self.teacher_slots[entry.teacher_id].discard(slot_key)
        
        # Remove room slot if no other allocation has this room at this slot
        if entry.room_id is not None and entry.room_id in self.room_slots:
            if not any(a.room_id == entry.room_id for a in remaining_at_slot):
                self.room_slots[entry.room_id].discard(slot_key)
        
        # Remove semester slot if no other allocation for this semester at this slot
        if entry.semester_id in self.semester_slots:
            if not any(a.semester_id == entry.semester_id for a in remaining_at_slot):
                self.semester_slots[entry.semester_id].discard(slot_key)
        
        # Decrement subject daily count
        day_key = (entry.semester_id, entry.day)
        if day_key in self.subject_daily_counts:
            if entry.subject_id in self.subject_daily_counts[day_key]:
                self.subject_daily_counts[day_key][entry.subject_id] = max(
                    0, self.subject_daily_counts[day_key][entry.subject_id] - 1
                )
    
    def is_teacher_free(self, teacher_id: int, day: int, slot: int) -> bool:
        """Check if teacher is free (in-memory check)."""
        if slot in self.global_blocked_slots:
            return False
        if teacher_id not in self.teacher_slots:
            return True
        return (day, slot) not in self.teacher_slots[teacher_id]
    
    def is_teacher_locked_for_elective(self, teacher_id: int, day: int, slot: int) -> bool:
        """Check if teacher is TEMPORARILY locked for elective (in-memory)."""
        lock_key = (day, slot)
        if lock_key in self.elective_teacher_locks:
            return teacher_id in self.elective_teacher_locks[lock_key]
        return False
    
    def is_teacher_eligible(self, teacher_id: int, day: int, slot: int) -> bool:
        """
        STRICT ELIGIBILITY CHECK (READ-ONLY).
        Teacher is eligible ONLY IF:
        1. Teacher is free in that period
        2. Teacher is NOT locked for elective
        """
        if not self.is_teacher_free(teacher_id, day, slot):
            return False
        if self.is_teacher_locked_for_elective(teacher_id, day, slot):
            return False
        return True
    
    def lock_elective_teachers_temporarily(self, day: int, slot: int, teacher_ids: Set[int]):
        """TEMPORARY lock for elective teachers (in-memory only, never saved)."""
        lock_key = (day, slot)
        if lock_key not in self.elective_teacher_locks:
            self.elective_teacher_locks[lock_key] = set()
        self.elective_teacher_locks[lock_key].update(teacher_ids)
    
    def reserve_elective_slot_for_group(
        self, 
        day: int, 
        slot: int, 
        year: int, 
        basket_id: Optional[int],
        teacher_ids: Set[int]
    ):
        """
        Reserve a slot for a specific elective group.
        
        EXTENDED MULTI-GROUP SUPPORT:
        - Each (year, basket_id) group can only use its own reserved slots
        - Different groups within same year get DIFFERENT slots
        - Teacher locks are applied PER GROUP
        
        Args:
            day: Day of week (0-4)
            slot: Period within day (0-6)
            year: Semester year for this group
            basket_id: Elective basket ID (unique per group)
            teacher_ids: Teachers belonging to this group
        """
        slot_key = (day, slot)
        group_key = (year, basket_id)
        ownership_key = (year, day, slot)
        
        # Mark slot ownership
        self.elective_slot_ownership[ownership_key] = group_key
        
        # Track slot for this group
        if group_key not in self.elective_slots_by_group:
            self.elective_slots_by_group[group_key] = []
        if slot_key not in self.elective_slots_by_group[group_key]:
            self.elective_slots_by_group[group_key].append(slot_key)
        
        # Legacy compatibility: also update elective_slots_by_year
        if year not in self.elective_slots_by_year:
            self.elective_slots_by_year[year] = []
        if slot_key not in self.elective_slots_by_year[year]:
            self.elective_slots_by_year[year].append(slot_key)
        
        # Lock teachers for this group at this slot
        self.lock_elective_teachers_temporarily(day, slot, teacher_ids)
        
        # Register these teachers as belonging to this group
        for teacher_id in teacher_ids:
            self.register_teacher_elective_group(teacher_id, year, basket_id)
    
    def is_slot_reserved_for_other_group(
        self, 
        day: int, 
        slot: int, 
        year: int, 
        basket_id: Optional[int]
    ) -> bool:
        """
        Check if a slot is already reserved for a DIFFERENT elective group.
        
        Returns True if slot is owned by another group (different basket_id).
        Returns False if slot is free or owned by the SAME group.
        """
        slot_key = (day, slot)
        ownership_key = (year, day, slot)
        
        if ownership_key not in self.elective_slot_ownership:
            return False  # Slot not reserved by any group
        
        owner_group = self.elective_slot_ownership[ownership_key]
        current_group = (year, basket_id)
        
        # If same group owns it, not reserved for "other" group
        return owner_group != current_group
    
    def register_teacher_elective_group(
        self, 
        teacher_id: int, 
        year: int, 
        basket_id: Optional[int]
    ):
        """Register a teacher as belonging to a specific elective group."""
        if teacher_id not in self.teacher_elective_groups:
            self.teacher_elective_groups[teacher_id] = set()
        self.teacher_elective_groups[teacher_id].add((year, basket_id))
    
    def is_teacher_eligible_for_elective_group(
        self, 
        teacher_id: int, 
        day: int, 
        slot: int,
        year: int,
        basket_id: Optional[int]
    ) -> bool:
        """
        STRICT eligibility check for elective teachers.
        
        A teacher is eligible for an elective slot ONLY IF:
        1. Teacher is free (not already teaching)
        2. Slot is not reserved for a DIFFERENT elective group
        3. Teacher is assigned to THIS elective group
        
        This prevents cross-group teacher conflicts.
        """
        # Basic availability check
        if not self.is_teacher_free(teacher_id, day, slot):
            # Check if busy due to SAME elective basket (Shared/Combined Class Scenario)
            # Find allocations causing busy state
            # Optimization: If teacher_slots has it, verify allocations
            conflicting_allocs = [
                a for a in self.allocations 
                if a.teacher_id == teacher_id and a.day == day and a.slot == slot
            ]
            
            # If conflicts exist, verify ALL match current basket
            if conflicting_allocs:
                all_match_basket = all(
                    a.is_elective and a.elective_basket_id == basket_id 
                    for a in conflicting_allocs
                )
                if not all_match_basket:
                    return False
                # If they match, allow shared teacher
            else:
                # Busy in teacher_slots but no allocations found? 
                # Could be a manual lock or external constraint without details. Fail safe.
                return False
        
        # Check if slot is reserved for another group
        if self.is_slot_reserved_for_other_group(day, slot, year, basket_id):
            return False
        
        # If teacher is locked but for THIS group, they ARE eligible
        slot_key = (day, slot)
        ownership_key = (year, day, slot)
        if ownership_key in self.elective_slot_ownership:
            owner_group = self.elective_slot_ownership[ownership_key]
            if owner_group == (year, basket_id):
                # This slot belongs to our group - teacher eligible if assigned to this group
                return True
        
        # Standard elective lock check
        if self.is_teacher_locked_for_elective(teacher_id, day, slot):
            teacher_groups = self.teacher_elective_groups.get(teacher_id, set())
            if (year, basket_id) not in teacher_groups:
                return False

        return True
    
    def is_room_free(self, room_id: int, day: int, slot: int) -> bool:
        if slot in self.global_blocked_slots:
            return False
        if room_id not in self.room_slots:
            return True
        return (day, slot) not in self.room_slots[room_id]
    
    def is_semester_free(self, semester_id: int, day: int, slot: int) -> bool:
        if slot in self.global_blocked_slots:
            return False
        if semester_id not in self.semester_slots:
            return True
        return (day, slot) not in self.semester_slots[semester_id]
    
    def get_subject_daily_count(self, semester_id: int, day: int, subject_id: int) -> int:
        day_key = (semester_id, day)
        if day_key not in self.subject_daily_counts:
            return 0
        return self.subject_daily_counts[day_key].get(subject_id, 0)
    
    def get_semester_filled_slots(self, semester_id: int) -> int:
        if semester_id not in self.semester_slots:
            return 0
        return len(self.semester_slots[semester_id])


@dataclass
class ElectiveGroup:
    """
    In-memory grouping of electives (READ from existing data).
    
    EXTENDED: Now supports MULTIPLE elective groups per year using basket_id.
    Each (year, basket_id) combination is a distinct elective group.
    """
    year: int
    basket_id: Optional[int] = None  # elective_basket_id - unique per group
    basket_name: str = ""            # Human-readable name (e.g., "Elective-1")
    subjects: List[int] = field(default_factory=list)  # Subject IDs in this group
    teachers: Set[int] = field(default_factory=set)    # Teacher IDs for this group
    classes: List[int] = field(default_factory=list)   # Semester IDs (classes) for this group


# ============================================================
# MAIN GENERATOR CLASS (READ-ONLY DATA ACCESS)
# ============================================================

class TimetableGenerator:
    """
    READ-ONLY Timetable Generation Engine.
    
    GUARANTEES:
    [OK] Existing data is UNTOUCHED
    [OK] Teachers never appear in wrong classes
    [OK] Elective teachers are isolated correctly
    [OK] Elective slots are synchronized
    [OK] Timetable generation is stable (NEVER fails)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.free_period_reasons: List[str] = []
        trace_raw = str(os.getenv("GENERATOR_TRACE", "0")).strip().lower()
        self.trace_enabled = trace_raw in {"1", "true", "yes", "on"}
        # Continuity boundaries are slot indices after which lunch exists.
        # Example: boundary=3 means slot pair (3,4) is NOT continuous.
        self.lab_continuity_boundaries: Set[int] = set()
        self.valid_lab_blocks: List[Tuple[int, int]] = list(VALID_LAB_BLOCKS)

    def _trace(self, message: str):
        """Verbose trace logs (disabled by default for faster generation)."""
        if self.trace_enabled:
            print(message)

    def _summarize_free_period_causes(self) -> List[str]:
        """
        Build concise, user-actionable cause summaries from collected failures.
        Most causes here are data/config constraints rather than code/runtime faults.
        """
        fails = getattr(self, "allocation_failures", []) or []
        if not fails:
            return []

        causes: List[str] = []
        if any("[E-LAB]" in f or "[THEORY] Elective Group" in f for f in fails):
            causes.append("elective basket teacher/slot mapping is constrained (configuration)")
        if any(f.startswith("[LAB]") for f in fails):
            causes.append("some assigned lab teachers/room pairs cannot fit a valid 2-slot block")
        if any("Teacher" in f and "Busy" in f for f in fails):
            causes.append("some teachers are double-booked at remaining candidate slots")
        if any("No Room" in f for f in fails):
            causes.append("room capacity/type availability is insufficient for some slots")
        return causes

    def _build_valid_lab_blocks(self) -> List[Tuple[int, int]]:
        """
        Build valid 2-slot lab pairs that are truly continuous.
        A block crossing lunch boundary is disallowed.
        """
        blocks = [
            (s, s + 1)
            for s in range(SLOTS_PER_DAY - 1)
            if s not in self.lab_continuity_boundaries
        ]
        return blocks or list(VALID_LAB_BLOCKS)
    
    def generate(
        self,
        semester_ids: Optional[List[int]] = None,
        dept_id: Optional[int] = None,
        clear_existing: bool = True,
        semester_type: str = "EVEN"
    ) -> Tuple[bool, str, List[AllocationEntry], float]:
        """
        MAIN ENTRY POINT: Generate timetable for COLLEGE (Multi-Department).
        
        SCALING STRATEGY:
        1. Identify target departments
        2. PHASE 0: Pre-schedule GLOBAL ELECTIVES (Strict Synchronization)
        3. PHASE 1: Generate each department SEQUENTIALLY (Local Optimization)
           - Respects Department-specific rules
           - Loads *other* departments' allocations as READ-ONLY constraints (Global Awareness)
        4. PHASE 2: Global Validation
        """
        start_time = time.time()
        all_allocations: List[AllocationEntry] = []
        messages = []
        
        # ============================================================
        # STEP 0: PREPARE SEMESTER BATCHES (BY DEPARTMENT)
        # ============================================================
        print("\n" + "="*60)
        print("COLLEGE TIMETABLE GENERATION ENGINE (MULTI-DEPT)")
        print("="*60)
        
        target_semesters = self._read_semesters(semester_ids, dept_id, semester_type)
        if not target_semesters:
            return False, "No active semesters found", [], 0.0

        # Reset analysis
        self.allocation_failures = []
        
        # Group by Department (dept_id)
        # Handle None dept_id as valid "General" department
        dept_batches: Dict[Optional[int], List[Semester]] = {}
        for sem in target_semesters:
            sem_dept_id = getattr(sem, 'dept_id', None) # Handle missing attr if schema mismatch
            if sem_dept_id not in dept_batches:
                dept_batches[sem_dept_id] = []
            dept_batches[sem_dept_id].append(sem)
            
        print(f"TARGET: {len(target_semesters)} classes across {len(dept_batches)} departments")

        # When full regeneration is requested, clear allocations for all target classes up-front.
        # This prevents stale allocations from yet-to-be-processed departments from becoming
        # false external constraints during sequential department generation.
        if clear_existing:
            print("DATA: Clearing existing allocations for target classes...")
            self._clear_allocations_only(target_semesters)
        
        # ============================================================
        # PHASE 0: GLOBAL RESOURCE LOADING & ELECTIVE PRE-SCHEDULING
        # ============================================================
        print("\nDATA: Loading global resources (Teachers, Subjects, Rooms)...")
        # Optimization: Load once for all phases
        all_teachers = self._read_teachers()
        all_subjects = self._read_subjects()
        all_rooms = self._read_rooms()
        teacher_assignment_map_global = self._read_teacher_assignment_map()
        
        # Handle Semester Template
        from app.db.models import SemesterTemplate
        import json
        template = self.db.query(SemesterTemplate).filter(SemesterTemplate.semester_type == semester_type).first()
        blocked_slots = set()
        self.lab_continuity_boundaries = set()
        if template:
            # IMPORTANT:
            # break_slots/lunch_slot are visual separators (break AFTER a period), not
            # non-teaching period indices. Blocking them here incorrectly removes valid
            # teaching slots and causes under-allocation.
            #
            # We only block slots if an explicit blocked slot list is present in
            # timing_structure JSON as {"blocked_slots":[...]}.
            try:
                timing = json.loads(template.timing_structure) if template.timing_structure else {}
                explicit_blocked = timing.get("blocked_slots", []) if isinstance(timing, dict) else []
                blocked_slots.update(int(s) for s in explicit_blocked if isinstance(s, int) or (isinstance(s, str) and s.isdigit()))
            except Exception:
                pass
            # Enforce true continuity for labs: never cross lunch boundary.
            if template.lunch_slot is not None:
                self.lab_continuity_boundaries.add(int(template.lunch_slot))
        else:
            blocked_slots = set()
            # Safe default for continuity if no template exists.
            self.lab_continuity_boundaries = {3}

        self.valid_lab_blocks = self._build_valid_lab_blocks()

        print(f"   [TEMPLATE] Using {semester_type} template. Blocked slots: {blocked_slots}")
        print(f"   [LAB] Valid continuous lab blocks: {self.valid_lab_blocks}")
        
        print("\nPHASE 0: PRE-SCHEDULING ELECTIVE BASKETS")
        # Find global elective slots for ALL baskets involved in this run
        global_theory_map, global_lab_map, global_teacher_locks = self._pre_schedule_common_electives(
            target_semesters, 
            all_teachers, 
            all_subjects, 
            teacher_assignment_map_global,
            blocked_slots
        )
        print(f"   [GLOBAL] Locked {len(global_theory_map)} theory groups and {len(global_lab_map)} lab groups")
        
        # 1. OPTIONAL: Clear EVERYTHING if clear_existing=True
        if clear_existing:
            print("   [CLEANUP] Clearing all existing allocations for these semesters...")
            self._clear_allocations_only(target_semesters)
        

        # INITIALIZE CUMULATIVE STATE
        # This state object will persist through all department batches, ensuring 
        # that Dept 2 sees the teachers/rooms already taken by Dept 1.
        cumulative_state = TimetableState()
        cumulative_state.teacher_assignment_map = teacher_assignment_map_global
        if blocked_slots:
            cumulative_state.global_blocked_slots = blocked_slots
            
        # Load external constraints (from semesters NOT in target_semesters)
        self._load_existing_allocations(cumulative_state, exclude_semesters=target_semesters)

        print("\nPHASE 0.5: PRE-SCHEDULING STRUCTURED COMPOSITE BASKETS")
        scb_allocations = self._pre_schedule_scbs(
            target_semesters,
            all_subjects,
            teacher_assignment_map_global,
            cumulative_state,
            all_rooms
        )
        print(f"   [GLOBAL SCB] Locked {len(scb_allocations)} SCB slot entries")
        
        # Add to cumulative state directly
        for entry in scb_allocations:
            cumulative_state.add_allocation(entry, force_parallel=True)
            cumulative_state.mark_slot_as_fixed(entry.semester_id, entry.day, entry.slot)


        # ============================================================
        # EXECUTE GENERATION PER DEPARTMENT
        # ============================================================
        # Sort batches for deterministic order (None last)
        sorted_dept_ids = sorted([d for d in dept_batches.keys() if d is not None])
        if None in dept_batches:
            sorted_dept_ids.append(None)
            
        all_allocations = []
        messages = []
        
        for dept_id in sorted_dept_ids:
            batch_semesters = dept_batches[dept_id]
            dept_name = f"Dept {dept_id}" if dept_id is not None else "General Dept"
            print(f"\nSTARTING PHASE 1: {dept_name} ({len(batch_semesters)} classes)")
            
            try:
                # GENERATE BATCH using cumulative state
                # clear_existing is False because we already cleared everything at start.
                success, msg, batch_allocs = self._generate_department_batch(
                    batch_semesters, 
                    all_teachers,
                    all_subjects,
                    all_rooms,
                    teacher_assignment_map_global,
                    clear_existing=False,
                    global_elective_theory_plan=global_theory_map, 
                    global_elective_lab_plan=global_lab_map,
                    global_teacher_locks=global_teacher_locks,
                    blocked_slots=blocked_slots,
                    state=cumulative_state
                )
                
                all_allocations.extend(batch_allocs)
                messages.append(f"{dept_name}: {msg}")
            except Exception as dept_err:
                import traceback
                traceback.print_exc()
                error_msg = f"{dept_name}: FAILED - {str(dept_err)}"
                print(f"   [ERROR] {error_msg}")
                messages.append(error_msg)
                self.allocation_failures.append(error_msg)
                # Continue with next department - do NOT crash
            
        # ============================================================
        # PHASE 2: FINAL COLLEGE-LEVEL VALIDATION
        # ============================================================
        print("\nPHASE 2: GLOBAL VALIDATION & CONFLICT CHECK...")
        validation_errors = self._validate_global_constraints(all_allocations)
        
        if self.allocation_failures:
            print("\n==============================================")
            print("  ALLOCATION ISSUES / FAILURES:")
            print("==============================================")
            for fail_msg in self.allocation_failures[:30]: # Limit output a bit more than 20
                print(f"  - {fail_msg}")
            if len(self.allocation_failures) > 30:
                print(f"  ... and {len(self.allocation_failures) - 30} more.")
        
        total_time = time.time() - start_time
        success = True
        
        if validation_errors:
            success = False
            print(f"   [WARN] Found {len(validation_errors)} global conflicts!")
            combined_msg = " ; ".join(messages) + f". WARNING: {len(validation_errors)} conflicts."
        else:
            print("   [OK] GLOBAL VALIDATION PASSED. No inter-department conflicts.")
            combined_msg = " ; ".join(messages)

        hard_batch_failures = [m for m in messages if "FAILED -" in m]
        if hard_batch_failures:
            success = False
        if not all_allocations:
            success = False
            if combined_msg:
                combined_msg += " ; No allocations were generated."
            else:
                combined_msg = "No allocations were generated."

        return success, combined_msg, all_allocations, total_time

    def _generate_department_batch(
        self,
        semesters: List[Semester],
        teachers: List[Teacher],
        subjects: List[Subject],
        rooms: List[Room],
        teacher_assignment_map: Dict[Tuple[int, int, str], int],
        clear_existing: bool = True,
        global_elective_theory_plan: Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]] = None,
        global_elective_lab_plan: Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]] = None,
        global_teacher_locks: Dict[int, Set[Tuple[int, int]]] = None,
        blocked_slots: Set[int] = None,
        state: TimetableState = None
    ) -> Tuple[bool, str, List[AllocationEntry]]:
        """
        Internal: Generate for a specific batch of classes (Department).
        """
        if not semesters:
            return True, "No semesters in batch", []
        
        # Initialize State if not provided
        if state is None:
            state = TimetableState()
            state.teacher_assignment_map = teacher_assignment_map
            if blocked_slots:
                state.global_blocked_slots = blocked_slots
            
            # 0. CLEAR EXISTING ALLOCATIONS FOR THIS BATCH (if requested)
            if clear_existing:
                self._clear_allocations_only(semesters)
                
            # 1. LOAD EXISTING ALLOCATIONS (from OTHER departments)
            # This populates state.teacher_slots, state.room_slots, etc.
            self._load_existing_allocations(state, exclude_semesters=semesters)
        else:
            # Using cumulative state - ensure teacher assignments reflect latest
            state.teacher_assignment_map = teacher_assignment_map
            # (Note: we assume clear/load handled at higher level)
            pass
                
        # 2. IDENTIFY ELECTIVE GROUPS
        elective_groups = self._detect_elective_groups(semesters, subjects, teacher_assignment_map)
        
        # Register elective teachers
        for group_key, group in elective_groups.items():
            year, basket_id = group_key
            for teacher_id in group.teachers:
                state.register_teacher_elective_group(teacher_id, year, basket_id)
        
        # Apply global elective teacher slot locks so regular subjects do not consume
        # reserved elective windows needed by other departments.
        if global_teacher_locks:
            for teacher_id, locked in global_teacher_locks.items():
                for day, slot in locked:
                    state.lock_elective_teachers_temporarily(day, slot, {teacher_id})

        # 3. PRE-FILL FIXED SLOTS
        self._prefill_fixed_slots(state, semesters, rooms)
        
        # 4. READ LOCAL MAPS (Batch, Parallel, Rooms)
        room_assignment_map = self._read_room_assignment_map()
        batch_assignment_map = self._read_batch_assignment_map()
        batch_room_map = self._read_batch_room_map()
        parallel_lab_groups = self._read_parallel_lab_groups()
        
        # 4b. READ DEFAULT CLASSROOM MAP (section-wise)
        default_classroom_map = self._read_default_classroom_map(rooms, semesters)
            
        # Helpers
        semester_by_id = {s.id: s for s in semesters}
        lecture_rooms = [r for r in rooms if r.room_type in [RoomType.LECTURE, RoomType.SEMINAR]]
        lab_rooms = [r for r in rooms if r.room_type == RoomType.LAB] or lecture_rooms
        
        # 8. BUILD REQUIREMENTS
        all_requirements = self._build_requirements_readonly(
            semesters, subjects, teacher_assignment_map, room_assignment_map, semester_by_id,
            batch_assignment_map, batch_room_map, parallel_lab_groups
        )
            
        elective_theory_reqs = [r for r in all_requirements if r.is_elective and r.component_type == ComponentType.THEORY]
        elective_lab_reqs = [r for r in all_requirements if r.is_elective and r.component_type == ComponentType.LAB]
        self._trace(f"   [DEBUG] Found {len(elective_lab_reqs)} elective lab requirements for this batch")
        regular_lab_reqs = [r for r in all_requirements if not r.is_elective and r.component_type == ComponentType.LAB and not r.parallel_lab_group]
        parallel_lab_reqs = [r for r in all_requirements if not r.is_elective and r.component_type == ComponentType.LAB and r.parallel_lab_group]
        theory_tutorial_reqs = [r for r in all_requirements if not r.is_elective and r.component_type in [ComponentType.THEORY, ComponentType.TUTORIAL]]
        
        # Detect Global Elective Slots from DB (Legacy/Existing).
        # When regenerating with clear_existing=True, old allocation slots should
        # not constrain fresh planning for this batch.
        existing_global_slots = {}
        if not clear_existing:
            existing_global_slots = self._scan_global_elective_slots(semesters)
        
        # Merge with PLAN
        final_theory_slots = existing_global_slots.copy()
        if global_elective_theory_plan:
            for k, v in global_elective_theory_plan.items():
               final_theory_slots[k] = v 
            print(f"   [PLAN] Applied global elective THEORY plan for {len(global_elective_theory_plan)} groups")
        
        final_lab_slots = existing_global_slots.copy()
        if global_elective_lab_plan:
            for k, v in global_elective_lab_plan.items():
               final_lab_slots[k] = v 
            print(f"   [PLAN] Applied global elective LAB plan for {len(global_elective_lab_plan)} groups")

        # 9. SCHEDULE
        self._schedule_electives_readonly(
            state, elective_theory_reqs, lecture_rooms, semesters, elective_groups, 
            global_slots=final_theory_slots
        )
        self._schedule_elective_labs_readonly(
            state, elective_lab_reqs, lab_rooms, semesters, elective_groups,
            global_slots=final_lab_slots  # Enforce basket-level lab synchronization across departments
        )

        # 8b. Best-effort day-based seminars (soft preference).
        day_based_seminar_reqs = [
            r for r in theory_tutorial_reqs
            if r.academic_component == "seminar" and r.block_size == 7
        ]
        self._schedule_day_based_seminars_readonly(state, day_based_seminar_reqs, lecture_rooms)

        # 8c. DATABASE-BACKED PARALLEL LAB BASKETS
        self._schedule_parallel_lab_baskets_readonly(state, semesters, rooms)

        # 8d. PARALLEL MULTI-SUBJECT LABS (LEGACY, before regular labs)
        if parallel_lab_reqs:
            print(f"   [PARALLEL-MULTI] Scheduling {len(parallel_lab_reqs)} parallel multi-subject lab reqs")
            added, failed_parallel = self._schedule_parallel_multi_subject_labs(state, parallel_lab_reqs, rooms)
            if failed_parallel:
                print(f"   [PARALLEL-MULTI] {len(failed_parallel)} reqs failed parallel scheduling. Falling back to regular.")
                regular_lab_reqs.extend(failed_parallel)

        failed_lab_reqs = self._schedule_labs_readonly(state, regular_lab_reqs, rooms)
        _, free_periods = self._schedule_theory_readonly(state, theory_tutorial_reqs, lecture_rooms, semesters, semester_by_id, default_classroom_map)

        # POST-THEORY LAB RETRY: Displace theory to make room for failed labs.
        # When labs fail initially (teacher/room busy), theory fills ALL slots.
        # This retry swaps out 2 adjacent theory classes and inserts the lab block.
        if failed_lab_reqs:
            self._retry_failed_labs_post_theory(
                state, failed_lab_reqs, rooms, lecture_rooms, semesters,
                semester_by_id, default_classroom_map
            )
        
        # 10. SAVE (New allocations only)
        # Filter allocations to only those for this batch (state might contain pre-filled others)
        batch_sem_ids = {s.id for s in semesters}
        new_allocations = [
            a for a in state.allocations 
            if a.semester_id in batch_sem_ids
        ]
        self._save_allocations_only(new_allocations)
        
        msg = f"Generated {len(new_allocations)} slots"
        if free_periods > 0:
            msg += f" ({free_periods} free)"
            cause_summary = self._summarize_free_period_causes()
            if cause_summary:
                msg += " | causes: " + "; ".join(cause_summary)
        
        
        return True, msg, new_allocations



    def _pre_schedule_common_electives(
        self, 
        target_semesters: List[Semester],
        teachers: List[Teacher],
        subjects: List[Subject],
        teacher_assignment_map: Dict[Tuple[int, int, str], int],
        blocked_slots: Set[int] = None
    ) -> Tuple[Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]], Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]], Dict[int, Set[Tuple[int, int]]]]:
        """
        Pre-calculate elective slots based on Baskets.
        Returns (TheoryPlan, LabPlan, TeacherLocks).
        TeacherLocks: TeacherID -> Set[(Day, Slot)] to reserve global slots.
        """
        if blocked_slots is None:
            blocked_slots = set()
            
        # Deterministic behavior for global electives
        random.seed(42)
        
        elective_groups = self._detect_elective_groups(target_semesters, subjects, teacher_assignment_map)
        
        # PLANS
        global_theory_plan: Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]] = {}
        global_lab_plan: Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]] = {}
        global_teacher_locks: Dict[int, Set[Tuple[int, int]]] = {} # Exported locks
        
        # Track used slots per Year to avoid overlapping different baskets for the same student year
        # (Year, Day, Slot) -> Used
        year_slots_used = set()
        
        # Track usage by teacher to avoid conflicts across different baskets for same teacher
        # TeacherID -> Set[(Day, Slot)]
        internal_teacher_usage: Dict[int, Set[Tuple[int, int]]] = {}
        
        # Sort groups for consistent assignment
        sorted_keys = sorted(elective_groups.keys(), key=lambda x: (x[0] if x[0] is not None else 0, x[1] if x[1] is not None else -1))
        
        # Group by Year
        year_to_baskets: Dict[int, List[Tuple[int, Optional[int]]]] = {}
        for key in sorted_keys:
            year, basket_id = key
            if basket_id is None: continue
            if year not in year_to_baskets: year_to_baskets[year] = []
            year_to_baskets[year].append(key)

        subject_by_id = {s.id: s for s in subjects}

        for year, basket_keys in year_to_baskets.items():
            sorted_basket_keys = sorted(
                basket_keys,
                key=lambda x: (x[1] if x[1] is not None else -1)
            )

            for key in sorted_basket_keys:
                group = elective_groups[key]
                if not group.subjects:
                    continue

                basket_id = key[1]
                basket_teachers = set(group.teachers)

                theory_hours_needed = 0
                lab_blocks_needed = 0
                for sid in group.subjects:
                    s = subject_by_id.get(sid)
                    if not s:
                        continue
                    theory_hours_needed = max(theory_hours_needed, int(getattr(s, "theory_hours_per_week", 0) or 0))
                    lab_blocks_needed = max(lab_blocks_needed, int(getattr(s, "lab_hours_per_week", 0) or 0) // 2)

                if theory_hours_needed == 0 and lab_blocks_needed == 0:
                    theory_hours_needed = 3

                print(
                    f"   [PLAN] Year {year} Basket {basket_id} Global Elective requires: "
                    f"{theory_hours_needed} Theory, {lab_blocks_needed} Lab Blocks"
                )

                theory_slots_target = min(theory_hours_needed, DAYS_PER_WEEK)
                allocated_theory: Set[Tuple[int, int]] = set()
                candidates = [(d, s) for d in range(DAYS_PER_WEEK) for s in range(SLOTS_PER_DAY)]
                random.shuffle(candidates)

                for day, slot in candidates:
                    if len(allocated_theory) >= theory_slots_target:
                        break
                    if slot in blocked_slots:
                        continue

                    # Max one elective theory slot per day for a basket.
                    if day in {d for d, _ in allocated_theory}:
                        continue
                    if (year, day, slot) in year_slots_used:
                        continue

                    teacher_clash = any(
                        (day, slot) in internal_teacher_usage.get(tid, set())
                        for tid in basket_teachers
                    )
                    if teacher_clash:
                        continue

                    allocated_theory.add((day, slot))

                allocated_lab_slots: Set[Tuple[int, int]] = set()
                if lab_blocks_needed > 0:
                    lab_candidates = [
                        (d, s1, s2)
                        for d in range(DAYS_PER_WEEK)
                        for (s1, s2) in self.valid_lab_blocks
                    ]
                    random.shuffle(lab_candidates)

                    theory_days = {d for d, _ in allocated_theory}
                    blocks_found = 0
                    for day, s1, s2 in lab_candidates:
                        if blocks_found >= lab_blocks_needed:
                            break
                        if s1 in blocked_slots or s2 in blocked_slots:
                            continue
                        # CRITICAL RULE: elective labs must not share a day with elective theory.
                        if day in theory_days:
                            continue
                        if (year, day, s1) in year_slots_used or (year, day, s2) in year_slots_used:
                            continue

                        teacher_clash = any(
                            (day, s1) in internal_teacher_usage.get(tid, set())
                            or (day, s2) in internal_teacher_usage.get(tid, set())
                            for tid in basket_teachers
                        )
                        if teacher_clash:
                            continue

                        blocks_found += 1
                        allocated_lab_slots.add((day, s1))
                        allocated_lab_slots.add((day, s2))

                global_theory_plan[key] = allocated_theory
                global_lab_plan[key] = allocated_lab_slots

                for d, s in allocated_theory:
                    year_slots_used.add((year, d, s))
                    for tid in basket_teachers:
                        internal_teacher_usage.setdefault(tid, set()).add((d, s))
                        global_teacher_locks.setdefault(tid, set()).add((d, s))

                for d, s in allocated_lab_slots:
                    year_slots_used.add((year, d, s))
                    for tid in basket_teachers:
                        internal_teacher_usage.setdefault(tid, set()).add((d, s))
                        global_teacher_locks.setdefault(tid, set()).add((d, s))
            
        return global_theory_plan, global_lab_plan, global_teacher_locks

    def _pre_schedule_scbs(
        self,
        target_semesters: List[Semester],
        all_subjects: List[Subject],
        teacher_assignment_map: Dict[Tuple[int, int, str], int],
        state: TimetableState,
        all_rooms: List[Room]
    ):
        import random
        from app.db.models import StructuredCompositeBasket, RoomType, ComponentType, Batch
        
        allocations = []
        
        try:
            active_scbs = self.db.query(StructuredCompositeBasket).all()
        except:
            return []
            
        if not active_scbs:
            return []
            
        subject_by_id = {s.id: s for s in all_subjects}
        room_by_type = {RoomType.LECTURE: [r for r in all_rooms if r.room_type in [RoomType.LECTURE, RoomType.SEMINAR]],
                        RoomType.LAB: [r for r in all_rooms if r.room_type == RoomType.LAB]}
        
        for scb in active_scbs:
            if not scb.departments_involved:
                continue
                
            scb_dept_ids = {d.id for d in scb.departments_involved}
            participating_sems = [
                s for s in target_semesters
                if s.dept_id in scb_dept_ids and s.semester_number == scb.semester
            ]
            
            if not participating_sems:
                continue
                
            theory_h = scb.theory_hours or 0
            lab_h = scb.lab_hours or 0
            lab_cont = scb.continuous_lab_periods or 2
            
            used_days = set()
            
            # --- Schedule Labs ---
            blocks_needed = lab_h // lab_cont if lab_cont > 0 else 0
            for _ in range(blocks_needed):
                valid_days = [d for d in range(5) if d not in used_days]
                random.shuffle(valid_days)
                
                block_found = False
                for d in valid_days:
                    valid_starts = [s for s in range(7 - lab_cont + 1)]
                    random.shuffle(valid_starts)
                    for start_slot in valid_starts:
                        slots_to_check = [start_slot + i for i in range(lab_cont)]
                        
                        # Validate
                        invalid = False
                        for s in slots_to_check:
                            if s in getattr(state, 'global_blocked_slots', set()): invalid = True; break
                            if any(state.is_slot_fixed(sem.id, d, s) for sem in participating_sems): invalid = True; break
                        if invalid or any(s in self.lab_continuity_boundaries for s in slots_to_check[:-1]):
                            continue
                            
                        # Assign lab block
                        used_days.add(d)
                        for sem in participating_sems:
                            batches = []
                            try:
                                batches = self.db.query(Batch).filter(Batch.semester_id == sem.id).all()
                            except:
                                pass
                            
                            for offset in range(lab_cont):
                                slot = start_slot + offset
                                for link in scb.linked_subjects:
                                    subject = subject_by_id.get(link.subject_id)
                                    if not subject or not ("LAB" in subject.name.upper() or subject.lab_hours_per_week > 0):
                                        continue
                                        
                                    tid = teacher_assignment_map.get((sem.id, subject.id, ComponentType.LAB.value))
                                    if not tid: tid = teacher_assignment_map.get((sem.id, subject.id, ComponentType.THEORY.value))
                                    if not tid: continue
                                    
                                    if scb.allow_lab_parallel and batches:
                                        for i, b in enumerate(batches):
                                            room = room_by_type[RoomType.LAB][i % len(room_by_type[RoomType.LAB])] if room_by_type[RoomType.LAB] else None
                                            allocations.append(AllocationEntry(
                                                semester_id=sem.id, subject_id=subject.id, teacher_id=tid, room_id=room.id if room else None,
                                                day=d, slot=slot, component_type=ComponentType.LAB, academic_component="lab", batch_id=b.id
                                            ))
                                    else:
                                        room = random.choice(room_by_type[RoomType.LAB]) if room_by_type[RoomType.LAB] else None
                                        allocations.append(AllocationEntry(
                                            semester_id=sem.id, subject_id=subject.id, teacher_id=tid, room_id=room.id if room else None,
                                            day=d, slot=slot, component_type=ComponentType.LAB, academic_component="lab", batch_id=None
                                        ))
                        block_found = True
                        break
                    if block_found:
                        break
            
            # --- Schedule Theory ---
            for _ in range(theory_h):
                valid_days = [d for d in range(5) if d not in used_days]
                if not valid_days: valid_days = [d for d in range(5)]
                random.shuffle(valid_days)
                
                theory_found = False
                for d in valid_days:
                    valid_slots = [s for s in range(7)]
                    random.shuffle(valid_slots)
                    for s in valid_slots:
                        if s in getattr(state, 'global_blocked_slots', set()): continue
                        if any(state.is_slot_fixed(sem.id, d, s) for sem in participating_sems): continue
                        
                        used_days.add(d)
                        for sem in participating_sems:
                            for link in scb.linked_subjects:
                                subject = subject_by_id.get(link.subject_id)
                                if not subject or ("LAB" in subject.name.upper() or subject.lab_hours_per_week > 0):
                                    continue
                                    
                                tid = teacher_assignment_map.get((sem.id, subject.id, ComponentType.THEORY.value))
                                if not tid: continue
                                room = random.choice(room_by_type[RoomType.LECTURE]) if room_by_type[RoomType.LECTURE] else None
                                allocations.append(AllocationEntry(
                                    semester_id=sem.id, subject_id=subject.id, teacher_id=tid, room_id=room.id if room else None,
                                    day=d, slot=slot, component_type=ComponentType.THEORY, academic_component="theory", batch_id=None
                                ))
                        theory_found = True
                        break
                    if theory_found:
                        break
                        
        return allocations

    def _scan_global_elective_slots(self, current_batch_semesters: List[Semester]) -> Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]]:
        """
        Identify elective slots already decided by OTHER departments.
        Returns: (Year, BasketID) -> Set[(Day, Slot)]
        """
        exclude_ids = [s.id for s in current_batch_semesters]
        
        # Query: Allocations where is_elective=True AND semester_id NOT IN exclude_ids
        allocs = self.db.query(Allocation).join(Semester).filter(
            Allocation.is_elective == True,
            Allocation.semester_id.notin_(exclude_ids)
        ).all()
        
        global_slots = {}
        for a in allocs:
            # Determine year - try specific attr or fallback
            sem = a.semester
            year = getattr(sem, 'year', None)
            if year is None:
                # Infer year from semester number (1-2->1, 3-4->2, etc)
                year = (sem.semester_number + 1) // 2
            
            # Determine basket from allocation (if we tracked it) - checking subject link
            # For now, simplistic assumption: if it's elective, group by year + basket logic
            # Since we don't store basket_id on allocation directly, we rely on subject link?
            # Actually, fixed slots logic might have it.
            # Let's use a loose grouping: Year + Day + Slot
            # Ideally, we should match Basket ID.
            # If IT/AIDS/AIML share 'Open Elective 1', they should align.
            
            # Key: (Year, BasketID)
            # If basket is undetectable, we might have issues. 
            # Current implementation: we assume single basket per year for global sync?
            # Or use a placeholder basket_id=0 if unknown.
            
            # IMPROVEMENT: Try to find basket_id from Subject or FixedSlot?
            basket_id = a.elective_basket_id
            # if a.subject and a.subject.is_elective:
            #     # This depends on how we model electives. 
            #     # If Subjects are linked to Baskets, we can find it.
            #     pass

            # Use (Year, BasketID) as key
            key = (year, basket_id)
            if key not in global_slots:
                global_slots[key] = set()
            
            global_slots[key].add((a.day, a.slot))
            self._trace(f"      [DEBUG-SYNC] Found existing elective slot: Year {year} Basket {basket_id} at {a.day}:{a.slot}")
        
        if global_slots:
            print(f"   [SYNC] Found {sum(len(s) for s in global_slots.values())} global elective slots to align with.")

        return global_slots



    def _load_existing_allocations(self, state: TimetableState, exclude_semesters: List[Semester]):
        """
        Load allocations from DB for classes NOT in the current batch.
        Marks teachers and rooms as BUSY in the state.
        """
        exclude_ids = [s.id for s in exclude_semesters]
        
        # Query existing allocations for OTHER semesters
        existing = self.db.query(Allocation).filter(
            Allocation.semester_id.notin_(exclude_ids)
        ).all()
        
        count = 0
        for alloc in existing:
            # Mark teacher as busy
            if alloc.teacher_id is not None:
                if alloc.teacher_id not in state.teacher_slots:
                    state.teacher_slots[alloc.teacher_id] = set()
                state.teacher_slots[alloc.teacher_id].add((alloc.day, alloc.slot))
            
            # Mark room as busy
            if alloc.room_id is not None:
                if alloc.room_id not in state.room_slots:
                    state.room_slots[alloc.room_id] = set()
                state.room_slots[alloc.room_id].add((alloc.day, alloc.slot))
            
            count += 1
            
        print(f"   [GLOBAL] Loaded {count} external allocations as constraints")

    def _validate_global_constraints(self, allocations: List[AllocationEntry]) -> List[str]:
        """Check for hard conflicts across all generated allocations."""
        errors = []
        # (teacher_id, day, slot) -> list of (sem_id, is_elective, basket_id)
        teacher_map: Dict[Tuple, List[Tuple]] = {}
        room_map = {}    # (room_id, day, slot) -> (sem_id, is_elective, basket_id)
        
        for a in allocations:
            # Teacher Check
            if a.teacher_id is not None:
                t_key = (a.teacher_id, a.day, a.slot)
                if t_key in teacher_map:
                    has_conflict = False
                    for prev_sem, prev_elective, prev_basket in teacher_map[t_key]:
                        # Same semester is OK (batch splitting / parallel labs)
                        if prev_sem == a.semester_id:
                            continue
                        # Both electives in same basket but DIFFERENT semesters = REAL CONFLICT
                        # A teacher can't physically be in two classrooms at once
                        if a.is_elective and prev_elective and a.elective_basket_id == prev_basket:
                            errors.append(
                                f"Teacher Elective Clash: Teacher {a.teacher_id} assigned to "
                                f"Semester {prev_sem} AND Semester {a.semester_id} at Day {a.day} "
                                f"Slot {a.slot} (Basket {a.elective_basket_id})"
                            )
                            has_conflict = True
                        else:
                            errors.append(f"Teacher Clash: ID {a.teacher_id} at {a.day}:{a.slot} (Sem {prev_sem} vs {a.semester_id})")
                            has_conflict = True
                    teacher_map[t_key].append((a.semester_id, a.is_elective, a.elective_basket_id))
                else:
                    teacher_map[t_key] = [(a.semester_id, a.is_elective, a.elective_basket_id)]
            
            # Room Check
            if a.room_id is not None:
                r_key = (a.room_id, a.day, a.slot)
                if r_key in room_map:
                    prev_sem, prev_elective, prev_basket = room_map[r_key]
                    # Skip if both are electives in same basket (different rooms should be used, but flag it only if truly clashing)
                    if a.is_elective and prev_elective and a.elective_basket_id == prev_basket:
                        pass
                    else:
                        errors.append(f"Room Clash: ID {a.room_id} at {a.day}:{a.slot}")
                room_map[r_key] = (a.semester_id, a.is_elective, a.elective_basket_id)
            
        return errors
    
    # ============================================================
    # READ-ONLY DATA ACCESS (NO MODIFICATIONS)
    # ============================================================
    
    def _read_semesters(self, semester_ids: Optional[List[int]], dept_id: Optional[int] = None, semester_type: Optional[str] = None) -> List[Semester]:
        """READ semesters from DB (no modification), filtering by semester type if provided."""
        query = self.db.query(Semester)
        if semester_ids:
            query = query.filter(Semester.id.in_(semester_ids))
        if dept_id:
            query = query.filter(Semester.dept_id == dept_id)
            
        semesters = query.all()
        
        if semester_type:
            if semester_type.upper() == "ODD":
                semesters = [s for s in semesters if (s.semester_number % 2) != 0]
            elif semester_type.upper() == "EVEN":
                semesters = [s for s in semesters if (s.semester_number % 2) == 0]
                
        return semesters
    
    def _read_teachers(self) -> List[Teacher]:
        """READ teachers from DB (no modification)."""
        return self.db.query(Teacher).filter(Teacher.is_active == True).all()
    
    def _read_subjects(self) -> List[Subject]:
        """READ subjects from DB (no modification)."""
        return self.db.query(Subject).all()
    
    def _read_rooms(self) -> List[Room]:
        """READ rooms from DB (no modification)."""
        return self.db.query(Room).filter(Room.is_available == True).all()
    
    def _prefill_fixed_slots(
        self,
        state: TimetableState,
        semesters: List[Semester],
        rooms: List[Room]
    ) -> int:
        """
        PRE-FILL fixed slots into the timetable state.
        
        CRITICAL RULES:
        1. Fixed slots are loaded FIRST before any automatic scheduling
        2. Fixed slots are marked as IMMUTABLE in state.fixed_slots
        3. Teachers assigned to fixed slots are marked as BUSY at those times
        4. Rooms assigned to fixed slots are marked as OCCUPIED
        5. Fixed slots reduce the hour requirements for their subjects
        
        Returns the number of fixed slots loaded.
        """
        sem_ids = [s.id for s in semesters]
        
        # Query all fixed slots for the target semesters
        fixed_slots = self.db.query(FixedSlot).filter(
            FixedSlot.semester_id.in_(sem_ids),
            FixedSlot.locked == True
        ).all()
        
        if not fixed_slots:
            return 0
        
        loaded_count = 0
        room_by_id = {r.id: r for r in rooms}
        
        for fs in fixed_slots:
            comp_label = getattr(fs, "academic_component", None) or (
                fs.component_type.value if fs.component_type else "theory"
            )

            # Find a room if not specified
            room_id = fs.room_id
            if not room_id:
                # Assign first available room based on component type
                if comp_label == "lab":
                    room = next(
                        (r for r in rooms 
                         if r.room_type == RoomType.LAB 
                         and state.is_room_free(r.id, fs.day, fs.slot)),
                        None
                    )
                else:
                    room = next(
                        (r for r in rooms 
                         if r.room_type in [RoomType.LECTURE, RoomType.SEMINAR]
                         and state.is_room_free(r.id, fs.day, fs.slot)),
                        None
                    )
                
                if room:
                    room_id = room.id
                else:
                    # Use any available room
                    room = next(
                        (r for r in rooms if state.is_room_free(r.id, fs.day, fs.slot)),
                        None
                    )
                    room_id = room.id if room else rooms[0].id if rooms else None
            
            if not room_id:
                print(f"   [WARN] No room available for fixed slot: Semester {fs.semester_id}, Day {fs.day}, Slot {fs.slot}")
                continue
            
            # Create an allocation entry for this fixed slot
            entry = AllocationEntry(
                semester_id=fs.semester_id,
                subject_id=fs.subject_id,
                teacher_id=fs.teacher_id,
                room_id=room_id,
                day=fs.day,
                slot=fs.slot,
                component_type=fs.component_type,
                academic_component=comp_label,
                is_lab_continuation=fs.is_lab_continuation,
                is_elective=fs.is_elective,
                elective_basket_id=fs.elective_basket_id
            )
            
            # Add to state - this marks teacher/room/semester as occupied
            if state.add_allocation(entry):
                # Mark this slot as FIXED (immutable)
                state.mark_slot_as_fixed(fs.semester_id, fs.day, fs.slot)
                loaded_count += 1
                
                print(
                    f"   FIXED: Class {fs.semester_id}, Day {fs.day}, Slot {fs.slot} -> Subject {fs.subject_id} (Teacher {fs.teacher_id})"
                )
            else:
                print(f"   [WARN] Could not add fixed slot: Semester {fs.semester_id}, Day {fs.day}, Slot {fs.slot} (slot conflict)")
        
        return loaded_count
    
    def _read_teacher_assignment_map(self) -> Dict[Tuple[int, int, str], int]:
        """
        READ existing teacher assignments from ClassSubjectTeacher.
        
        Priority order:
        1) Explicit class-subject-component assignments (ClassSubjectTeacher)
        2) Subject-qualified teacher mapping (teacher_subjects) for missing keys only

        This preserves explicit class assignments while avoiding large "no mapping"
        gaps for classes where fixed class-level mapping is incomplete.
        """
        assignment_map: Dict[Tuple[int, int, str], int] = {}
        additional_teachers_by_key: Dict[Tuple[int, int, str], Set[int]] = {}

        # Build quick lookups for balancing candidate selection.
        teacher_max_hours: Dict[int, int] = {}
        for t in self.db.query(Teacher).all():
            teacher_max_hours[t.id] = int(getattr(t, "max_hours_per_week", 20) or 20)

        subject_by_id: Dict[int, Subject] = {s.id: s for s in self.db.query(Subject).all()}

        def _component_hours(subject_id: int, component_key: str) -> int:
            subj = subject_by_id.get(subject_id)
            if not subj:
                return 1
            if component_key == ComponentType.LAB.value:
                return max(1, int(getattr(subj, "lab_hours_per_week", 0) or 0))
            if component_key == ComponentType.TUTORIAL.value:
                return max(1, int(getattr(subj, "tutorial_hours_per_week", 0) or 0))
            # THEORY + extended theory-like components.
            theory_like = (
                int(getattr(subj, "theory_hours_per_week", 0) or 0)
                + int(getattr(subj, "project_hours_per_week", 0) or 0)
                + int(getattr(subj, "report_hours_per_week", 0) or 0)
                + int(getattr(subj, "self_study_hours_per_week", 0) or 0)
                + int(getattr(subj, "seminar_hours_per_week", 0) or 0)
            )
            return max(1, theory_like)

        # STEP 1: READ explicit non-batch class assignments (PRIMARY SOURCE).
        # If multiple teachers are mapped for the same key (append-mode history),
        # choose one deterministically using load-aware balancing.
        explicit_assignments = self.db.query(ClassSubjectTeacher).filter(
            ClassSubjectTeacher.batch_id.is_(None)
        ).order_by(ClassSubjectTeacher.id.asc()).all()

        candidates_by_key: Dict[Tuple[int, int, str], List[int]] = {}
        for assignment in explicit_assignments:
            key = (assignment.semester_id, assignment.subject_id, assignment.component_type.value)
            if key not in candidates_by_key:
                candidates_by_key[key] = []
            if assignment.teacher_id not in candidates_by_key[key]:
                candidates_by_key[key].append(assignment.teacher_id)

        projected_hours_by_teacher: Dict[int, int] = {}

        # Harder keys first (fewer candidates, then higher weekly component hours).
        ordered_keys = sorted(
            candidates_by_key.keys(),
            key=lambda k: (
                len(candidates_by_key[k]),
                -_component_hours(k[1], k[2]),
                k[0],
                k[1],
                k[2],
            ),
        )

        for key in ordered_keys:
            sem_id, subj_id, comp_key = key
            candidates = candidates_by_key[key]
            req_hours = _component_hours(subj_id, comp_key)

            best_teacher = None
            best_score = None
            for idx, candidate_id in enumerate(candidates):
                current_load = projected_hours_by_teacher.get(candidate_id, 0)
                max_hours = teacher_max_hours.get(candidate_id, 20)
                overflow_after = max(0, (current_load + req_hours) - max_hours)
                # Prefer no-overflow, then lowest projected load, then stable candidate order.
                score = (overflow_after, current_load, idx)
                if best_score is None or score < best_score:
                    best_score = score
                    best_teacher = candidate_id

            assignment_map[key] = best_teacher
            projected_hours_by_teacher[best_teacher] = projected_hours_by_teacher.get(best_teacher, 0) + req_hours

            if len(candidates) > 1:
                additional_teachers_by_key[key] = set(candidates) - {best_teacher}
                self._trace(
                    f"   READ [LOCKED-BALANCED]: Class {sem_id}, Subject {subj_id}, {comp_key} "
                    f"-> Teacher {best_teacher} (candidates={len(candidates)})"
                )
            else:
                self._trace(
                    f"   READ [LOCKED]: Class {sem_id}, Subject {subj_id}, {comp_key} -> Teacher {best_teacher}"
                )

        # STEP 2: Batch assignments can still provide a deterministic teacher fallback
        # for components that have no whole-class mapping.
        batch_assignments = self.db.query(ClassSubjectTeacher).filter(
            ClassSubjectTeacher.batch_id.isnot(None)
        ).order_by(ClassSubjectTeacher.id.asc()).all()
        for assignment in batch_assignments:
            key = (assignment.semester_id, assignment.subject_id, assignment.component_type.value)
            if key not in assignment_map:
                assignment_map[key] = assignment.teacher_id
            else:
                additional_teachers_by_key.setdefault(key, set()).add(assignment.teacher_id)

        # STEP 3: REMOVED - Global teacher_subjects fallback.
        # Previously this called _read_teacher_subjects_mapping_strict() which used
        # the teacher_subjects table (subject_id -> teacher_id with NO class filter).
        # This caused Teacher X assigned to Subject Y for Class A to bleed into
        # Class D's timetable. Now only ClassSubjectTeacher (STEP 1 & 2) mappings
        # are used. If no explicit class+subject mapping exists, the slot is left
        # unassigned rather than pulling a teacher from another class.
        #
        # Priority resolution order:
        #   1) Locked teacher assignment (ClassSubjectTeacher) - STEP 1 above
        #   2) Batch teacher assignment (ClassSubjectTeacher with batch_id) - STEP 2 above
        #   3) Elective teachers (handled in elective scheduling)
        #   4) Parallel basket teachers (handled in parallel lab scheduling)
        #   5) Unassigned (leave empty - DO NOT pull from another class)

        if additional_teachers_by_key:
            extra_count = sum(len(v) for v in additional_teachers_by_key.values())
            print(
                f"   [INFO] Detected {extra_count} additional append-mode assignment row(s). "
                "Balanced primary mapping selected per class-subject-component."
            )

        print(f"   TOTAL LOCKED MAPPINGS: {len(assignment_map)}")
        return assignment_map

    def _read_room_assignment_map(self) -> Dict[Tuple[int, int, str], int]:
        """
        READ optional room preferences from ClassSubjectTeacher.

        Returns:
            (semester_id, subject_id, component_type) -> room_id
        """
        room_map: Dict[Tuple[int, int, str], int] = {}

        try:
            assignments = self.db.query(ClassSubjectTeacher).filter(
                ClassSubjectTeacher.room_id.isnot(None),
                ClassSubjectTeacher.batch_id.is_(None)
            ).all()
        except Exception as e:
            print(f"   [WARN] Could not read room preferences (schema may be old): {e}")
            return {}

        for assignment in assignments:
            if not assignment.room_id:
                continue
            key = (assignment.semester_id, assignment.subject_id, assignment.component_type.value)
            room_map[key] = assignment.room_id
            self._trace(
                f"   READ [ROOM]: Class {assignment.semester_id}, Subject {assignment.subject_id}, "
                f"{assignment.component_type.value} -> Room {assignment.room_id}"
            )

        if room_map:
            print(f"   TOTAL ROOM PREFERENCES: {len(room_map)}")

        return room_map

    def _read_default_classroom_map(
        self, rooms: List[Room], semesters: List[Semester]
    ) -> Dict[int, int]:
        """
        READ default classroom assignments.

        For each semester whose (dept_id, year, section) matches a Room with
        is_default_classroom=True, record the mapping semester_id -> room_id.
        
        Supports multi-department rooms: checks both legacy dept_id and
        the room_departments junction (via room.departments relationship).

        Used during theory scheduling to prioritize section classrooms.
        """
        # Build lookup: (dept_id, year, section) -> room
        default_rooms: Dict[Tuple, Room] = {}
        for r in rooms:
            if getattr(r, 'is_default_classroom', False) and getattr(r, 'assigned_year', None) and getattr(r, 'assigned_section', None):
                # Collect all dept_ids this room belongs to
                dept_ids_set = set()
                if r.dept_id:
                    dept_ids_set.add(r.dept_id)
                # Also check the departments relationship (multi-dept)
                if hasattr(r, 'departments') and r.departments:
                    for dept in r.departments:
                        dept_ids_set.add(dept.id)
                
                for did in dept_ids_set:
                    key = (did, r.assigned_year, r.assigned_section)
                    default_rooms[key] = r

        if not default_rooms:
            return {}

        # Map semesters to their default classroom
        sem_default: Dict[int, int] = {}  # semester_id -> room_id
        for sem in semesters:
            key = (sem.dept_id, sem.year, sem.section)
            room = default_rooms.get(key)
            if room and room.is_available and room.capacity >= sem.student_count:
                sem_default[sem.id] = room.id
                print(
                    f"   DEFAULT CLASSROOM: {sem.name} (Year {sem.year} Section {sem.section}) -> {room.name}"
                )

        if sem_default:
            print(f"   TOTAL DEFAULT CLASSROOMS MAPPED: {len(sem_default)}")
        return sem_default


    def _read_batch_assignment_map(self) -> Dict[Tuple[int, int, str], Dict[int, int]]:
        """
        READ batch-specific teacher assignments from ClassSubjectTeacher.
        Returns: (semester_id, subject_id, component_type) -> {batch_id -> teacher_id}
        """
        batch_map: Dict[Tuple[int, int, str], Dict[int, int]] = {}
        
        try:
            assignments = self.db.query(ClassSubjectTeacher).filter(
                ClassSubjectTeacher.batch_id.isnot(None)
            ).all()
        except Exception as e:
            print(f"   [WARN] Could not read batch assignments: {e}")
            return {}
            
        duplicate_batch_rows = 0
        for assignment in assignments:
            key = (assignment.semester_id, assignment.subject_id, assignment.component_type.value)
            if key not in batch_map:
                batch_map[key] = {}
            if assignment.batch_id in batch_map[key]:
                duplicate_batch_rows += 1
                continue
            batch_map[key][assignment.batch_id] = assignment.teacher_id
            
        print(f"   TOTAL BATCH-SPECIFIC MAPPINGS: {len(batch_map)}")
        if duplicate_batch_rows:
            print(
                f"   [INFO] Ignored {duplicate_batch_rows} duplicate batch assignment row(s) "
                "to keep deterministic mapping."
            )
        return batch_map

    def _read_batch_room_map(self) -> Dict[Tuple[int, int, str], Dict[int, int]]:
        """
        READ batch-specific room assignments from ClassSubjectTeacher.
        Returns: (semester_id, subject_id, component_type) -> {batch_id -> room_id}
        """
        room_map: Dict[Tuple[int, int, str], Dict[int, int]] = {}
        
        try:
            assignments = self.db.query(ClassSubjectTeacher).filter(
                ClassSubjectTeacher.batch_id.isnot(None),
                ClassSubjectTeacher.room_id.isnot(None)
            ).all()
        except Exception as e:
            print(f"   [WARN] Could not read batch room assignments: {e}")
            return {}
            
        duplicate_batch_room_rows = 0
        for assignment in assignments:
            key = (assignment.semester_id, assignment.subject_id, assignment.component_type.value)
            if key not in room_map:
                room_map[key] = {}
            if assignment.batch_id in room_map[key]:
                duplicate_batch_room_rows += 1
                continue
            room_map[key][assignment.batch_id] = assignment.room_id
            
        print(f"   TOTAL BATCH-SPECIFIC ROOMS: {len(room_map)}")
        if duplicate_batch_room_rows:
            print(
                f"   [INFO] Ignored {duplicate_batch_room_rows} duplicate batch room mapping row(s) "
                "to keep deterministic mapping."
            )
        return room_map
    
    def _read_parallel_lab_groups(self) -> Dict[Tuple[int, int, str], str]:
        """
        READ parallel_lab_group from ClassSubjectTeacher.
        Returns: (semester_id, subject_id, component_type) -> parallel_lab_group string
        """
        result: Dict[Tuple[int, int, str], str] = {}
        
        try:
            assignments = self.db.query(ClassSubjectTeacher).filter(
                ClassSubjectTeacher.parallel_lab_group.isnot(None)
            ).all()
        except Exception as e:
            print(f"   [WARN] Could not read parallel lab groups: {e}")
            return {}
        
        for a in assignments:
            key = (a.semester_id, a.subject_id, a.component_type.value)
            result[key] = a.parallel_lab_group
        
        if result:
            print(f"   [PARALLEL] Found {len(result)} parallel lab group entries")
        return result

    def _read_teacher_subjects_mapping_strict(self) -> Dict[Tuple[int, int, str], int]:
        """
        STRICT READ from teacher_subjects table.
        
        CRITICAL RULES:
        - Only use teachers EXPLICITLY assigned to subjects
        - If multiple teachers exist, use the FIRST one (deterministic order by ID)
        - DO NOT guess, rotate, or infer teachers
        """
        assignment_map: Dict[Tuple[int, int, str], int] = {}
        
        # Get all semester-subject assignments
        semesters = self.db.query(Semester).all()
        
        # Get teacher-subject relationships (ordered by teacher_id for determinism)
        teacher_subject_rows = self.db.execute(
            teacher_subjects.select().order_by(teacher_subjects.c.teacher_id)
        ).fetchall()
        
        # Build subject -> teacher list (ordered)
        subject_to_teachers: Dict[int, List[int]] = {}
        for row in teacher_subject_rows:
            if row.subject_id not in subject_to_teachers:
                subject_to_teachers[row.subject_id] = []
            subject_to_teachers[row.subject_id].append(row.teacher_id)
        
        for semester in semesters:
            for subject in semester.subjects:
                # Get teachers for this subject
                teachers_for_subject = subject_to_teachers.get(subject.id, [])
                
                if not teachers_for_subject:
                    self._trace(f"   [NO TEACHER] {subject.code} in {semester.name}: Subject NOT eligible for scheduling")
                    continue
                
                # Use the first assigned teacher (deterministic, ordered by ID)
                teacher_id = teachers_for_subject[0]
                
                # Determine components
                components = self._get_subject_components(subject)
                
                for spec in components:
                    comp_type = spec["component_type"]
                    key = (semester.id, subject.id, comp_type.value)
                    if key not in assignment_map:
                        assignment_map[key] = teacher_id
                        self._trace(
                            f"   READ [INFERRED]: Class {semester.id}, Subject {subject.id} ({subject.code}), {comp_type.value} -> Teacher {teacher_id}"
                        )
        
        return assignment_map
    
    def _detect_elective_groups(
        self,
        semesters: List[Semester],
        subjects: List[Subject],
        teacher_map: Dict[Tuple[int, int, str], int]
    ) -> Dict[Tuple[int, Optional[int]], ElectiveGroup]:
        """
        DETECT elective groups from existing data (READ-ONLY).
        
        EXTENDED: Now groups electives by (year, basket_id) tuple.
        This allows MULTIPLE elective groups within the same year.
        
        Example:
          - (5, 1) -> Elective Group 1 for 5th semester
          - (5, 2) -> Elective Group 2 for 5th semester
          - (5, 3) -> Elective Group 3 for 5th semester
        
        Each group is scheduled INDEPENDENTLY with its own time slot.
        """
        groups: Dict[Tuple[int, Optional[int]], ElectiveGroup] = {}
        
        # Build basket name lookup from ElectiveBasket table
        basket_names: Dict[int, str] = {}
        basket_semester_map: Dict[int, Set[int]] = {}
        try:
            from app.db.models import ElectiveBasket
            from sqlalchemy.orm import joinedload
            baskets = self.db.query(ElectiveBasket).options(
                joinedload(ElectiveBasket.subjects),
                joinedload(ElectiveBasket.participating_semesters)
            ).all()
            for basket in baskets:
                basket_names[basket.id] = basket.name or f"Elective-{basket.id}"
                sem_ids = {s.id for s in (basket.participating_semesters or [])}
                if sem_ids:
                    basket_semester_map[basket.id] = sem_ids
        except Exception:
            baskets = []
            pass  # ElectiveBasket table may not exist

        target_sem_ids = {s.id for s in semesters}
        
        for semester in semesters:
            year = getattr(semester, 'year', None) or ((semester.semester_number + 1) // 2)
            
            for subject in semester.subjects:
                # DETECT elective flag from existing data
                is_elective = (
                    subject.is_elective or 
                    subject.subject_type == SubjectType.ELECTIVE or
                    subject.elective_basket_id is not None
                )
                
                if is_elective:
                    # Use basket_id as the group identifier (can be None)
                    basket_id = subject.elective_basket_id
                    if basket_id is not None:
                        allowed_semesters = basket_semester_map.get(basket_id, set())
                        if allowed_semesters and semester.id not in allowed_semesters:
                            # Ignore off-basket class mappings for this elective subject.
                            continue
                    group_key = (year, basket_id)
                    
                    # Create group if doesn't exist
                    if group_key not in groups:
                        basket_name = basket_names.get(basket_id, f"Elective-{basket_id}" if basket_id else "Elective")
                        groups[group_key] = ElectiveGroup(
                            year=year,
                            basket_id=basket_id,
                            basket_name=basket_name
                        )
                    
                    # Add subject to group
                    if subject.id not in groups[group_key].subjects:
                        groups[group_key].subjects.append(subject.id)
                    
                    # Add class to group
                    if semester.id not in groups[group_key].classes:
                        groups[group_key].classes.append(semester.id)
                    
                    # Get teacher from existing mapping
                    for comp_type in ['theory', 'lab', 'tutorial']:
                        key = (semester.id, subject.id, comp_type)
                        if key in teacher_map:
                            groups[group_key].teachers.add(teacher_map[key])

        # Also include basket-driven electives even if subject-semester mapping is incomplete.
        for basket in baskets:
            if not basket.subjects or not basket.participating_semesters:
                continue
            basket_id = basket.id
            for sem in basket.participating_semesters:
                if sem.id not in target_sem_ids:
                    continue
                year = getattr(sem, 'year', None) or ((sem.semester_number + 1) // 2)
                group_key = (year, basket_id)
                if group_key not in groups:
                    basket_name = basket_names.get(basket_id, f"Elective-{basket_id}")
                    groups[group_key] = ElectiveGroup(
                        year=year,
                        basket_id=basket_id,
                        basket_name=basket_name
                    )
                if sem.id not in groups[group_key].classes:
                    groups[group_key].classes.append(sem.id)
                for subject in basket.subjects:
                    if subject.id not in groups[group_key].subjects:
                        groups[group_key].subjects.append(subject.id)
                    # STRICT: Only use explicit class-subject mapping (ClassSubjectTeacher).
                    # REMOVED: subject.teachers fallback (global lookup, no class filter).
                    for comp_type in ['theory', 'lab', 'tutorial']:
                        key = (sem.id, subject.id, comp_type)
                        if key in teacher_map:
                            groups[group_key].teachers.add(teacher_map[key])

        # Include semesters inferred from explicit ClassSubjectTeacher mappings for electives.
        sem_by_id = {s.id: s for s in semesters}
        subject_by_id = {s.id: s for s in subjects}
        for (sem_id, subj_id, comp_type), teacher_id in teacher_map.items():
            if sem_id not in sem_by_id or subj_id not in subject_by_id:
                continue
            subject = subject_by_id[subj_id]
            is_elective = (
                subject.is_elective or
                subject.subject_type == SubjectType.ELECTIVE or
                subject.elective_basket_id is not None
            )
            if not is_elective:
                continue
            sem = sem_by_id[sem_id]
            year = getattr(sem, 'year', None) or ((sem.semester_number + 1) // 2)
            basket_id = subject.elective_basket_id
            if basket_id is not None:
                allowed_semesters = basket_semester_map.get(basket_id, set())
                if allowed_semesters and sem_id not in allowed_semesters:
                    # Ignore stray ClassSubjectTeacher rows that cross basket boundaries.
                    continue
            group_key = (year, basket_id)
            if group_key not in groups:
                basket_name = basket_names.get(basket_id, f"Elective-{basket_id}" if basket_id else "Elective")
                groups[group_key] = ElectiveGroup(
                    year=year,
                    basket_id=basket_id,
                    basket_name=basket_name
                )
            if sem_id not in groups[group_key].classes:
                groups[group_key].classes.append(sem_id)
            if subj_id not in groups[group_key].subjects:
                groups[group_key].subjects.append(subj_id)
            if teacher_id:
                groups[group_key].teachers.add(teacher_id)
        
        return groups
    
    def _get_subject_components(self, subject: Subject) -> List[dict]:
        """
        READ subject components (no modification).

        Returns a list of component specs that are timetable-visible when hours > 0.
        Each spec includes:
        - component_type: scheduling category (theory/lab/tutorial)
        - academic_component: UI/report label (project/report/seminar/internship/etc)
        - hours_per_week
        - block_size (1/2/7)
        - preferred_room_types
        - teacher_key: which existing mapping key to use ("theory"/"lab"/"tutorial")
        """
        specs: List[dict] = []

        lecture_room_types = [RoomType.LECTURE, RoomType.SEMINAR]

        theory_hours = int(getattr(subject, 'theory_hours_per_week', 0) or 0)
        lab_hours = int(getattr(subject, 'lab_hours_per_week', 0) or 0)
        tutorial_hours = int(getattr(subject, 'tutorial_hours_per_week', 0) or 0)

        # Legacy compatibility overrides (deprecated subject_type values)
        if subject.subject_type == SubjectType.LAB:
            lab_hours = int(subject.weekly_hours or 0)
            theory_hours = 0
            tutorial_hours = 0
        elif subject.subject_type == SubjectType.TUTORIAL:
            tutorial_hours = int(subject.weekly_hours or 0)
            theory_hours = 0
            lab_hours = 0
        else:
            # If component fields are empty, treat legacy weekly_hours as theory
            if theory_hours == 0 and lab_hours == 0 and tutorial_hours == 0:
                theory_hours = int(subject.weekly_hours or 0)

        if theory_hours > 0:
            specs.append({
                "component_type": ComponentType.THEORY,
                "academic_component": "theory",
                "hours_per_week": theory_hours,
                "block_size": 1,
                "preferred_room_types": lecture_room_types,
                "teacher_key": "theory",
            })
        if lab_hours > 0:
            specs.append({
                "component_type": ComponentType.LAB,
                "academic_component": "lab",
                "hours_per_week": lab_hours,
                "block_size": 2,
                "preferred_room_types": [RoomType.LAB],
                "teacher_key": "lab",
            })
        if tutorial_hours > 0:
            specs.append({
                "component_type": ComponentType.TUTORIAL,
                "academic_component": "tutorial",
                "hours_per_week": tutorial_hours,
                "block_size": 1,
                "preferred_room_types": lecture_room_types,
                "teacher_key": "tutorial",
            })

        # Extended academic components (optional)
        project_hours = int(getattr(subject, "project_hours_per_week", 0) or 0)
        if project_hours > 0:
            bs = int(getattr(subject, "project_block_size", 1) or 1)
            bs = 2 if bs >= 2 else 1
            specs.append({
                "component_type": ComponentType.LAB if bs == 2 else ComponentType.THEORY,
                "academic_component": "project",
                "hours_per_week": project_hours,
                "block_size": bs,
                "preferred_room_types": lecture_room_types,
                "teacher_key": "theory",
            })

        report_hours = int(getattr(subject, "report_hours_per_week", 0) or 0)
        if report_hours > 0:
            bs = int(getattr(subject, "report_block_size", 1) or 1)
            bs = 2 if bs >= 2 else 1
            specs.append({
                "component_type": ComponentType.LAB if bs == 2 else ComponentType.THEORY,
                "academic_component": "report",
                "hours_per_week": report_hours,
                "block_size": bs,
                "preferred_room_types": lecture_room_types,
                "teacher_key": "theory",
            })

        seminar_hours = int(getattr(subject, "self_study_hours_per_week", 0) or 0)
        if seminar_hours > 0:
            specs.append({
                "component_type": ComponentType.THEORY,
                "academic_component": "seminar",
                "hours_per_week": seminar_hours,
                "block_size": 1,
                "preferred_room_types": lecture_room_types,
                "teacher_key": "theory",
            })

        internship_hours = int(getattr(subject, "seminar_hours_per_week", 0) or 0)
        if internship_hours > 0:
            day_based = bool(getattr(subject, "seminar_day_based", False))
            bs = int(getattr(subject, "seminar_block_size", 2) or 2)
            # Prefer day-based if enabled; generator will soft-fallback if not possible.
            if day_based:
                bs = 7
            else:
                bs = 2 if bs >= 2 else 1
            specs.append({
                "component_type": ComponentType.LAB if bs == 2 else ComponentType.THEORY,
                "academic_component": "internship",
                "hours_per_week": internship_hours,
                "block_size": bs,
                "preferred_room_types": lecture_room_types,
                "teacher_key": "theory",
            })

        return specs
    
    def _build_requirements_readonly(
        self,
        semesters: List[Semester],
        subjects: List[Subject],
        teacher_map: Dict[Tuple[int, int, str], int],
        room_map: Dict[Tuple[int, int, str], int],
        semester_by_id: Dict[int, Semester],
        batch_map: Dict[Tuple[int, int, str], Dict[int, int]] = None,
        batch_room_map: Dict[Tuple[int, int, str], Dict[int, int]] = None,
        parallel_lab_group_map: Dict[Tuple[int, int, str], str] = None
    ) -> List[ComponentRequirement]:
        """Build requirements using ONLY existing mappings."""
        requirements = []
        batch_map = batch_map or {}
        batch_room_map = batch_room_map or {}
        parallel_lab_group_map = parallel_lab_group_map or {}

        # REMOVED: Cross-semester teacher pool for elective fallback.
        # Previously this aggregated teachers from ALL classes for the same subject
        # and allowed any class to pick from the pool. This caused teachers assigned
        # to Subject Y for Class A to appear in Class D's timetable.
        # Now elective teacher lookup is strictly class-scoped via ClassSubjectTeacher.

        # Build per-semester subject list, augmented by elective basket participation.
        semester_subjects_map: Dict[int, List[Subject]] = {}
        semester_subject_ids: Dict[int, Set[int]] = {}
        subject_by_id = {s.id: s for s in subjects}
        for semester in semesters:
            subj_list = list(getattr(semester, "subjects", []) or [])
            semester_subjects_map[semester.id] = subj_list
            semester_subject_ids[semester.id] = {s.id for s in subj_list}

        baskets = []
        basket_semester_map: Dict[int, Set[int]] = {}
        try:
            from app.db.models import ElectiveBasket
            from sqlalchemy.orm import joinedload
            baskets = self.db.query(ElectiveBasket).options(
                joinedload(ElectiveBasket.subjects),
                joinedload(ElectiveBasket.participating_semesters)
            ).all()
            for basket in baskets:
                sem_ids = {s.id for s in (basket.participating_semesters or [])}
                if sem_ids:
                    basket_semester_map[basket.id] = sem_ids
        except Exception as e:
            print(f"   [WARN] Elective basket sync skipped: {e}")
            baskets = []

        # Include subjects that have explicit ClassSubjectTeacher mappings for this semester.
        for (sem_id, subj_id, _), teacher_id in teacher_map.items():
            if sem_id in semester_subjects_map and subj_id in subject_by_id:
                subj = subject_by_id[subj_id]
                basket_id = getattr(subj, "elective_basket_id", None)
                if basket_id is not None:
                    allowed_semesters = basket_semester_map.get(basket_id, set())
                    if allowed_semesters and sem_id not in allowed_semesters:
                        # Ignore off-basket mappings to keep elective classes strict.
                        continue
                if subj_id not in semester_subject_ids[sem_id]:
                    semester_subject_ids[sem_id].add(subj_id)
                    semester_subjects_map[sem_id].append(subject_by_id[subj_id])

        target_sem_ids = set(semester_subjects_map.keys())
        for basket in baskets:
            if not basket.subjects:
                continue
            for sem in basket.participating_semesters or []:
                if sem.id not in target_sem_ids:
                    continue
                for subj in basket.subjects:
                    if subj.id not in semester_subject_ids[sem.id]:
                        semester_subject_ids[sem.id].add(subj.id)
                        semester_subjects_map[sem.id].append(subj)

        missing_elective_teachers: List[Tuple[int, str, str]] = []
        
        for semester in semesters:
            year = getattr(semester, 'year', None) or ((semester.semester_number + 1) // 2)
            
            for subject in semester_subjects_map.get(semester.id, []):
                is_elective = (
                    subject.is_elective or 
                    subject.subject_type == SubjectType.ELECTIVE or
                    subject.elective_basket_id is not None
                )
                if is_elective and subject.elective_basket_id is not None:
                    allowed_semesters = basket_semester_map.get(subject.elective_basket_id, set())
                    if allowed_semesters and semester.id not in allowed_semesters:
                        # Keep elective requirements constrained to declared basket classes.
                        continue
                
                components = self._get_subject_components(subject)

                for spec in components:
                    comp_type: ComponentType = spec["component_type"]
                    hours: int = spec["hours_per_week"]
                    academic_component: str = spec["academic_component"]
                    block_size: int = spec.get("block_size", 1)
                    preferred_room_types = spec.get("preferred_room_types")
                    teacher_key = spec.get("teacher_key", comp_type.value)
                    
                    # Key for looking up assignments
                    lookup_key = (semester.id, subject.id, teacher_key)

                    # 1. Read PRIMARY teacher (whole class)
                    teacher_id = teacher_map.get(lookup_key)
                    if teacher_id is None:
                        # Fallback checks
                        for fallback_key in ["theory", "tutorial", "lab"]:
                            teacher_id = teacher_map.get((semester.id, subject.id, fallback_key))
                            if teacher_id is not None:
                                break

                    # REMOVED: Cross-class elective teacher fallback.
                    # Previously if a class had no direct mapping for an elective
                    # subject, teachers from OTHER classes were reused. This caused
                    # teachers to appear in wrong timetables.
                    # Now: if no explicit ClassSubjectTeacher mapping exists for
                    # this class + subject, the slot is left unassigned.
                    if teacher_id is None and is_elective:
                        print(
                            f"   [STRICT] No teacher for elective {subject.code} in "
                            f"Class {semester.id} ({semester.name}) - leaving unassigned"
                        )
                    
                    # 2. Read BATCH teachers (split class)
                    batch_allocs = batch_map.get(lookup_key, {})
                    batch_room_allocs = batch_room_map.get(lookup_key, {})

                    # Read optional room preference
                    preferred_room_id = room_map.get(lookup_key)

                    # VALIDITY CHECK:
                    # Requirement exists if:
                    # A. There is a primary teacher assigned OR
                    # B. There are batch assignments (parallel scheduling)
                    if teacher_id is not None or batch_allocs:
                        req = ComponentRequirement(
                            semester_id=semester.id,
                            subject_id=subject.id,
                            subject_name=subject.name,
                            subject_code=subject.code,
                            component_type=comp_type,
                            academic_component=academic_component,
                            hours_per_week=hours,
                            block_size=block_size,
                            preferred_room_types=preferred_room_types,
                            min_room_capacity=semester.student_count,
                            is_elective=is_elective,
                            elective_basket_id=subject.elective_basket_id,
                            year=year,
                            assigned_teacher_id=teacher_id, # Can be None if only batches exist
                            assigned_room_id=preferred_room_id,
                            batch_allocations=batch_allocs,
                            batch_room_allocations=batch_room_allocs,
                            parallel_lab_group=parallel_lab_group_map.get(lookup_key),
                            priority_weight=getattr(subject, 'computed_priority_score', 0) or 0
                        )
                        requirements.append(req)
                    else:
                        print(f"   [NO MAPPING] {subject.code} - {academic_component} in {semester.name}")
                        if is_elective:
                            missing_elective_teachers.append((semester.id, subject.code, subject.name))

        if missing_elective_teachers:
            unique_missing = {(s, c) for (s, c, _) in missing_elective_teachers}
            print(f"   [WARN] {len(unique_missing)} elective subjects missing teacher assignments (not scheduled)")
        
        print(f"   Built {len(requirements)} requirements from existing mappings")
        return requirements
    
    # ============================================================
    # ELECTIVE SCHEDULING (WITH TEMPORARY LOCKS)
    # ============================================================
    
    def _schedule_electives_readonly(
        self,
        state: TimetableState,
        elective_reqs: List[ComponentRequirement],
        rooms: List[Room],
        semesters: List[Semester],
        elective_groups: Dict[Tuple[int, Optional[int]], ElectiveGroup],
        global_slots: Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]] = None
    ) -> int:
        """
        Schedule elective theory with COMMON SLOTS per basket.

        Behavior:
        - Slots are synchronized across all classes in the elective group.
        - In each class/slot, schedule ONE elective option (not every basket subject).
        - Different classes may get different elective subjects at the same slot.
        """
        if not elective_reqs:
            print("      No elective requirements to schedule")
            return 0
        
        allocations_added = 0
        room_by_id = {r.id: r for r in rooms}
        
        # Group requirements by (year, basket_id) to match elective_groups
        by_group: Dict[Tuple[int, Optional[int]], List[ComponentRequirement]] = {}
        for req in elective_reqs:
            group_key = (req.year, req.elective_basket_id)
            if group_key not in by_group:
                by_group[group_key] = []
            by_group[group_key].append(req)
        
        print(f"      Processing {len(by_group)} elective group(s)")
        
        # Process each elective group INDEPENDENTLY
        for group_key, group_reqs in by_group.items():
            if not group_reqs:
                continue
            
            year, basket_id = group_key
            
            # Get the group definition
            group = elective_groups.get(group_key)
            if not group:
                continue
            
            group_classes = group.classes
            group_teachers = group.teachers
            group_name = group.basket_name
            
            print(f"\n      Elective Group '{group_name}' (Year {year}, Basket {basket_id}):")

            # Group requirements by academic component to avoid collisions and ensure visibility
            reqs_by_component: Dict[str, List[ComponentRequirement]] = {}
            for req in group_reqs:
                comp_label = req.academic_component or req.component_type.value
                if comp_label not in reqs_by_component:
                    reqs_by_component[comp_label] = []
                reqs_by_component[comp_label].append(req)

            for comp_label, comp_reqs in reqs_by_component.items():
                if not comp_reqs:
                    continue

                print(f"        Component: {comp_label}")

                # Group requirements by class (semester)
                reqs_by_class: Dict[int, List[ComponentRequirement]] = {}
                for req in comp_reqs:
                    if req.semester_id not in reqs_by_class:
                        reqs_by_class[req.semester_id] = []
                    reqs_by_class[req.semester_id].append(req)

                # Only classes that actually have mapped requirements can be scheduled.
                scheduled_classes = [sid for sid in group_classes if sid in reqs_by_class]
                if not scheduled_classes:
                    continue

                # Hours needed is common per class for this component.
                hours_needed = max((r.hours_per_week for r in comp_reqs), default=0)

                # Track remaining hours per class and keep scheduling until each class
                # reaches its target. This prevents ghost/partial scheduling.
                class_hours_remaining: Dict[int, int] = {
                    sem_id: hours_needed for sem_id in scheduled_classes
                }

                # Track daily allocations for this component-group to enforce distribution
                group_daily_counts = {d: 0 for d in range(DAYS_PER_WEEK)}

                # Map each class to a specific distinct elective subject/teacher for the whole week
                class_to_req: Dict[int, ComponentRequirement] = {}
                used_teachers_for_map = set()
                sorted_classes = sorted(scheduled_classes, key=lambda sid: len(set(r.assigned_teacher_id for r in reqs_by_class.get(sid, []) if r.assigned_teacher_id)))
                for sem_id in sorted_classes:
                    r_candidates = reqs_by_class.get(sem_id, [])
                    selected = next((r for r in r_candidates if r.assigned_teacher_id and r.assigned_teacher_id not in used_teachers_for_map), None)
                    if not selected and r_candidates:
                        selected = r_candidates[0]
                    class_to_req[sem_id] = selected
                    if selected and selected.assigned_teacher_id:
                        used_teachers_for_map.add(selected.assigned_teacher_id)

                # DETERMINE SLOT ORDER
                slot_candidates = []
                is_global_sync = False

                if global_slots and group_key in global_slots:
                    predefined_slots = list(global_slots[group_key])
                    predefined_slots.sort()
                    predefined_set = set(predefined_slots)
                    fallback_slots = [s for s in self._get_randomized_slots() if s not in predefined_set]
                    slot_candidates = predefined_slots + fallback_slots
                    is_global_sync = True
                    print(
                        f"        [SYNC] Preferred {len(predefined_slots)} global slots "
                        f"(with {len(fallback_slots)} fallback slots)"
                    )
                else:
                    slot_candidates = self._get_randomized_slots()

                # Pre-index existing elective allocations for this basket by slot to
                # avoid repeatedly scanning full state on each candidate slot.
                basket_slot_teacher_rooms: Dict[Tuple[int, int], Dict[int, int]] = {}
                for a in state.allocations:
                    if (
                        a.is_elective
                        and a.elective_basket_id == basket_id
                        and a.teacher_id is not None
                        and a.room_id is not None
                    ):
                        basket_slot_teacher_rooms.setdefault((a.day, a.slot), {})[a.teacher_id] = a.room_id

                # Hard day-level exclusion (lab already scheduled for this basket/day).
                lab_days_for_group = {
                    a.day for a in state.allocations
                    if (
                        a.is_elective
                        and a.elective_basket_id == basket_id
                        and a.semester_id in scheduled_classes
                        and a.component_type == ComponentType.LAB
                    )
                }

                for day, slot in slot_candidates:
                    if all(v <= 0 for v in class_hours_remaining.values()):
                        break

                    # EXTENDED: For 2nd Year (Semesters 3 & 4), enforce MAX 1 elective theory per day
                    is_second_year = (year in [3, 4])
                    if is_second_year and group_daily_counts[day] >= 1:
                        continue

                    # Check slot is not reserved by a DIFFERENT elective group
                    if state.is_slot_reserved_for_other_group(day, slot, year, basket_id):
                        continue

                    # HARD RULE: elective theory and elective lab for the same basket
                    # must not be on the same day.
                    if day in lab_days_for_group:
                        continue

                    # Allow partial class coverage in this slot; classes that cannot be
                    # scheduled here are retried in later slots.
                    active_classes = [
                        sid for sid in scheduled_classes
                        if class_hours_remaining.get(sid, 0) > 0
                        and state.is_semester_free(sid, day, slot)
                    ]
                    if not active_classes:
                        continue

                    # For this slot, schedule one elective option per class.
                    slot_allocs = []
                    used_rooms = set()
                    shared_room_by_teacher: Dict[int, Room] = {}
                    # Track teachers already used in THIS slot to prevent same teacher
                    # being assigned to multiple departments/classes simultaneously
                    slot_used_teachers: Set[int] = set()
                    slot_teacher_rooms = basket_slot_teacher_rooms.get((day, slot), {})
                    for tid, rid in slot_teacher_rooms.items():
                        room_obj = room_by_id.get(rid)
                        if room_obj:
                            shared_room_by_teacher[tid] = room_obj
                        slot_used_teachers.add(tid)

                    for sem_id in active_classes:
                        preferred_req = class_to_req.get(sem_id)
                        if not preferred_req:
                            continue
                        req_candidates = [preferred_req] + [
                            r for r in reqs_by_class.get(sem_id, [])
                            if r is not preferred_req
                        ]

                        req = None
                        teacher_id = None
                        for cand in req_candidates:
                            tid = cand.assigned_teacher_id
                            if not tid or tid in slot_used_teachers:
                                continue
                            if state.is_teacher_eligible_for_elective_group(tid, day, slot, year, basket_id):
                                req = cand
                                teacher_id = tid
                                break
                        if not req or not teacher_id:
                            continue
                        class_to_req[sem_id] = req

                        room = None
                        used_shared_room = False

                        # Room selection for valid teacher allocation only.
                        existing_alloc = next((r for r_q, r, tid, _ in slot_allocs if tid == teacher_id), None)
                        room = existing_alloc
                        used_shared_room = bool(existing_alloc)
                        if not room:
                            room = shared_room_by_teacher.get(teacher_id)
                            if room:
                                used_shared_room = True

                        if not room and req.assigned_room_id and req.assigned_room_id not in used_rooms:
                            r_obj = room_by_id.get(req.assigned_room_id)
                            if r_obj and r_obj.capacity >= req.min_room_capacity and state.is_room_free(r_obj.id, day, slot) and (not req.preferred_room_types or r_obj.room_type in req.preferred_room_types):
                                room = r_obj

                        if not room:
                            for r in rooms:
                                if r.id not in used_rooms and r.capacity >= req.min_room_capacity and state.is_room_free(r.id, day, slot):
                                    if req.preferred_room_types and r.room_type not in req.preferred_room_types:
                                        continue
                                    room = r
                                    break
                        if not room:
                            continue

                        if not used_shared_room:
                            used_rooms.add(room.id)
                        slot_used_teachers.add(teacher_id)
                        slot_allocs.append((req, room, teacher_id, sem_id))

                    if not slot_allocs:
                        continue

                    state.reserve_elective_slot_for_group(day, slot, year, basket_id, group_teachers)
                    group_daily_counts[day] += 1

                    for req, room, teacher_id, sem_id in slot_allocs:
                        entry = AllocationEntry(
                            semester_id=sem_id,
                            subject_id=req.subject_id,
                            teacher_id=teacher_id,
                            room_id=room.id,
                            day=day,
                            slot=slot,
                            component_type=req.component_type,
                            academic_component=req.academic_component,
                            is_elective=True,
                            elective_basket_id=basket_id
                        )
                        state.add_allocation(entry, force_parallel=True)
                        allocations_added += 1
                        if teacher_id is not None and room is not None:
                            basket_slot_teacher_rooms.setdefault((day, slot), {})[teacher_id] = room.id
                        class_hours_remaining[sem_id] = max(
                            0, class_hours_remaining.get(sem_id, 0) - 1
                        )

                target_class_hours = len(scheduled_classes) * hours_needed
                missing_class_hours = sum(class_hours_remaining.values())
                scheduled_class_hours = target_class_hours - missing_class_hours
                print(
                    f"        Scheduled {scheduled_class_hours}/{target_class_hours} class-hours for {comp_label}"
                )
                if missing_class_hours > 0:
                    representative_req = comp_reqs[0] if comp_reqs else None
                    if representative_req:
                        fail_msg = (
                            f"[THEORY] Elective Group '{group_name}' (Year {year}, Basket {basket_id}) "
                            f"Component '{comp_label}': Unscheduled {missing_class_hours} class-hour(s)."
                        )
                        print(f"        {fail_msg}")
                        self.allocation_failures.append(fail_msg)
        
        return allocations_added
    
    def _schedule_elective_labs_readonly(
        self,
        state: TimetableState,
        elective_reqs: List[ComponentRequirement],
        rooms: List[Room],
        semesters: List[Semester],
        elective_groups: Dict[Tuple[int, Optional[int]], ElectiveGroup],
        global_slots: Dict[Tuple[int, Optional[int]], Set[Tuple[int, int]]] = None
    ) -> int:
        """
        Schedule elective labs as atomic 2-period blocks.

        KEY DESIGN: All subjects in the same basket are ALTERNATIVES
        (students pick one). They MUST be scheduled at the SAME time slots
        across classes, while each class gets one elective option per block.
        """
        if not elective_reqs:
            print("      No elective lab requirements to schedule.")
            return 0

        allocations_added = 0
        room_by_id = {r.id: r for r in rooms}

        # Group requirements by (year, basket_id)
        reqs_by_group: Dict[Tuple[int, Optional[int]], List[ComponentRequirement]] = {}
        for req in elective_reqs:
            key = (req.year, req.elective_basket_id)
            if key not in reqs_by_group:
                reqs_by_group[key] = []
            reqs_by_group[key].append(req)

        print(f"      [E-LAB] Grouped {len(elective_reqs)} reqs into {len(reqs_by_group)} basket groups")

        for group_key, group_reqs in reqs_by_group.items():
            year, basket_id = group_key
            group = elective_groups.get(group_key)
            if not group:
                print(f"      [WARN] No elective group definition for {group_key}")
                continue

            group_classes = group.classes
            group_teachers = group.teachers

            # Blocks needed per class = max across all subjects in basket.
            blocks_needed = max((r.hours_per_week for r in group_reqs), default=0) // 2
            if blocks_needed == 0:
                continue

            # Sub-group requirements by class for one-option-per-class selection.
            reqs_by_class: Dict[int, List[ComponentRequirement]] = {}
            for req in group_reqs:
                if req.semester_id not in reqs_by_class:
                    reqs_by_class[req.semester_id] = []
                reqs_by_class[req.semester_id].append(req)

            scheduled_classes = [sid for sid in group_classes if sid in reqs_by_class]
            if not scheduled_classes:
                continue

            unique_subject_ids = sorted({r.subject_id for r in group_reqs})
            print(
                f"      [E-LAB] Basket {basket_id} (Year {year}): "
                f"{len(unique_subject_ids)} subjects, {len(scheduled_classes)} classes, need {blocks_needed} block(s)"
            )

            # Global Slot Restriction
            allowed_slots = global_slots.get(group_key) if global_slots else None

            # Build candidates
            candidates = []
            if allowed_slots:
                for d in range(DAYS_PER_WEEK):
                    for s1, s2 in self.valid_lab_blocks:
                        if (d, s1) in allowed_slots and (d, s2) in allowed_slots:
                            candidates.append((d, s1, s2))
                candidates.sort()
                preferred_set = set(candidates)
                fallback = [
                    (d, s1, s2)
                    for d in range(DAYS_PER_WEEK)
                    for s1, s2 in self.valid_lab_blocks
                    if (d, s1, s2) not in preferred_set
                ]
                random.shuffle(fallback)
                candidates.extend(fallback)
            else:
                candidates = [(d, s1, s2) for d in range(DAYS_PER_WEEK) for s1, s2 in self.valid_lab_blocks]
                random.shuffle(candidates)

            # Map each class to a specific distinct elective subject/teacher.
            class_to_req: Dict[int, ComponentRequirement] = {}
            used_teachers_for_map = set()
            sorted_classes = sorted(
                scheduled_classes,
                key=lambda sid: len(set(r.assigned_teacher_id for r in reqs_by_class.get(sid, []) if r.assigned_teacher_id))
            )
            for sem_id in sorted_classes:
                r_candidates = reqs_by_class.get(sem_id, [])
                selected = next(
                    (r for r in r_candidates if r.assigned_teacher_id and r.assigned_teacher_id not in used_teachers_for_map),
                    None
                )
                if not selected and r_candidates:
                    selected = r_candidates[0]
                class_to_req[sem_id] = selected
                if selected and selected.assigned_teacher_id:
                    used_teachers_for_map.add(selected.assigned_teacher_id)

            class_blocks_remaining: Dict[int, int] = {
                sem_id: blocks_needed for sem_id in scheduled_classes
            }
            blocks_used_slots = 0

            # Pre-index existing elective allocations for this basket by slot to
            # avoid repeatedly scanning full state inside candidate loops.
            basket_slot_teacher_rooms: Dict[Tuple[int, int], Dict[int, int]] = {}
            for a in state.allocations:
                if (
                    a.is_elective
                    and a.elective_basket_id == basket_id
                    and a.teacher_id is not None
                    and a.room_id is not None
                ):
                    basket_slot_teacher_rooms.setdefault((a.day, a.slot), {})[a.teacher_id] = a.room_id

            # Hard day-level exclusion (theory already scheduled for this basket/day).
            theory_days_for_group = {
                a.day for a in state.allocations
                if (
                    a.is_elective
                    and a.elective_basket_id == basket_id
                    and a.semester_id in scheduled_classes
                    and a.component_type == ComponentType.THEORY
                )
            }

            for day, s1, s2 in candidates:
                if all(v <= 0 for v in class_blocks_remaining.values()):
                    break

                # Slot not reserved for another group.
                if (
                    state.is_slot_reserved_for_other_group(day, s1, year, basket_id)
                    or state.is_slot_reserved_for_other_group(day, s2, year, basket_id)
                ):
                    continue

                # Elective labs and elective theory for the same basket should not be
                # placed on the same day.
                if day in theory_days_for_group:
                    continue

                active_classes = [
                    sem_id for sem_id in scheduled_classes
                    if class_blocks_remaining.get(sem_id, 0) > 0
                    and state.is_semester_free(sem_id, day, s1)
                    and state.is_semester_free(sem_id, day, s2)
                ]
                if not active_classes:
                    continue

                all_allocations_to_make = []
                rooms_used_here = set()
                shared_lab_room_by_teacher: Dict[int, Room] = {}
                slot_used_teachers: Set[int] = set()

                # If a teacher already has an elective allocation for this basket in this
                # exact lab block, allow classes to join that same teacher+room block.
                slot_map_1 = basket_slot_teacher_rooms.get((day, s1), {})
                slot_map_2 = basket_slot_teacher_rooms.get((day, s2), {})
                slot_used_teachers.update(slot_map_1.keys())
                slot_used_teachers.update(slot_map_2.keys())
                for tid in slot_used_teachers:
                    rid_1 = slot_map_1.get(tid)
                    rid_2 = slot_map_2.get(tid)
                    if rid_1 is not None and rid_1 == rid_2:
                        room_obj = room_by_id.get(rid_1)
                        if room_obj:
                            shared_lab_room_by_teacher[tid] = room_obj

                for sem_id in active_classes:
                    preferred_req = class_to_req.get(sem_id)
                    if not preferred_req:
                        continue
                    req_candidates = [preferred_req] + [
                        r for r in reqs_by_class.get(sem_id, [])
                        if r is not preferred_req
                    ]

                    req = None
                    teacher_id = None
                    for cand in req_candidates:
                        tid = cand.assigned_teacher_id
                        if not tid or tid in slot_used_teachers:
                            continue
                        if (
                            state.is_teacher_eligible_for_elective_group(tid, day, s1, year, basket_id)
                            and state.is_teacher_eligible_for_elective_group(tid, day, s2, year, basket_id)
                        ):
                            req = cand
                            teacher_id = tid
                            break
                    if not req or not teacher_id:
                        continue
                    class_to_req[sem_id] = req

                    room = None
                    used_shared_room = False

                    # Room selection for valid teacher allocation only.
                    existing_alloc = next((r for _, r, tid, _ in all_allocations_to_make if tid == teacher_id), None)
                    room = existing_alloc
                    used_shared_room = bool(existing_alloc)
                    if not room:
                        room = shared_lab_room_by_teacher.get(teacher_id)
                        if room:
                            used_shared_room = True

                    if not room and req.assigned_room_id and req.assigned_room_id not in rooms_used_here:
                        r_obj = room_by_id.get(req.assigned_room_id)
                        if (
                            r_obj
                            and r_obj.capacity >= req.min_room_capacity
                            and state.is_room_free(r_obj.id, day, s1)
                            and state.is_room_free(r_obj.id, day, s2)
                            and (not req.preferred_room_types or r_obj.room_type in req.preferred_room_types)
                        ):
                            room = r_obj

                    if not room:
                        for r in rooms:
                            if (
                                r.id not in rooms_used_here
                                and r.capacity >= req.min_room_capacity
                                and state.is_room_free(r.id, day, s1)
                                and state.is_room_free(r.id, day, s2)
                            ):
                                if req.preferred_room_types and r.room_type not in req.preferred_room_types:
                                    continue
                                room = r
                                break

                    if not room:
                        continue
                    if not used_shared_room:
                        rooms_used_here.add(room.id)
                    slot_used_teachers.add(teacher_id)

                    all_allocations_to_make.append((req, room, teacher_id, sem_id))

                if not all_allocations_to_make:
                    continue

                # Commit one elective lab option per schedulable class at this block.
                for req, room, teacher_id, sem_id in all_allocations_to_make:
                    state.add_allocation(AllocationEntry(
                        semester_id=sem_id,
                        subject_id=req.subject_id,
                        teacher_id=teacher_id,
                        room_id=room.id,
                        day=day,
                        slot=s1,
                        component_type=req.component_type,
                        academic_component=req.academic_component,
                        is_lab_continuation=False,
                        is_elective=True,
                        elective_basket_id=basket_id
                    ))
                    state.add_allocation(AllocationEntry(
                        semester_id=sem_id,
                        subject_id=req.subject_id,
                        teacher_id=teacher_id,
                        room_id=room.id,
                        day=day,
                        slot=s2,
                        component_type=req.component_type,
                        academic_component=req.academic_component,
                        is_lab_continuation=True,
                        is_elective=True,
                        elective_basket_id=basket_id
                    ), force_parallel=True)
                    allocations_added += 2
                    if teacher_id is not None and room is not None:
                        basket_slot_teacher_rooms.setdefault((day, s1), {})[teacher_id] = room.id
                        basket_slot_teacher_rooms.setdefault((day, s2), {})[teacher_id] = room.id
                    class_blocks_remaining[sem_id] = max(0, class_blocks_remaining.get(sem_id, 0) - 1)

                # Mark slot ownership.
                state.elective_slot_ownership[(year, day, s1)] = (year, basket_id)
                state.elective_slot_ownership[(year, day, s2)] = (year, basket_id)
                state.reserve_elective_slot_for_group(day, s1, year, basket_id, group_teachers)
                state.reserve_elective_slot_for_group(day, s2, year, basket_id, group_teachers)

                blocks_used_slots += 1
                print(f"        [OK] Lab block at Day {day} Slots {s1}-{s2} ({len(all_allocations_to_make)} classes)")

            target_class_blocks = len(scheduled_classes) * blocks_needed
            missing_class_blocks = sum(class_blocks_remaining.values())
            scheduled_class_blocks = target_class_blocks - missing_class_blocks
            if missing_class_blocks > 0:
                fail_msg = (
                    f"[E-LAB] Basket {basket_id} (Year {year}): Unscheduled "
                    f"{missing_class_blocks}/{target_class_blocks} class-block(s). Checked {len(candidates)} slots."
                )
                if allowed_slots:
                    fail_msg += f" (Restricted by GLOBAL plan: {allowed_slots})"
                print(f"        {fail_msg}")
                self.allocation_failures.append(fail_msg)
            else:
                print(
                    f"        [OK] Basket {basket_id} completed "
                    f"{scheduled_class_blocks}/{target_class_blocks} class-blocks "
                    f"using {blocks_used_slots} synchronized slot(s)."
                )

        return allocations_added

    # ============================================================
    # PARALLEL LAB BASKET SCHEDULING (DATABASE-BACKED SYSTEM)
    # ============================================================
    
    def _schedule_parallel_lab_baskets_readonly(
        self,
        state: TimetableState,
        semesters: List[Semester],
        rooms: List[Room]
    ) -> int:
        from app.db.models import ParallelLabBasket, ParallelLabBasketSubject, Batch
        from sqlalchemy.orm import joinedload
        
        allocations_added = 0
        semester_ids = [s.id for s in semesters]
        
        # Map of (dept_id, year, section) -> Semester
        sem_map = {}
        for s in semesters:
            if hasattr(s, 'dept_id') and hasattr(s, 'year') and hasattr(s, 'section'):
                sem_map[(s.dept_id, s.year, s.section)] = s
                
        if not sem_map: return 0
                
        dept_ids = list(set(s.dept_id for s in semesters if hasattr(s, 'dept_id')))
        if not dept_ids: return 0
        
        baskets = self.db.query(ParallelLabBasket).options(
            joinedload(ParallelLabBasket.basket_subjects).joinedload(ParallelLabBasketSubject.subject)
        ).filter(
            ParallelLabBasket.dept_id.in_(dept_ids)
        ).all()
        
        if not baskets: return 0
        
        print(f"   [DB-PARALLEL-LAB] Processing {len(baskets)} parallel lab baskets")
        
        for basket in baskets:
            sem = sem_map.get((basket.dept_id, basket.year, basket.section))
            if not sem:
                continue # Basket not for this batch
                
            blocks_needed = 2
            blocks_scheduled = 0
            
            candidates = [(d, s1, s2) for d in range(DAYS_PER_WEEK) for s1, s2 in self.valid_lab_blocks]
            random.shuffle(candidates)
            
            scheduled_days = set()

            for day, s1, s2 in candidates:
                if blocks_scheduled >= blocks_needed:
                    break
                    
                # Try to distribute across different days
                if day in scheduled_days and blocks_scheduled < blocks_needed:
                    continue
                    
                if not (state.is_semester_free(sem.id, day, s1) and state.is_semester_free(sem.id, day, s2)):
                    continue
                if state.is_slot_fixed(sem.id, day, s1) or state.is_slot_fixed(sem.id, day, s2):
                    continue
                    
                resources_ok = True
                for b_sub in basket.basket_subjects:
                    if not (state.is_teacher_free(b_sub.teacher_id, day, s1) and state.is_teacher_free(b_sub.teacher_id, day, s2)):
                        resources_ok = False
                        break
                    if b_sub.room_id and not (state.is_room_free(b_sub.room_id, day, s1) and state.is_room_free(b_sub.room_id, day, s2)):
                        resources_ok = False
                        break
                if not resources_ok:
                    continue
                    
                # Allocate
                for b_sub in basket.basket_subjects:
                    batch_id = None
                    b = self.db.query(Batch).filter_by(semester_id=sem.id, name=b_sub.batch_name).first()
                    if b:
                        batch_id = b.id
                    
                    alloc_room_id = b_sub.room_id
                    if not alloc_room_id:
                        lab_rooms = [r for r in rooms if r.room_type == RoomType.LAB]
                        if lab_rooms:
                            alloc_room_id = lab_rooms[0].id
                        elif rooms:
                            alloc_room_id = rooms[0].id
                    
                    for i, slot in enumerate([s1, s2]):
                        state.add_allocation(AllocationEntry(
                            semester_id=sem.id,
                            subject_id=b_sub.subject_id,
                            teacher_id=b_sub.teacher_id,
                            room_id=alloc_room_id,
                            day=day,
                            slot=slot,
                            component_type=ComponentType.LAB,
                            academic_component="lab",
                            is_lab_continuation=(i > 0),
                            is_elective=False,
                            batch_id=batch_id
                        ), force_parallel=True)
                        allocations_added += 1
                
                blocks_scheduled += 1
                scheduled_days.add(day)
                print(f"      [OK] Scheduled DB-Basket {basket.id} block {blocks_scheduled} at Day {day} Slots {s1}-{s2} for {len(basket.basket_subjects)} subjects")
            
            if blocks_scheduled < blocks_needed:
                msg = f"[DB-PARALLEL-LAB] Failed to schedule all blocks for Basket {basket.id} ({blocks_scheduled}/{blocks_needed} blocks)"
                print(f"      {msg}")
                self.allocation_failures.append(msg)
                
        return allocations_added
    # ============================================================

    def _schedule_parallel_multi_subject_labs(
        self,
        state: TimetableState,
        parallel_lab_reqs: List[ComponentRequirement],
        rooms: List[Room]
    ) -> Tuple[int, List[ComponentRequirement]]:
        """
        Schedule PARALLEL multi-subject labs (co-scheduled in the same time slot
        with different teachers/rooms for different lab subjects).

        IMPROVEMENTS:
        - Slot scoring: prefer days with fewer existing allocations
        - Room matching: sort by best-fit capacity, prefer labs
        - Retry with relaxed room type on failure
        - Better diagnostics
        """
        if not parallel_lab_reqs:
            return 0, []

        allocations_added = 0
        failed_reqs = []

        # Group by (semester_id, parallel_lab_group)
        from collections import defaultdict
        groups: Dict[Tuple[int, str], List[ComponentRequirement]] = defaultdict(list)
        for req in parallel_lab_reqs:
            key = (req.semester_id, req.parallel_lab_group)
            groups[key].append(req)

        # Pre-sort rooms by type preference (labs first, then by capacity ascending for best-fit)
        lab_room_types = {RoomType.LAB}
        computer_lab_type = getattr(RoomType, "COMPUTER_LAB", None)
        if computer_lab_type is not None:
            lab_room_types.add(computer_lab_type)
        lab_rooms_sorted = sorted(
            [r for r in rooms if r.room_type in lab_room_types],
            key=lambda r: r.capacity
        )
        all_rooms_sorted = sorted(rooms, key=lambda r: r.capacity)

        for group_key, group_reqs in groups.items():
            semester_id, group_name = group_key
            n_subjects = len(group_reqs)
            print(f"      [PARALLEL-GROUP] {group_name}: {n_subjects} subjects (sem={semester_id})")

            # Validate: no duplicate teachers within the group
            teacher_ids = [r.assigned_teacher_id for r in group_reqs if r.assigned_teacher_id]
            if len(set(teacher_ids)) != len(teacher_ids):
                print(f"         [ERROR] Duplicate teacher in parallel group {group_name} - skipping group")
                failed_reqs.extend(group_reqs)
                continue

            # All subjects in the group need the same number of lab blocks
            max_blocks = max(r.hours_per_week // 2 for r in group_reqs)
            blocks_scheduled = 0

            # Build slot candidates and SCORE them (prefer emptier days)
            lab_slots = [(d, block) for d in range(DAYS_PER_WEEK) for block in self.valid_lab_blocks]

            def slot_score(day_block):
                day, (s1, s2) = day_block
                # Count existing allocations on this day for this semester
                day_load = sum(
                    1 for slot_n in range(SLOTS_PER_DAY)
                    if not state.is_semester_free(semester_id, day, slot_n)
                )
                return day_load  # lower is better

            lab_slots.sort(key=slot_score)
            # Add slight randomness within same-score groups for variety
            import itertools
            scored = [(slot_score(s), s) for s in lab_slots]
            final_slots = []
            for _, group_iter in itertools.groupby(scored, key=lambda x: x[0]):
                bucket = [item[1] for item in group_iter]
                random.shuffle(bucket)
                final_slots.extend(bucket)

            for day, (start_slot, end_slot) in final_slots:
                if blocks_scheduled >= max_blocks:
                    break

                # 1. Check semester is free for both slots
                if not (state.is_semester_free(semester_id, day, start_slot) and
                        state.is_semester_free(semester_id, day, end_slot)):
                    continue

                # 2. Check ALL teachers are eligible
                teachers_ok = True
                for req in group_reqs:
                    tid = req.assigned_teacher_id
                    if not tid:
                        teachers_ok = False
                        break
                    if not (state.is_teacher_eligible(tid, day, start_slot) and
                            state.is_teacher_eligible(tid, day, end_slot)):
                        teachers_ok = False
                        break
                if not teachers_ok:
                    continue

                # 3. Find rooms for EACH subject (with retry)
                def try_find_rooms(room_pool):
                    used = set()
                    chosen = {}
                    for i, req in enumerate(group_reqs):
                        room = None
                        # Try assigned room first
                        if req.assigned_room_id:
                            room = next(
                                (r for r in room_pool
                                 if r.id == req.assigned_room_id
                                 and r.id not in used
                                 and state.is_room_free(r.id, day, start_slot)
                                 and state.is_room_free(r.id, day, end_slot)),
                                None
                            )
                        if not room:
                            # Best-fit from pool: smallest room >= 20 students (batch size)
                            room = next(
                                (r for r in room_pool
                                 if r.id not in used
                                 and r.capacity >= 20
                                 and state.is_room_free(r.id, day, start_slot)
                                 and state.is_room_free(r.id, day, end_slot)),
                                None
                            )
                        if room:
                            chosen[i] = room
                            used.add(room.id)
                        else:
                            return None  # Failed
                    return chosen

                # Try with preferred lab rooms first
                chosen_rooms = try_find_rooms(lab_rooms_sorted)
                if not chosen_rooms:
                    # Retry with ALL rooms
                    chosen_rooms = try_find_rooms(all_rooms_sorted)
                if not chosen_rooms:
                    continue

                # 4. COMMIT: Create allocations for ALL subjects in this group
                for i, req in enumerate(group_reqs):
                    room = chosen_rooms[i]
                    batch_id = next(iter(req.batch_allocations.keys()), None) if req.batch_allocations else None

                    for idx, slot in enumerate([start_slot, end_slot]):
                        entry = AllocationEntry(
                            semester_id=semester_id,
                            subject_id=req.subject_id,
                            teacher_id=req.assigned_teacher_id,
                            room_id=room.id,
                            day=day,
                            slot=slot,
                            component_type=req.component_type,
                            academic_component=req.academic_component,
                            is_lab_continuation=(idx == 1),
                            batch_id=batch_id
                        )
                        state.add_allocation(entry, force_parallel=True)
                        allocations_added += 1

                blocks_scheduled += 1
                subj_codes = ", ".join(r.subject_code for r in group_reqs)
                print(f"         [OK] Group {group_name} -> Day {day} slots {start_slot}-{end_slot} ({subj_codes})")

            if blocks_scheduled < max_blocks:
                print(f"      [WARN] Only {blocks_scheduled}/{max_blocks} blocks for group {group_name}. Falling back.")
                failed_reqs.extend(group_reqs)
            else:
                print(f"      [OK] Group {group_name}: all {max_blocks} blocks scheduled")

        return allocations_added, failed_reqs

    # ============================================================
    # REGULAR SCHEDULING (READ-ONLY)
    # ============================================================
    
    def _schedule_labs_readonly(
        self,
        state: TimetableState,
        lab_reqs: List[ComponentRequirement],
        rooms: List[Room]
    ) -> List[ComponentRequirement]:
        """Schedule regular labs as atomic 2-period blocks.
        Returns list of failed (unscheduled) lab requirements."""
        if not lab_reqs:
            return []
        
        allocations_added = 0
        failed_reqs = []
        
        for req in sorted(lab_reqs, key=lambda r: r.hours_per_week, reverse=True):
            blocks_needed = req.hours_per_week // 2
            blocks_scheduled = 0
            
            lab_slots = [(d, block) for d in range(DAYS_PER_WEEK) for block in self.valid_lab_blocks]
            random.shuffle(lab_slots)
            
            # CASE 1: PARALLEL BATCHES (Split Class)
            if req.batch_allocations:
                # We need to schedule MULTIPLE allocations per slot (one for each batch)
                # All batches must be scheduled at the SAME TIME.
                n_batches = len(req.batch_allocations)
                print(f"      [PARALLEL] Scheduling {n_batches} batches for {req.subject_code} ({blocks_needed} blocks)")
                
                batches = list(req.batch_allocations.items()) # [(batch_id, teacher_id), ...]
                
                # Score slots by day load for better distribution
                def batch_slot_score(day_block):
                    day, (s1, s2) = day_block
                    day_load = sum(
                        1 for sl in range(SLOTS_PER_DAY)
                        if not state.is_semester_free(req.semester_id, day, sl)
                    )
                    return day_load

                lab_slots_scored = sorted(lab_slots, key=batch_slot_score)
                # Shuffle within same-score groups
                import itertools as _it
                scored_items = [(batch_slot_score(s), s) for s in lab_slots_scored]
                lab_slots_final = []
                for _, grp in _it.groupby(scored_items, key=lambda x: x[0]):
                    bucket = [item[1] for item in grp]
                    random.shuffle(bucket)
                    lab_slots_final.extend(bucket)

                # Pre-sort rooms for batch allocation (prefer lab-type, then by capacity)
                batch_rooms = sorted(
                    [r for r in rooms if (not req.preferred_room_types or r.room_type in req.preferred_room_types)],
                    key=lambda r: r.capacity
                )
                if not batch_rooms:
                    batch_rooms = sorted(rooms, key=lambda r: r.capacity)

                for day, (start_slot, end_slot) in lab_slots_final:
                    if blocks_scheduled >= blocks_needed:
                        break
                    
                    # 1. Check if Semester is free (prevent overlap with whole-class lectures)
                    if not (state.is_semester_free(req.semester_id, day, start_slot) and
                            state.is_semester_free(req.semester_id, day, end_slot)):
                        continue

                    # 2. Check ALL Teachers
                    teachers_eligible = True
                    for batch_id, teacher_id in batches:
                        if not (state.is_teacher_eligible(teacher_id, day, start_slot) and
                                state.is_teacher_eligible(teacher_id, day, end_slot)):
                            teachers_eligible = False
                            break
                    if not teachers_eligible:
                        continue
                        
                    # 3. Find Rooms for EACH Batch (best-fit allocation)
                    chosen_rooms = {} # batch_id -> room
                    used_rooms_in_this_slot = set()
                    
                    rooms_ok = True
                    
                    for batch_id, teacher_id in batches:
                        # Check for specific room
                        specific_room_id = req.batch_room_allocations.get(batch_id)
                        
                        room = None
                        if specific_room_id:
                            room = next(
                                (r for r in rooms
                                 if r.id == specific_room_id
                                 and r.id not in used_rooms_in_this_slot
                                 and state.is_room_free(r.id, day, start_slot)
                                 and state.is_room_free(r.id, day, end_slot)),
                                None
                            )
                        if not room:
                            # Best-fit from pre-sorted pool
                            room = next(
                                (r for r in batch_rooms
                                 if r.capacity >= 20
                                 and r.id not in used_rooms_in_this_slot
                                 and state.is_room_free(r.id, day, start_slot)
                                 and state.is_room_free(r.id, day, end_slot)),
                                None
                            )
                        
                        if room:
                            chosen_rooms[batch_id] = room
                            used_rooms_in_this_slot.add(room.id)
                        else:
                            rooms_ok = False
                            break
                    
                    if rooms_ok:
                        # COMMIT ALL BATCHES
                        for batch_id, teacher_id in batches:
                            room = chosen_rooms[batch_id]
                            for idx, slot in enumerate([start_slot, end_slot]):
                                entry = AllocationEntry(
                                    semester_id=req.semester_id,
                                    subject_id=req.subject_id,
                                    teacher_id=teacher_id,
                                    room_id=room.id,
                                    day=day,
                                    slot=slot,
                                    component_type=req.component_type,
                                    academic_component=req.academic_component,
                                    is_lab_continuation=(idx == 1),
                                    batch_id=batch_id # KEY: Assign to specific batch
                                )
                                state.add_allocation(entry)
                                allocations_added += 1
                                
                        blocks_scheduled += 1

            # CASE 2: REGULAR LAB (Whole Class)
            else:
                teacher_id = req.assigned_teacher_id
                if not teacher_id:
                    continue
                
                for day, (start_slot, end_slot) in lab_slots:
                    if blocks_scheduled >= blocks_needed:
                        break
                    
                    # Check availability
                    if not (state.is_semester_free(req.semester_id, day, start_slot) and
                            state.is_semester_free(req.semester_id, day, end_slot)):
                        continue
                    
                    # STRICT eligibility check
                    if not (state.is_teacher_eligible(teacher_id, day, start_slot) and
                            state.is_teacher_eligible(teacher_id, day, end_slot)):
                        continue

                    room = None
                    if req.assigned_room_id:
                        room = next(
                            (r for r in rooms
                             if r.id == req.assigned_room_id
                             and r.capacity >= req.min_room_capacity
                             and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                             and state.is_room_free(r.id, day, start_slot)
                             and state.is_room_free(r.id, day, end_slot)),
                            None
                        )
                    else:
                        room = next(
                            (r for r in rooms
                             if r.capacity >= req.min_room_capacity
                             and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                             and state.is_room_free(r.id, day, start_slot)
                             and state.is_room_free(r.id, day, end_slot)),
                            None
                        )
                    
                    if room:
                        for idx, slot in enumerate([start_slot, end_slot]):
                            entry = AllocationEntry(
                                semester_id=req.semester_id,
                                subject_id=req.subject_id,
                                teacher_id=teacher_id,
                                room_id=room.id,
                                day=day,
                                slot=slot,
                                component_type=req.component_type,
                                academic_component=req.academic_component,
                                is_lab_continuation=(idx == 1)
                            )
                            state.add_allocation(entry)
                            allocations_added += 1
                        blocks_scheduled += 1

            if blocks_scheduled < blocks_needed:
                missing = blocks_needed - blocks_scheduled
                if req.batch_allocations:
                    fail_msg = (
                        f"[LAB] Class {req.semester_id} {req.subject_code} ({req.academic_component}): "
                        f"Unscheduled {missing}/{blocks_needed} batch block(s). "
                        "Likely teacher or room constraint for one/more batches."
                    )
                else:
                    fail_msg = (
                        f"[LAB] Class {req.semester_id} {req.subject_code} ({req.academic_component}): "
                        f"Unscheduled {missing}/{blocks_needed} block(s). "
                        f"Assigned teacher {req.assigned_teacher_id} not available with a valid room pair."
                    )
                self.allocation_failures.append(fail_msg)
                failed_reqs.append(req)
        
        return failed_reqs

    def _schedule_day_based_seminars_readonly(
        self,
        state: TimetableState,
        internship_reqs: List[ComponentRequirement],
        rooms: List[Room],
    ) -> int:
        """
        Best-effort scheduler for day-based internships (7 periods on the same day).

        This is a SOFT preference:
        - If a full-day block can't be placed due to constraints, it is skipped
        - Any remaining hours are scheduled later by the normal theory scheduler

        Safety: Only adds in-memory allocations; never modifies source data.
        """
        if not internship_reqs:
            return 0

        allocations_added = 0

        for req in internship_reqs:
            teacher_id = req.assigned_teacher_id
            if not teacher_id:
                continue

            remaining_hours = int(req.hours_per_week or 0)
            full_day_blocks_needed = remaining_hours // SLOTS_PER_DAY
            if full_day_blocks_needed <= 0:
                continue

            blocks_scheduled = 0

            # Try to schedule as many full days as needed.
            for _ in range(full_day_blocks_needed):
                days = list(range(DAYS_PER_WEEK))
                random.shuffle(days)

                scheduled = False
                for day in days:
                    # Must have ALL 7 slots free for this class + teacher.
                    if not all(state.is_semester_free(req.semester_id, day, slot) for slot in range(SLOTS_PER_DAY)):
                        continue
                    if not all(state.is_teacher_eligible(teacher_id, day, slot) for slot in range(SLOTS_PER_DAY)):
                        continue

                    room = None
                    if req.assigned_room_id:
                        room = next(
                            (
                                r
                                for r in rooms
                                if r.id == req.assigned_room_id
                                and r.capacity >= req.min_room_capacity
                                and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                and all(state.is_room_free(r.id, day, slot) for slot in range(SLOTS_PER_DAY))
                            ),
                            None,
                        )
                    else:
                        room = next(
                            (
                                r
                                for r in rooms
                                if r.capacity >= req.min_room_capacity
                                and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                and all(state.is_room_free(r.id, day, slot) for slot in range(SLOTS_PER_DAY))
                            ),
                            None,
                        )

                    if not room:
                        continue

                    for slot in range(SLOTS_PER_DAY):
                        entry = AllocationEntry(
                            semester_id=req.semester_id,
                            subject_id=req.subject_id,
                            teacher_id=teacher_id,
                            room_id=room.id,
                            day=day,
                            slot=slot,
                            component_type=req.component_type,
                            academic_component=req.academic_component,
                        )
                        state.add_allocation(entry)
                        allocations_added += 1

                    remaining_hours -= SLOTS_PER_DAY
                    blocks_scheduled += 1
                    scheduled = True
                    break

                if not scheduled:
                    # Can't place more full-day blocks; leave remainder for normal scheduling.
                    break

            # Reduce remaining hours so the normal theory scheduler only schedules what's left.
            req.hours_per_week = max(remaining_hours, 0)

            if blocks_scheduled > 0:
                print(
                    f"        [INTERNSHIP] Scheduled {blocks_scheduled} day-based block(s) for {req.subject_code} ({req.semester_id})"
                )

        return allocations_added
    
    def _retry_failed_labs_post_theory(
        self,
        state: TimetableState,
        failed_reqs: List[ComponentRequirement],
        rooms: List[Room],
        lecture_rooms: List[Room],
        semesters: List[Semester],
        semester_by_id: Dict[int, Semester],
        default_classroom_map: Dict[int, int] = None
    ):
        """Retry failed lab blocks by swapping out theory allocations.
        
        After theory fills ALL slots, some lab blocks couldn't get 2 consecutive
        periods. This method finds 2 adjacent slots with theory classes, removes
        them, places the lab block, then re-schedules the displaced theory classes
        into any remaining open slots.
        """
        if not failed_reqs:
            return
        
        default_classroom_map = default_classroom_map or {}
        room_by_id = {r.id: r for r in rooms}
        labs_fixed = 0
        
        # Clear "phantom" semester_slots entries: the theory scheduler marks
        # free period slots as used in semester_slots for tracking, but they
        # have no actual allocation. Remove these so the retry can use them.
        actual_alloc_slots = {}
        for a in state.allocations:
            if a.semester_id not in actual_alloc_slots:
                actual_alloc_slots[a.semester_id] = set()
            actual_alloc_slots[a.semester_id].add((a.day, a.slot))
        
        for sem_id_check in state.semester_slots:
            phantom = state.semester_slots[sem_id_check] - actual_alloc_slots.get(sem_id_check, set())
            if phantom:
                state.semester_slots[sem_id_check] -= phantom
        
        for req in failed_reqs:
            sem_id = req.semester_id
            teacher_id = req.assigned_teacher_id
            if not teacher_id:
                continue
            
            blocks_needed = req.hours_per_week // 2
            blocks_placed = 0
            
            for _ in range(blocks_needed):
                placed = False
                
                # Try each valid lab block position
                candidate_swaps = []
                for day in range(DAYS_PER_WEEK):
                    for (start_slot, end_slot) in self.valid_lab_blocks:
                        # Check teacher is free at BOTH slots
                        if not (state.is_teacher_eligible(teacher_id, day, start_slot) and
                                state.is_teacher_eligible(teacher_id, day, end_slot)):
                            continue
                        
                        # Check if semester has THEORY (swappable) allocations at these slots
                        alloc_s1 = None
                        alloc_s2 = None
                        for a in state.allocations:
                            if a.semester_id == sem_id and a.day == day and a.slot == start_slot:
                                if a.component_type.value == 'theory' or a.component_type.value == 'tutorial':
                                    alloc_s1 = a
                            if a.semester_id == sem_id and a.day == day and a.slot == end_slot:
                                if a.component_type.value == 'theory' or a.component_type.value == 'tutorial':
                                    alloc_s2 = a
                        
                        # Both slots must have swappable theory classes (or be free)
                        s1_free = state.is_semester_free(sem_id, day, start_slot)
                        s2_free = state.is_semester_free(sem_id, day, end_slot)
                        
                        if (s1_free or alloc_s1) and (s2_free or alloc_s2):
                            # Find a lab-type room
                            lab_room = None
                            if req.assigned_room_id:
                                lab_room = next(
                                    (r for r in rooms
                                     if r.id == req.assigned_room_id
                                     and r.capacity >= req.min_room_capacity
                                     and state.is_room_free(r.id, day, start_slot)
                                     and state.is_room_free(r.id, day, end_slot)),
                                    None
                                )
                            if not lab_room:
                                lab_room = next(
                                    (r for r in rooms
                                     if r.capacity >= req.min_room_capacity
                                     and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                     and state.is_room_free(r.id, day, start_slot)
                                     and state.is_room_free(r.id, day, end_slot)),
                                    None
                                )
                            
                            if lab_room:
                                to_displace = []
                                if alloc_s1 and not s1_free:
                                    to_displace.append(alloc_s1)
                                if alloc_s2 and not s2_free:
                                    to_displace.append(alloc_s2)
                                candidate_swaps.append((day, start_slot, end_slot, lab_room, to_displace))
                
                # Sort candidates: prefer those displacing fewer theory classes
                candidate_swaps.sort(key=lambda x: len(x[4]))
                
                for day, start_slot, end_slot, lab_room, to_displace in candidate_swaps:
                    # Remove displaced theory allocations from state
                    for a in to_displace:
                        state.remove_allocation(a)
                    
                    # Place the lab block
                    for idx, slot in enumerate([start_slot, end_slot]):
                        entry = AllocationEntry(
                            semester_id=sem_id,
                            subject_id=req.subject_id,
                            teacher_id=teacher_id,
                            room_id=lab_room.id,
                            day=day,
                            slot=slot,
                            component_type=req.component_type,
                            academic_component=req.academic_component,
                            is_lab_continuation=(idx == 1)
                        )
                        state.add_allocation(entry)
                    
                    # Try to re-schedule displaced theory into open slots
                    reschedule_ok = True
                    for displaced in to_displace:
                        rescheduled = False
                        for rs in range(SLOTS_PER_DAY):
                            for rd in range(DAYS_PER_WEEK):
                                if not state.is_semester_free(sem_id, rd, rs):
                                    continue
                                if not state.is_teacher_eligible(displaced.teacher_id, rd, rs):
                                    continue
                                # Find a room for the displaced theory
                                d_room = None
                                default_room_id = default_classroom_map.get(sem_id)
                                if default_room_id:
                                    dr = room_by_id.get(default_room_id)
                                    if dr and state.is_room_free(dr.id, rd, rs):
                                        d_room = dr
                                if not d_room:
                                    d_room = next(
                                        (r for r in lecture_rooms
                                         if r.capacity >= 30
                                         and state.is_room_free(r.id, rd, rs)),
                                        None
                                    )
                                if d_room:
                                    new_entry = AllocationEntry(
                                        semester_id=displaced.semester_id,
                                        subject_id=displaced.subject_id,
                                        teacher_id=displaced.teacher_id,
                                        room_id=d_room.id,
                                        day=rd,
                                        slot=rs,
                                        component_type=displaced.component_type,
                                        academic_component=displaced.academic_component
                                    )
                                    state.add_allocation(new_entry)
                                    rescheduled = True
                                    break
                            if rescheduled:
                                break
                        if not rescheduled:
                            reschedule_ok = False
                    
                    if reschedule_ok:
                        blocks_placed += 1
                        labs_fixed += 1
                        sem = semester_by_id.get(sem_id)
                        print(f"      [LAB-RETRY] Placed {req.subject_code} lab for {sem.name if sem else sem_id} at Day {day} Slots {start_slot}-{end_slot}")
                        placed = True
                        break
                    else:
                        # Rollback: remove lab, restore displaced
                        lab_allocs = [
                            a for a in state.allocations
                            if a.semester_id == sem_id
                            and a.subject_id == req.subject_id
                            and a.day == day
                            and a.slot in (start_slot, end_slot)
                        ]
                        for a in lab_allocs:
                            state.remove_allocation(a)
                        for a in to_displace:
                            state.add_allocation(a)
                
                if not placed:
                    break  # Can't place any more blocks for this req
        
        if labs_fixed > 0:
            print(f"      [LAB-RETRY] Fixed {labs_fixed} lab block(s) via theory displacement")

    def _schedule_theory_readonly(
        self,
        state: TimetableState,
        theory_reqs: List[ComponentRequirement],
        rooms: List[Room],
        semesters: List[Semester],
        semester_by_id: Dict[int, Semester],
        default_classroom_map: Dict[int, int] = None
    ) -> Tuple[int, int]:
        """Schedule theory/tutorials using ONLY existing mappings.
        
        default_classroom_map: semester_id -> room_id
            If a semester has a default classroom, theory classes prioritize it.
        """
        if not theory_reqs:
            return 0, 0
        
        allocations_added = 0
        free_periods = 0
        default_classroom_map = default_classroom_map or {}
        
        # Build room lookup for fast default-room access
        room_by_id = {r.id: r for r in rooms}
        hour_counters: Dict[Tuple[int, int, str], int] = {}
        req_lookup: Dict[Tuple[int, int, str], ComponentRequirement] = {}
        
        for req in theory_reqs:
            if not req.assigned_teacher_id:
                continue
            key = (req.semester_id, req.subject_id, req.academic_component)
            hour_counters[key] = req.hours_per_week
            req_lookup[key] = req
        
        # Process each semester
        for semester in semesters:
            sem_id = semester.id
            sem_free = 0
            sem_filled = 0
            
            print(f"      {semester.name}...")
            
            # SLOT-FIRST iteration
            for slot in range(SLOTS_PER_DAY):
                days = list(range(DAYS_PER_WEEK))
                random.shuffle(days)
                
                for day in days:
                    if not state.is_semester_free(sem_id, day, slot):
                        continue
                    
                    filled = False
                    
                    # Get subjects with remaining hours
                    available = [
                        (k, hour_counters[k])
                        for k in hour_counters
                        if k[0] == sem_id and hour_counters[k] > 0
                    ]
                    
                    if available:
                        # PRIORITY SLOT SCORING:
                        # Slot weights: Period 1-2 â†’ +3, Period 3-4 â†’ +2, Period 5-6 â†’ +1, Period 7 â†’ 0
                        SLOT_WEIGHTS = {0: 3, 1: 3, 2: 2, 3: 2, 4: 1, 5: 1, 6: 0}
                        slot_weight = SLOT_WEIGHTS.get(slot, 0)
                        
                        # Sort by: priority_weight (desc), then remaining hours (desc)
                        # Higher priority subjects get first pick of morning slots
                        def sort_key(item):
                            key, remaining = item
                            req = req_lookup.get(key)
                            pw = req.priority_weight if req else 0
                            # TotalScore = SlotWeight + priority_weight
                            # For HIGH priority subjects, score matters more for early slots
                            return (-(pw * slot_weight + remaining), -remaining)
                        
                        available.sort(key=sort_key)
                        
                        for (s_sem, s_subj, s_comp), remaining in available:
                            req = req_lookup.get((s_sem, s_subj, s_comp))
                            if not req:
                                continue
                            
                            teacher_id = req.assigned_teacher_id
                            
                            # STRICT eligibility check
                            if not state.is_teacher_eligible(teacher_id, day, slot):
                                continue
                            
                            # Daily limit (soft constraint - can be relaxed)
                            # HIGH priority: prefer spread across week (max 1/day)
                            current = state.get_subject_daily_count(sem_id, day, req.subject_id)
                            if req.priority_weight >= 2:
                                # HIGH priority: prefer 1 per day for better distribution
                                max_daily = 1 if req.hours_per_week <= 5 else 2
                            else:
                                max_daily = 2 if req.hours_per_week > 5 else 1
                            if current >= max_daily:
                                continue

                            # ----- DEFAULT CLASSROOM PRIORITIZATION -----
                            room = None
                            
                            # Check if this semester has a default classroom AND
                            # the component is theory/tutorial (not lab)
                            default_room_id = default_classroom_map.get(sem_id)
                            
                            if default_room_id and not req.assigned_room_id:
                                # Try the default classroom first
                                default_room = room_by_id.get(default_room_id)
                                if (default_room
                                    and default_room.capacity >= req.min_room_capacity
                                    and (not req.preferred_room_types or default_room.room_type in req.preferred_room_types)
                                    and state.is_room_free(default_room.id, day, slot)):
                                    room = default_room
                            
                            # If no default room (or it was busy), fall back
                            if room is None and req.assigned_room_id:
                                room = next(
                                    (r for r in rooms
                                     if r.id == req.assigned_room_id
                                     and r.capacity >= req.min_room_capacity
                                     and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                     and state.is_room_free(r.id, day, slot)),
                                    None
                                )
                            elif room is None:
                                room = next(
                                    (r for r in rooms
                                     if r.capacity >= req.min_room_capacity
                                     and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                     and state.is_room_free(r.id, day, slot)),
                                    None
                                )
                            
                            if room:
                                entry = AllocationEntry(
                                    semester_id=sem_id,
                                    subject_id=req.subject_id,
                                    teacher_id=teacher_id,
                                    room_id=room.id,
                                    day=day,
                                    slot=slot,
                                    component_type=req.component_type,
                                    academic_component=req.academic_component
                                )
                                state.add_allocation(entry)
                                hour_counters[(s_sem, s_subj, s_comp)] -= 1
                                allocations_added += 1
                                sem_filled += 1
                                filled = True
                                break
                    
                    # RETRY PASS: Relax daily limit if no subjects available
                    if not filled and available:
                        for (s_sem, s_subj, s_comp), remaining in available:
                            req = req_lookup.get((s_sem, s_subj, s_comp))
                            if not req:
                                continue
                            
                            teacher_id = req.assigned_teacher_id
                            
                            if not state.is_teacher_eligible(teacher_id, day, slot):
                                continue
                            
                            # ----- DEFAULT CLASSROOM PRIORITIZATION (RETRY) -----
                            room = None
                            
                            default_room_id = default_classroom_map.get(sem_id)
                            if default_room_id and not req.assigned_room_id:
                                default_room = room_by_id.get(default_room_id)
                                if (default_room
                                    and default_room.capacity >= req.min_room_capacity
                                    and (not req.preferred_room_types or default_room.room_type in req.preferred_room_types)
                                    and state.is_room_free(default_room.id, day, slot)):
                                    room = default_room
                            
                            if room is None and req.assigned_room_id:
                                room = next(
                                    (r for r in rooms
                                     if r.id == req.assigned_room_id
                                     and r.capacity >= req.min_room_capacity
                                     and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                     and state.is_room_free(r.id, day, slot)),
                                    None
                                )
                            elif room is None:
                                room = next(
                                    (r for r in rooms
                                     if r.capacity >= req.min_room_capacity
                                     and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                     and state.is_room_free(r.id, day, slot)),
                                    None
                                )
                            
                            if room:
                                entry = AllocationEntry(
                                    semester_id=sem_id,
                                    subject_id=req.subject_id,
                                    teacher_id=teacher_id,
                                    room_id=room.id,
                                    day=day,
                                    slot=slot,
                                    component_type=req.component_type,
                                    academic_component=req.academic_component
                                )
                                state.add_allocation(entry)
                                hour_counters[(s_sem, s_subj, s_comp)] -= 1
                                allocations_added += 1
                                sem_filled += 1
                                filled = True
                                break
                    
                    # FREE PERIOD determination:
                    # Only create a TRUE free period when:
                    #   1. No subjects remain (available is empty), OR
                    #   2. Subjects exist but ALL failures are "No Room" (unresolvable now and later).
                    # If all failures are "teacher busy" (shared teacher in same dept batch),
                    # DEFER the slot - leave it open so a later iteration can fill it.
                    # This prevents cascading free periods for I-B/I-F and similar shared-teacher cases.
                    if not filled:
                        if not available:
                            # Truly no subjects left - genuine free period
                            if sem_id not in state.semester_slots:
                                state.semester_slots[sem_id] = set()
                            state.semester_slots[sem_id].add((day, slot))
                            free_periods += 1
                            sem_free += 1
                        else:
                            # Determine WHY scheduling failed
                            all_teacher_busy = all(
                                not state.is_teacher_eligible(
                                    req_lookup[(s_sem, s_subj, s_comp)].assigned_teacher_id, day, slot
                                )
                                for (s_sem, s_subj, s_comp), _ in available
                                if (s_sem, s_subj, s_comp) in req_lookup
                            )
                            if all_teacher_busy:
                                # DEFER: teacher busy with another class in this batch.
                                # Leave slot open - do NOT add to semester_slots.
                                # Post-iteration pass will attempt to fill it.
                                pass
                            else:
                                # At least one failure is "No Room" - emit free period
                                reasons = []
                                for (s_sem, s_subj, s_comp), remaining in available:
                                    req = req_lookup.get((s_sem, s_subj, s_comp))
                                    if not req: continue
                                    teacher_busy = not state.is_teacher_eligible(req.assigned_teacher_id, day, slot)
                                    if teacher_busy:
                                        reasons.append(f"Subj {req.subject_name}: Teacher {req.assigned_teacher_id} Busy")
                                    else:
                                        reasons.append(f"Subj {req.subject_name}: No Room")
                                fail_summary = f"[FREE] Class {sem_id} Day {day} Slot {slot}: {', '.join(reasons[:3])}"
                                if len(reasons) > 3: fail_summary += "..."
                                if fail_summary not in self.allocation_failures:
                                    self.allocation_failures.append(fail_summary)
                                if sem_id not in state.semester_slots:
                                    state.semester_slots[sem_id] = set()
                                state.semester_slots[sem_id].add((day, slot))
                                free_periods += 1
                                sem_free += 1
            
            # ---------------------------------------------------------------
            # POST-ITERATION PASS: Fill remaining hours deferred by teacher conflicts.
            # When teachers are shared across sections in the same dept batch,
            # some slots are deferred (left open) during the main iteration.
            # We now try ALL open (day, slot) pairs to fill remaining subject hours.
            # ---------------------------------------------------------------
            remaining_keys = [
                k for k in hour_counters
                if k[0] == sem_id and hour_counters[k] > 0
            ]
            if remaining_keys:
                open_slots = [
                    (day, slot)
                    for slot in range(SLOTS_PER_DAY)
                    for day in range(DAYS_PER_WEEK)
                    if state.is_semester_free(sem_id, day, slot)
                ]
                random.shuffle(open_slots)

                for day, slot in open_slots:
                    still_remaining = [k for k in remaining_keys if hour_counters[k] > 0]
                    if not still_remaining:
                        break

                    for key in still_remaining:
                        req = req_lookup.get(key)
                        if not req:
                            continue

                        teacher_id = req.assigned_teacher_id
                        if not state.is_teacher_eligible(teacher_id, day, slot):
                            continue

                        room = None
                        default_room_id = default_classroom_map.get(sem_id)
                        if default_room_id and not req.assigned_room_id:
                            default_room = room_by_id.get(default_room_id)
                            if (default_room
                                    and default_room.capacity >= req.min_room_capacity
                                    and (not req.preferred_room_types or default_room.room_type in req.preferred_room_types)
                                    and state.is_room_free(default_room.id, day, slot)):
                                room = default_room

                        if room is None and req.assigned_room_id:
                            room = next(
                                (r for r in rooms
                                 if r.id == req.assigned_room_id
                                 and r.capacity >= req.min_room_capacity
                                 and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                 and state.is_room_free(r.id, day, slot)),
                                None
                            )
                        elif room is None:
                            room = next(
                                (r for r in rooms
                                 if r.capacity >= req.min_room_capacity
                                 and (not req.preferred_room_types or r.room_type in req.preferred_room_types)
                                 and state.is_room_free(r.id, day, slot)),
                                None
                            )

                        if room:
                            entry = AllocationEntry(
                                semester_id=sem_id,
                                subject_id=req.subject_id,
                                teacher_id=teacher_id,
                                room_id=room.id,
                                day=day,
                                slot=slot,
                                component_type=req.component_type,
                                academic_component=req.academic_component
                            )
                            state.add_allocation(entry)
                            hour_counters[key] -= 1
                            allocations_added += 1
                            sem_filled += 1
                            break

                # Any hours still remaining truly cannot be scheduled.
                truly_remaining = sum(hour_counters[k] for k in remaining_keys if hour_counters[k] > 0)
                if truly_remaining > 0:
                    remaining_subj_names = [
                        req_lookup[k].subject_name
                        for k in remaining_keys
                        if hour_counters[k] > 0 and k in req_lookup
                    ]
                    fail_msg = (
                        f"[POST-PASS] Class {sem_id}: {truly_remaining} hours unschedulable. "
                        f"Subjects: {', '.join(remaining_subj_names[:5])}"
                    )
                    if fail_msg not in self.allocation_failures:
                        self.allocation_failures.append(fail_msg)

            if sem_free > 0:
                print(f"         -> {sem_filled} subjects + {sem_free} FREE")
            else:
                print(f"         -> {sem_filled} subjects")
        
        return allocations_added, free_periods
    
    # ============================================================
    # SAVE ALLOCATIONS ONLY (NO SOURCE DATA CHANGES)
    # ============================================================
    
    def _save_allocations_only(self, allocations: List[AllocationEntry]):
        """
        Save ONLY allocation records.
        DO NOT modify teachers, subjects, classes, or assignments.
        """
        if not allocations:
            return
        
        # Deduplicate (key includes subject_id to allow multiple electives at same slot)
        seen = set()
        unique = []
        for entry in allocations:
            # Prevent saving incomplete allocations (which violates DB NOT NULL constraints)
            if entry.teacher_id is None or entry.subject_id is None or entry.room_id is None:
                continue
                
            key = (entry.semester_id, entry.subject_id, entry.day, entry.slot)
            if key not in seen:
                seen.add(key)
                unique.append(entry)
        
        for entry in unique:
            db_alloc = Allocation(
                teacher_id=entry.teacher_id,
                subject_id=entry.subject_id,
                semester_id=entry.semester_id,
                room_id=entry.room_id,
                day=entry.day,
                slot=entry.slot,
                component_type=entry.component_type,
                academic_component=entry.academic_component,
                is_lab_continuation=entry.is_lab_continuation,
                is_elective=entry.is_elective,
                elective_basket_id=entry.elective_basket_id,
                batch_id=entry.batch_id # NEW: Persist batch assignment
            )
            self.db.add(db_alloc)
        
        try:
            self.db.commit()
            print(f"   [OK] Saved {len(unique)} valid allocations")
        except Exception as e:
            self.db.rollback()
            print(f"   [FAIL] Save failed: {e}")
    
    def _clear_allocations_only(self, semesters: List[Semester]):
        """
        Clear ONLY allocation records.
        DO NOT touch ClassSubjectTeacher or any source data.
        """
        sem_ids = [s.id for s in semesters]
        
        deleted = self.db.query(Allocation).filter(
            Allocation.semester_id.in_(sem_ids)
        ).delete(synchronize_session=False)
        
        self.db.commit()
        print(f"   Cleared {deleted} existing allocations")
    
    def _get_randomized_slots(self) -> List[Tuple[int, int]]:
        """Get slots in randomized order."""
        slots = [(d, s) for d in range(DAYS_PER_WEEK) for s in range(SLOTS_PER_DAY)]
        random.shuffle(slots)
        return slots


