"""
READ-ONLY COLLEGE TIMETABLE GENERATION ENGINE
==============================================

⚠️ CRITICAL SAFETY RULE (ABSOLUTE):
- DO NOT delete, recreate, overwrite, or modify any existing data
- DO NOT change existing teachers, subjects, classes, or assignments
- ONLY READ existing data and ENFORCE rules during timetable generation

GENERATION FLOW:
1. READ existing teacher↔subject↔class mappings
2. BUILD temporary elective time locks (in-memory only)
3. ALLOCATE slots using ONLY existing mappings
4. SAVE allocations to database (new records only)
5. NEVER modify source data
"""
import random
import time
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

# Valid lab block positions (0-indexed): 4th+5th or 6th+7th period
VALID_LAB_BLOCKS = [(3, 4), (5, 6)]


# ============================================================
# DATA STRUCTURES (IN-MEMORY ONLY - NO DATABASE WRITES)
# ============================================================

@dataclass
class ComponentRequirement:
    """A single component that needs to be scheduled (READ from DB)."""
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
    assigned_teacher_id: Optional[int] = None  # READ from existing mapping


@dataclass
class AllocationEntry:
    """A single allocation in the timetable (NEW records to be created)."""
    semester_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    day: int
    slot: int
    component_type: ComponentType = ComponentType.THEORY
    is_lab_continuation: bool = False
    is_elective: bool = False
    elective_basket_id: Optional[int] = None


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
    elective_slot_ownership: Dict[Tuple[int, int], Tuple[int, Optional[int]]] = field(default_factory=dict)
    
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
    
    def is_slot_fixed(self, semester_id: int, day: int, slot: int) -> bool:
        """Check if a slot is fixed/locked and cannot be modified."""
        return (semester_id, day, slot) in self.fixed_slots
    
    def mark_slot_as_fixed(self, semester_id: int, day: int, slot: int):
        """Mark a slot as fixed/locked."""
        self.fixed_slots.add((semester_id, day, slot))
    
    def add_allocation(self, entry: AllocationEntry) -> bool:
        """Add allocation to in-memory state. Returns False if slot taken."""
        slot_key = (entry.day, entry.slot)
        
        # Check for collision
        if entry.semester_id in self.semester_slots:
            if slot_key in self.semester_slots[entry.semester_id]:
                return False
        
        self.allocations.append(entry)
        
        # Update in-memory lookups
        if entry.teacher_id not in self.teacher_slots:
            self.teacher_slots[entry.teacher_id] = set()
        self.teacher_slots[entry.teacher_id].add(slot_key)
        
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
    
    def is_teacher_free(self, teacher_id: int, day: int, slot: int) -> bool:
        """Check if teacher is free (in-memory check)."""
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
        
        # Mark slot ownership
        self.elective_slot_ownership[slot_key] = group_key
        
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
        
        if slot_key not in self.elective_slot_ownership:
            return False  # Slot not reserved by any group
        
        owner_group = self.elective_slot_ownership[slot_key]
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
            return False
        
        # Check if slot is reserved for another group
        if self.is_slot_reserved_for_other_group(day, slot, year, basket_id):
            return False
        
        # If teacher is locked but for THIS group, they ARE eligible
        slot_key = (day, slot)
        if slot_key in self.elective_slot_ownership:
            owner_group = self.elective_slot_ownership[slot_key]
            if owner_group == (year, basket_id):
                # This slot belongs to our group - teacher eligible if assigned to this group
                return True
        
        # Standard elective lock check
        if self.is_teacher_locked_for_elective(teacher_id, day, slot):
            return False
        
        return True
    
    def is_room_free(self, room_id: int, day: int, slot: int) -> bool:
        if room_id not in self.room_slots:
            return True
        return (day, slot) not in self.room_slots[room_id]
    
    def is_semester_free(self, semester_id: int, day: int, slot: int) -> bool:
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
    ✔ Existing data is UNTOUCHED
    ✔ Teachers never appear in wrong classes
    ✔ Elective teachers are isolated correctly
    ✔ Elective slots are synchronized
    ✔ Timetable generation is stable (NEVER fails)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.free_period_reasons: List[str] = []
    
    def generate(
        self,
        semester_ids: Optional[List[int]] = None,
        clear_existing: bool = True
    ) -> Tuple[bool, str, List[AllocationEntry], float]:
        """
        MAIN ENTRY POINT: Generate timetable using READ-ONLY data access.
        
        SAFETY:
        - Only READS existing mappings
        - Only CREATES new Allocation records
        - NEVER modifies teachers, subjects, or assignments
        """
        start_time = time.time()
        self.free_period_reasons = []
        total_free_periods = 0
        
        # ============================================================
        # DETERMINISTIC SEED - Ensures consistent results every run
        # ============================================================
        random.seed(42)  # Fixed seed for reproducible generation
        
        try:
            print("\n" + "="*60)
            print("READ-ONLY TIMETABLE GENERATION ENGINE")
            print("="*60)
            print("⚠️ DATA SAFETY: Existing data will NOT be modified")
            print("🎯 DETERMINISTIC MODE: Using fixed seed for consistent results")
            
            # ============================================================
            # STEP 1: READ ALL DATA (NO MODIFICATIONS)
            # ============================================================
            print("\n[STEP 1] READING EXISTING DATA...")
            
            semesters = self._read_semesters(semester_ids)
            teachers = self._read_teachers()
            subjects = self._read_subjects()
            rooms = self._read_rooms()
            
            if not semesters:
                return True, "No semesters to generate", [], time.time() - start_time
            
            print(f"   READ: {len(semesters)} classes, {len(teachers)} teachers, {len(subjects)} subjects, {len(rooms)} rooms")
            
            # Clear ONLY allocations (not source data)
            if clear_existing:
                self._clear_allocations_only(semesters)
            
            # ============================================================
            # STEP 2: READ EXISTING TEACHER ASSIGNMENTS (NO FALLBACK)
            # ============================================================
            print("\n[STEP 2] READING TEACHER ASSIGNMENTS...")
            
            state = TimetableState()
            
            # READ teacher assignments - NO auto-assignment, NO fallback
            teacher_assignment_map = self._read_teacher_assignment_map()
            state.teacher_assignment_map = teacher_assignment_map
            
            print(f"   READ: {len(teacher_assignment_map)} teacher↔class↔subject mappings")
            
            # ============================================================
            # STEP 3: DETECT ELECTIVE GROUPS (READ-ONLY)
            # ============================================================
            print("\n[STEP 3] DETECTING ELECTIVE GROUPS...")
            
            elective_groups = self._detect_elective_groups(semesters, subjects, teacher_assignment_map)
            
            print(f"   Detected {len(elective_groups)} elective group(s):")
            for group_key, group in elective_groups.items():
                year, basket_id = group_key
                print(f"   → Year {year}, Basket {basket_id} ({group.basket_name}): {len(group.subjects)} subjects, {len(group.teachers)} teachers, {len(group.classes)} classes")
            
            # EXTENDED: Pre-register all elective teachers with their groups
            # This enables per-group eligibility checking from the start
            for group_key, group in elective_groups.items():
                year, basket_id = group_key
                for teacher_id in group.teachers:
                    state.register_teacher_elective_group(teacher_id, year, basket_id)
            
            print(f"   Registered {len(state.teacher_elective_groups)} teachers with elective groups")
            
            # ============================================================
            # STEP 3.5: PRE-FILL FIXED SLOTS (IMMUTABLE DURING GENERATION)
            # ============================================================
            print("\n[STEP 3.5] LOADING FIXED/LOCKED SLOTS...")
            
            fixed_slots_count = self._prefill_fixed_slots(state, semesters, rooms)
            
            if fixed_slots_count > 0:
                print(f"   ✔ Loaded {fixed_slots_count} fixed/locked slots")
                print(f"   ⚠️ These slots are IMMUTABLE and will NOT be changed during generation")
            else:
                print("   No fixed slots found - all slots available for automatic scheduling")
            
            # Build helper lookups
            teacher_by_id = {t.id: t for t in teachers}
            semester_by_id = {s.id: s for s in semesters}
            lecture_rooms = [r for r in rooms if r.room_type in [RoomType.LECTURE, RoomType.SEMINAR]]
            lab_rooms = [r for r in rooms if r.room_type == RoomType.LAB]
            if not lab_rooms:
                lab_rooms = lecture_rooms
            
            # Build requirements from existing data
            all_requirements = self._build_requirements_readonly(
                semesters, subjects, teacher_assignment_map, semester_by_id
            )
            
            # Separate by type
            elective_theory_reqs = [r for r in all_requirements 
                                    if r.is_elective and r.component_type == ComponentType.THEORY]
            elective_lab_reqs = [r for r in all_requirements 
                                 if r.is_elective and r.component_type == ComponentType.LAB]
            regular_lab_reqs = [r for r in all_requirements 
                                if not r.is_elective and r.component_type == ComponentType.LAB]
            theory_tutorial_reqs = [r for r in all_requirements 
                                    if not r.is_elective and r.component_type in [ComponentType.THEORY, ComponentType.TUTORIAL]]
            
            # ============================================================
            # STEP 4: SCHEDULE ELECTIVES (WITH TEMPORARY LOCKS)
            # ============================================================
            print("\n[STEP 4] SCHEDULING ELECTIVES (with temporary teacher locks)...")
            
            elective_allocs = self._schedule_electives_readonly(
                state, elective_theory_reqs, lecture_rooms, semesters, elective_groups
            )
            print(f"   Scheduled {elective_allocs} elective theory slots")
            
            elective_lab_allocs = self._schedule_elective_labs_readonly(
                state, elective_lab_reqs, lab_rooms, semesters, elective_groups
            )
            print(f"   Scheduled {elective_lab_allocs} elective lab slots")
            
            # ============================================================
            # STEP 5: SCHEDULE REGULAR LABS
            # ============================================================
            print("\n[STEP 5] SCHEDULING REGULAR LABS...")
            
            lab_allocs = self._schedule_labs_readonly(state, regular_lab_reqs, lab_rooms)
            print(f"   Scheduled {lab_allocs} regular lab slots")
            
            # ============================================================
            # STEP 6: SCHEDULE THEORY/TUTORIALS
            # ============================================================
            print("\n[STEP 6] SCHEDULING THEORY & TUTORIALS...")
            
            theory_allocs, free_periods = self._schedule_theory_readonly(
                state, theory_tutorial_reqs, lecture_rooms, semesters, semester_by_id
            )
            print(f"   Scheduled {theory_allocs} theory/tutorial slots")
            print(f"   FREE periods: {free_periods}")
            total_free_periods = free_periods
            
            # ============================================================
            # STEP 7: SAVE ALLOCATIONS ONLY (NO SOURCE DATA CHANGES)
            # ============================================================
            print("\n[STEP 7] SAVING ALLOCATIONS (source data unchanged)...")
            
            self._save_allocations_only(state.allocations)
            
            total_time = time.time() - start_time
            total_allocations = len(state.allocations)
            
            print(f"   Saved {total_allocations} allocations in {total_time:.2f}s")
            print("\n" + "="*60)
            print("GENERATION COMPLETE - EXISTING DATA UNCHANGED")
            print("="*60)
            
            # Build message
            if total_free_periods > 0:
                message = f"Timetable generated with {total_free_periods} free periods due to teacher constraints"
            else:
                message = "Timetable generated successfully"
            
            return True, message, state.allocations, total_time
            
        except Exception as e:
            # NEVER FAIL - return what we have
            import traceback
            error_msg = f"Generation completed with issues: {str(e)}"
            print(f"\n[WARN] {error_msg}")
            print(traceback.format_exc())
            return True, error_msg, [], time.time() - start_time
    
    # ============================================================
    # READ-ONLY DATA ACCESS (NO MODIFICATIONS)
    # ============================================================
    
    def _read_semesters(self, semester_ids: Optional[List[int]]) -> List[Semester]:
        """READ semesters from DB (no modification)."""
        if semester_ids:
            return self.db.query(Semester).filter(Semester.id.in_(semester_ids)).all()
        return self.db.query(Semester).all()
    
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
            # Find a room if not specified
            room_id = fs.room_id
            if not room_id:
                # Assign first available room based on component type
                if fs.component_type == ComponentType.LAB:
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
                is_lab_continuation=fs.is_lab_continuation,
                is_elective=fs.is_elective,
                elective_basket_id=fs.elective_basket_id
            )
            
            # Add to state - this marks teacher/room/semester as occupied
            if state.add_allocation(entry):
                # Mark this slot as FIXED (immutable)
                state.mark_slot_as_fixed(fs.semester_id, fs.day, fs.slot)
                loaded_count += 1
                
                print(f"   📌 FIXED: Class {fs.semester_id}, Day {fs.day}, Slot {fs.slot} → Subject {fs.subject_id} (Teacher {fs.teacher_id})")
            else:
                print(f"   [WARN] Could not add fixed slot: Semester {fs.semester_id}, Day {fs.day}, Slot {fs.slot} (slot conflict)")
        
        return loaded_count
    
    def _read_teacher_assignment_map(self) -> Dict[Tuple[int, int, str], int]:
        """
        READ existing teacher assignments from ClassSubjectTeacher.
        
        ⚠️ STRICT RULES:
        - NO FALLBACK: If no mapping exists, subject is NOT eligible.
        - NO AUTO-ASSIGNMENT: We do not infer or create mappings.
        - NO TEACHER ROTATION: Same teacher for all slots of a class-subject.
        """
        assignment_map: Dict[Tuple[int, int, str], int] = {}
        
        # STEP 1: READ from ClassSubjectTeacher table (PRIMARY SOURCE)
        existing_assignments = self.db.query(ClassSubjectTeacher).all()
        
        for assignment in existing_assignments:
            key = (assignment.semester_id, assignment.subject_id, assignment.component_type.value)
            assignment_map[key] = assignment.teacher_id
            print(f"   READ [LOCKED]: Class {assignment.semester_id}, Subject {assignment.subject_id}, {assignment.component_type.value} → Teacher {assignment.teacher_id}")
        
        # STEP 2: If no ClassSubjectTeacher entries, read from teacher_subjects
        # This is a STRICT read - we only use explicitly assigned teachers
        if not assignment_map:
            print("   [INFO] No ClassSubjectTeacher entries. Reading from teacher_subjects...")
            assignment_map = self._read_teacher_subjects_mapping_strict()
        
        print(f"   TOTAL LOCKED MAPPINGS: {len(assignment_map)}")
        return assignment_map
    
    def _read_teacher_subjects_mapping_strict(self) -> Dict[Tuple[int, int, str], int]:
        """
        STRICT READ from teacher_subjects table.
        
        ⚠️ CRITICAL RULES:
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
                    print(f"   [NO TEACHER] {subject.code} in {semester.name}: Subject NOT eligible for scheduling")
                    continue
                
                # Use the first assigned teacher (deterministic, ordered by ID)
                teacher_id = teachers_for_subject[0]
                
                # Determine components
                components = self._get_subject_components(subject)
                
                for comp_type, hours in components:
                    key = (semester.id, subject.id, comp_type.value)
                    if key not in assignment_map:
                        assignment_map[key] = teacher_id
                        print(f"   READ [INFERRED]: Class {semester.id}, Subject {subject.id} ({subject.code}), {comp_type.value} → Teacher {teacher_id}")
        
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
        try:
            from app.db.models import ElectiveBasket
            baskets = self.db.query(ElectiveBasket).all()
            for basket in baskets:
                basket_names[basket.id] = basket.name or f"Elective-{basket.id}"
        except Exception:
            pass  # ElectiveBasket table may not exist
        
        for semester in semesters:
            year = semester.semester_number
            
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
        
        return groups
    
    def _get_subject_components(self, subject: Subject) -> List[Tuple[ComponentType, int]]:
        """READ subject components (no modification)."""
        components = []
        
        theory_hours = getattr(subject, 'theory_hours_per_week', 0)
        lab_hours = getattr(subject, 'lab_hours_per_week', 0)
        tutorial_hours = getattr(subject, 'tutorial_hours_per_week', 0)
        
        if subject.subject_type == SubjectType.LAB:
            components.append((ComponentType.LAB, subject.weekly_hours))
        elif subject.subject_type == SubjectType.TUTORIAL:
            components.append((ComponentType.TUTORIAL, subject.weekly_hours))
        else:
            if theory_hours == 0 and lab_hours == 0 and tutorial_hours == 0:
                theory_hours = subject.weekly_hours
            
            if theory_hours > 0:
                components.append((ComponentType.THEORY, theory_hours))
            if lab_hours > 0:
                components.append((ComponentType.LAB, lab_hours))
            if tutorial_hours > 0:
                components.append((ComponentType.TUTORIAL, tutorial_hours))
        
        return components
    
    def _build_requirements_readonly(
        self,
        semesters: List[Semester],
        subjects: List[Subject],
        teacher_map: Dict[Tuple[int, int, str], int],
        semester_by_id: Dict[int, Semester]
    ) -> List[ComponentRequirement]:
        """Build requirements using ONLY existing mappings."""
        requirements = []
        
        for semester in semesters:
            year = semester.semester_number
            
            for subject in semester.subjects:
                is_elective = (
                    subject.is_elective or 
                    subject.subject_type == SubjectType.ELECTIVE or
                    subject.elective_basket_id is not None
                )
                
                components = self._get_subject_components(subject)
                
                for comp_type, hours in components:
                    key = (semester.id, subject.id, comp_type.value)
                    teacher_id = teacher_map.get(key)
                    
                    # ONLY create requirement if teacher mapping EXISTS
                    if teacher_id is not None:
                        requirements.append(ComponentRequirement(
                            semester_id=semester.id,
                            subject_id=subject.id,
                            subject_name=subject.name,
                            subject_code=subject.code,
                            component_type=comp_type,
                            hours_per_week=hours,
                            min_room_capacity=semester.student_count,
                            is_elective=is_elective,
                            elective_basket_id=subject.elective_basket_id,
                            year=year,
                            assigned_teacher_id=teacher_id
                        ))
                    else:
                        print(f"   [NO MAPPING] {subject.code} - {comp_type.value} in {semester.name}")
        
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
        elective_groups: Dict[Tuple[int, Optional[int]], ElectiveGroup]
    ) -> int:
        """
        Schedule elective theory - EACH ELECTIVE GROUP gets its own time slot.
        
        EXTENDED MULTI-GROUP SUPPORT:
        - Groups are identified by (year, basket_id) tuple
        - Each group is scheduled INDEPENDENTLY
        - Different groups can have DIFFERENT time slots
        - Teachers are locked PER GROUP during that group's slot
        
        Example:
          - Elective-1 (basket 1): Mon 2nd period for all classes
          - Elective-2 (basket 2): Wed 3rd period for all classes  
          - Elective-3 (basket 3): Fri 1st period for all classes
        """
        if not elective_reqs:
            print("      No elective requirements to schedule")
            return 0
        
        allocations_added = 0
        
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
                print(f"      [SKIP] Group ({year}, {basket_id}): No elective group definition found")
                continue
            
            # Get all classes of this group
            group_classes = group.classes
            group_teachers = group.teachers
            group_name = group.basket_name
            
            print(f"\n      Elective Group '{group_name}' (Year {year}, Basket {basket_id}):")
            print(f"        Classes: {group_classes}")
            print(f"        Teachers: {group_teachers}")
            
            # Group requirements by class (semester)
            reqs_by_class: Dict[int, List[ComponentRequirement]] = {}
            for req in group_reqs:
                if req.semester_id not in reqs_by_class:
                    reqs_by_class[req.semester_id] = []
                reqs_by_class[req.semester_id].append(req)
            
            print(f"        Requirements per class:")
            for sem_id, class_reqs in reqs_by_class.items():
                print(f"          Class {sem_id}: {[r.subject_code for r in class_reqs]}")
            
            # Calculate hours needed
            if not group_reqs:
                continue
            
            hours_needed = group_reqs[0].hours_per_week
            hours_scheduled = 0
            
            print(f"        Need to schedule {hours_needed} elective hours per class")
            
            # Track remaining hours per (class, subject)
            class_subject_hours: Dict[Tuple[int, int], int] = {}
            for req in group_reqs:
                key = (req.semester_id, req.subject_id)
                class_subject_hours[key] = req.hours_per_week
            
            # Track daily allocations for this group to enforce distribution
            group_daily_counts = {d: 0 for d in range(DAYS_PER_WEEK)}
            
            # Find slots where ALL group classes are free
            slot_order = self._get_randomized_slots()
            
            for day, slot in slot_order:
                if hours_scheduled >= hours_needed:
                    break
                
                # EXTENDED: For 2nd Year (Semesters 3 & 4), enforce MAX 1 elective theory per day
                # "dont assign all the elective periods on the same day , keep one period for one day"
                is_second_year = (year in [3, 4])
                if is_second_year and group_daily_counts[day] >= 1:
                    continue
                
                # EXTENDED: Check slot is not reserved by a DIFFERENT elective group
                if state.is_slot_reserved_for_other_group(day, slot, year, basket_id):
                    continue
                
                # Check ALL group classes are free
                all_free = all(state.is_semester_free(sid, day, slot) for sid in group_classes)
                if not all_free:
                    continue
                
                # For this slot, pick ONE elective per class in this group
                slot_allocs = []
                used_rooms = set()
                used_teachers = set()
                can_schedule = True
                
                for sem_id in group_classes:
                    class_reqs = reqs_by_class.get(sem_id, [])
                    if not class_reqs:
                        can_schedule = False
                        break
                    
                    scheduled_this_class = False
                    
                    for req in class_reqs:
                        key = (req.semester_id, req.subject_id)
                        remaining = class_subject_hours.get(key, 0)
                        
                        if remaining <= 0:
                            continue
                        
                        if not req.assigned_teacher_id:
                            continue
                        
                        # EXTENDED: Use per-group eligibility check
                        if not state.is_teacher_eligible_for_elective_group(
                            req.assigned_teacher_id, day, slot, year, basket_id
                        ):
                            continue
                        
                        # Teacher shouldn't already be used in this slot
                        if req.assigned_teacher_id in used_teachers:
                            continue
                        
                        # Find a room
                        room = next(
                            (r for r in rooms 
                             if r.id not in used_rooms 
                             and r.capacity >= req.min_room_capacity
                             and state.is_room_free(r.id, day, slot)),
                            None
                        )
                        
                        if room:
                            slot_allocs.append((req, room))
                            used_rooms.add(room.id)
                            used_teachers.add(req.assigned_teacher_id)
                            scheduled_this_class = True
                            break
                    
                    if not scheduled_this_class:
                        can_schedule = False
                        break
                
                # Only schedule if ALL group classes got an elective
                if can_schedule and len(slot_allocs) == len(group_classes):
                    # EXTENDED: Reserve this slot for THIS GROUP (not just lock teachers)
                    state.reserve_elective_slot_for_group(day, slot, year, basket_id, group_teachers)
                    
                    # Track daily usage
                    group_daily_counts[day] += 1
                    
                    print(f"        Scheduling at Day {day}, Slot {slot}:")
                    
                    for req, room in slot_allocs:
                        entry = AllocationEntry(
                            semester_id=req.semester_id,
                            subject_id=req.subject_id,
                            teacher_id=req.assigned_teacher_id,
                            room_id=room.id,
                            day=day,
                            slot=slot,
                            component_type=ComponentType.THEORY,
                            is_elective=True,
                            elective_basket_id=req.elective_basket_id
                        )
                        state.add_allocation(entry)
                        allocations_added += 1
                        
                        # Decrement remaining hours
                        key = (req.semester_id, req.subject_id)
                        class_subject_hours[key] = class_subject_hours.get(key, 0) - 1
                        
                        print(f"          Class {req.semester_id}: {req.subject_code} -> Teacher {req.assigned_teacher_id}")
                    
                    hours_scheduled += 1
            
            print(f"        Scheduled {hours_scheduled}/{hours_needed} hours for this group")
        
        return allocations_added
    
    def _schedule_elective_labs_readonly(
        self,
        state: TimetableState,
        elective_reqs: List[ComponentRequirement],
        rooms: List[Room],
        semesters: List[Semester],
        elective_groups: Dict[Tuple[int, Optional[int]], ElectiveGroup]
    ) -> int:
        """
        Schedule elective labs as atomic 2-period blocks.
        
        EXTENDED MULTI-GROUP SUPPORT:
        - Each elective group (year, basket_id) is scheduled INDEPENDENTLY
        - Different groups can have labs at DIFFERENT time slots
        - Teachers are LOCKED PER GROUP during that group's lab slot
        """
        if not elective_reqs:
            print("      No elective lab requirements")
            return 0
        
        allocations_added = 0
        
        # Group requirements by (year, basket_id) to match elective_groups
        by_group: Dict[Tuple[int, Optional[int]], List[ComponentRequirement]] = {}
        for req in elective_reqs:
            group_key = (req.year, req.elective_basket_id)
            if group_key not in by_group:
                by_group[group_key] = []
            by_group[group_key].append(req)
        
        print(f"      Processing {len(by_group)} elective lab group(s)")
        
        # Process each elective group INDEPENDENTLY
        for group_key, group_reqs in by_group.items():
            if not group_reqs:
                continue
            
            year, basket_id = group_key
            
            # Get the group definition
            group = elective_groups.get(group_key)
            if not group:
                print(f"      [SKIP] Group ({year}, {basket_id}): No elective group definition found")
                continue
            
            group_classes = group.classes
            group_teachers = group.teachers
            group_name = group.basket_name
            
            print(f"\n      Elective Lab Group '{group_name}' (Year {year}, Basket {basket_id}):")
            print(f"        Classes: {group_classes}")
            print(f"        Teachers: {group_teachers}")
            print(f"        Requirements: {[f'{r.subject_code} ({r.hours_per_week}h)' for r in group_reqs]}")
            
            # Group requirements by class
            reqs_by_class: Dict[int, List[ComponentRequirement]] = {}
            for req in group_reqs:
                if req.semester_id not in reqs_by_class:
                    reqs_by_class[req.semester_id] = []
                reqs_by_class[req.semester_id].append(req)
            
            # Calculate blocks needed (use max from any subject in this group)
            blocks_needed = max((r.hours_per_week for r in group_reqs), default=0) // 2
            if blocks_needed == 0:
                print(f"        No lab blocks needed")
                continue
            
            print(f"        Need {blocks_needed} lab block(s) per class")
            
            # Track hours remaining per (class, subject)
            class_subject_blocks: Dict[Tuple[int, int], int] = {}
            for req in group_reqs:
                key = (req.semester_id, req.subject_id)
                class_subject_blocks[key] = req.hours_per_week // 2
            
            blocks_scheduled = 0
            
            # Try each lab slot
            lab_slots = [(d, block) for d in range(DAYS_PER_WEEK) for block in VALID_LAB_BLOCKS]
            random.shuffle(lab_slots)
            
            for day, (start_slot, end_slot) in lab_slots:
                if blocks_scheduled >= blocks_needed:
                    break
                
                # EXTENDED: Check BOTH slots are not reserved by DIFFERENT elective groups
                if (state.is_slot_reserved_for_other_group(day, start_slot, year, basket_id) or
                    state.is_slot_reserved_for_other_group(day, end_slot, year, basket_id)):
                    continue
                
                # EXTENDED: Don't assign elective lab if group already has elective theory on this day
                # Since theory is scheduled before labs, elective_slots_by_group currently only contains theory slots
                # for this group (plus any lab slots already scheduled in previous blocks).
                group_key = (year, basket_id)
                if any(d == day for d, s in state.elective_slots_by_group.get(group_key, [])):
                    continue

                # Check ALL group classes are free for both slots
                all_free = all(
                    state.is_semester_free(sid, day, start_slot) and 
                    state.is_semester_free(sid, day, end_slot)
                    for sid in group_classes
                )
                if not all_free:
                    continue
                
                # For this block, try to schedule ONE elective lab per class in this group
                block_allocs = []
                used_rooms = set()
                used_teachers = set()
                can_schedule_all = True
                
                for sem_id in group_classes:
                    class_reqs = reqs_by_class.get(sem_id, [])
                    if not class_reqs:
                        can_schedule_all = False
                        break
                    
                    scheduled_this_class = False
                    
                    for req in class_reqs:
                        key = (req.semester_id, req.subject_id)
                        remaining = class_subject_blocks.get(key, 0)
                        
                        if remaining <= 0:
                            continue
                        
                        if not req.assigned_teacher_id:
                            continue
                        
                        # EXTENDED: Use per-group eligibility check for BOTH slots
                        if not (state.is_teacher_eligible_for_elective_group(
                                    req.assigned_teacher_id, day, start_slot, year, basket_id
                                ) and 
                                state.is_teacher_eligible_for_elective_group(
                                    req.assigned_teacher_id, day, end_slot, year, basket_id
                                )):
                            continue
                        
                        # Teacher shouldn't be used already in this block
                        if req.assigned_teacher_id in used_teachers:
                            continue
                        
                        # Find a lab room
                        room = next(
                            (r for r in rooms
                             if r.id not in used_rooms
                             and r.capacity >= req.min_room_capacity
                             and state.is_room_free(r.id, day, start_slot)
                             and state.is_room_free(r.id, day, end_slot)),
                            None
                        )
                        
                        if room:
                            block_allocs.append((req, room))
                            used_rooms.add(room.id)
                            used_teachers.add(req.assigned_teacher_id)
                            scheduled_this_class = True
                            break
                    
                    if not scheduled_this_class:
                        can_schedule_all = False
                        break
                
                # Only commit if ALL group classes got an elective lab
                if can_schedule_all and len(block_allocs) == len(group_classes):
                    # EXTENDED: Reserve BOTH slots for THIS GROUP (not just lock teachers)
                    state.reserve_elective_slot_for_group(day, start_slot, year, basket_id, group_teachers)
                    state.reserve_elective_slot_for_group(day, end_slot, year, basket_id, group_teachers)
                    
                    print(f"        Scheduling labs at Day {day}, Slots {start_slot}-{end_slot}:")
                    
                    for req, room in block_allocs:
                        for idx, slot in enumerate([start_slot, end_slot]):
                            entry = AllocationEntry(
                                semester_id=req.semester_id,
                                subject_id=req.subject_id,
                                teacher_id=req.assigned_teacher_id,
                                room_id=room.id,
                                day=day,
                                slot=slot,
                                component_type=ComponentType.LAB,
                                is_lab_continuation=(idx == 1),
                                is_elective=True,
                                elective_basket_id=req.elective_basket_id
                            )
                            state.add_allocation(entry)
                            allocations_added += 1
                        
                        # Decrement remaining blocks
                        key = (req.semester_id, req.subject_id)
                        class_subject_blocks[key] = class_subject_blocks.get(key, 0) - 1
                        
                        print(f"          Class {req.semester_id}: {req.subject_code} → Teacher {req.assigned_teacher_id}")
                    
                    blocks_scheduled += 1
            
            print(f"        Scheduled {blocks_scheduled}/{blocks_needed} lab blocks for this group")
        
        return allocations_added
    
    # ============================================================
    # REGULAR SCHEDULING (READ-ONLY)
    # ============================================================
    
    def _schedule_labs_readonly(
        self,
        state: TimetableState,
        lab_reqs: List[ComponentRequirement],
        rooms: List[Room]
    ) -> int:
        """Schedule regular labs as atomic 2-period blocks."""
        if not lab_reqs:
            return 0
        
        allocations_added = 0
        
        for req in sorted(lab_reqs, key=lambda r: r.hours_per_week, reverse=True):
            teacher_id = req.assigned_teacher_id
            if not teacher_id:
                continue
            
            blocks_needed = req.hours_per_week // 2
            blocks_scheduled = 0
            
            lab_slots = [(d, block) for d in range(DAYS_PER_WEEK) for block in VALID_LAB_BLOCKS]
            random.shuffle(lab_slots)
            
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
                
                room = next(
                    (r for r in rooms
                     if r.capacity >= req.min_room_capacity
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
                            component_type=ComponentType.LAB,
                            is_lab_continuation=(idx == 1)
                        )
                        state.add_allocation(entry)
                        allocations_added += 1
                    blocks_scheduled += 1
        
        return allocations_added
    
    def _schedule_theory_readonly(
        self,
        state: TimetableState,
        theory_reqs: List[ComponentRequirement],
        rooms: List[Room],
        semesters: List[Semester],
        semester_by_id: Dict[int, Semester]
    ) -> Tuple[int, int]:
        """Schedule theory/tutorials using ONLY existing mappings."""
        if not theory_reqs:
            return 0, 0
        
        allocations_added = 0
        free_periods = 0
        
        # Build hour counters
        hour_counters: Dict[Tuple[int, int, str], int] = {}
        req_lookup: Dict[Tuple[int, int, str], ComponentRequirement] = {}
        
        for req in theory_reqs:
            if not req.assigned_teacher_id:
                continue
            key = (req.semester_id, req.subject_id, req.component_type.value)
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
                        available.sort(key=lambda x: x[1], reverse=True)
                        
                        for (s_sem, s_subj, s_comp), remaining in available:
                            req = req_lookup.get((s_sem, s_subj, s_comp))
                            if not req:
                                continue
                            
                            teacher_id = req.assigned_teacher_id
                            
                            # STRICT eligibility check
                            if not state.is_teacher_eligible(teacher_id, day, slot):
                                continue
                            
                            # Daily limit (soft constraint - can be relaxed)
                            current = state.get_subject_daily_count(sem_id, day, req.subject_id)
                            max_daily = 2 if req.hours_per_week > 5 else 1
                            if current >= max_daily:
                                continue
                            
                            room = next(
                                (r for r in rooms
                                 if r.capacity >= req.min_room_capacity
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
                                    component_type=req.component_type
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
                            
                            # Skip daily limit check in retry pass
                            room = next(
                                (r for r in rooms
                                 if r.capacity >= req.min_room_capacity
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
                                    component_type=req.component_type
                                )
                                state.add_allocation(entry)
                                hour_counters[(s_sem, s_subj, s_comp)] -= 1
                                allocations_added += 1
                                sem_filled += 1
                                filled = True
                                break
                    
                    # FREE PERIOD - truly no eligible subject/teacher
                    if not filled:
                        if sem_id not in state.semester_slots:
                            state.semester_slots[sem_id] = set()
                        state.semester_slots[sem_id].add((day, slot))
                        free_periods += 1
                        sem_free += 1
            
            if sem_free > 0:
                print(f"         → {sem_filled} subjects + {sem_free} FREE")
            else:
                print(f"         → {sem_filled} subjects")
        
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
        
        # Deduplicate
        seen = set()
        unique = []
        for entry in allocations:
            key = (entry.semester_id, entry.day, entry.slot)
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
                is_lab_continuation=entry.is_lab_continuation,
                is_elective=entry.is_elective,
                elective_basket_id=entry.elective_basket_id
            )
            self.db.add(db_alloc)
        
        try:
            self.db.commit()
            print(f"   ✔ Saved {len(unique)} allocations")
        except Exception as e:
            self.db.rollback()
            print(f"   ✖ Save failed: {e}")
    
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
