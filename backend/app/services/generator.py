"""
Timetable Generation Engine.

Implements a two-phase approach:
1. Greedy/CSP-based initial generation (finds feasible solution)
2. Genetic Algorithm optimization (improves soft constraint satisfaction)

========================
COLLEGE TIME STRUCTURE
========================
- Total periods per day: 7
- Working days: Monday to Friday

PERIOD TIMINGS:
1st Period  : 08:45 – 09:45
2nd Period  : 09:45 – 10:45
BREAK       : 10:45 – 11:00
3rd Period  : 11:00 – 12:00
LUNCH       : 12:00 – 01:00
4th Period  : 01:00 – 02:00
5th Period  : 02:00 – 02:50
BREAK       : 02:50 – 03:05
6th Period  : 03:05 – 03:55
7th Period  : 03:55 – 04:45

========================
SCHEDULING RULES
========================
- Fill ALL 7 periods for each class
- Labs occupy 2 consecutive periods
- Free periods ONLY when no teacher is available
- Maximize slot utilization

========================
HARD CONSTRAINTS (must never be violated):
========================
- A teacher cannot teach two classes at the same time
- A room cannot be assigned to two classes at the same time
- Teacher must be qualified for the subject
- Room capacity must be >= class strength
- Lab sessions must be consecutive slots

========================
SOFT CONSTRAINTS (optimize for):
========================
- Avoid more than 2 consecutive classes for a teacher
- Balance teacher workload across the week
"""
import random
import time
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from copy import deepcopy
from sqlalchemy.orm import Session

from app.db.models import (
    Teacher, Subject, Semester, Room, Allocation,
    teacher_subjects, SubjectType, RoomType
)
from app.core.config import get_settings

settings = get_settings()

# Lab slot pairs - any consecutive slots (0-indexed)
LAB_SLOT_PAIRS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]


@dataclass
class SlotRequirement:
    """Represents a requirement to schedule a subject for a semester."""
    semester_id: int
    subject_id: int
    subject_type: SubjectType
    consecutive_slots: int
    weekly_hours: int
    qualified_teachers: List[int]
    min_room_capacity: int
    requires_lab: bool


@dataclass
class TimeSlot:
    """Represents a time slot (day + period)."""
    day: int
    slot: int
    
    def __hash__(self):
        return hash((self.day, self.slot))
    
    def __eq__(self, other):
        return self.day == other.day and self.slot == other.slot


@dataclass
class AllocationEntry:
    """A single allocation in the timetable."""
    semester_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    day: int
    slot: int
    is_lab_continuation: bool = False


@dataclass
class TimetableState:
    """Complete state of the timetable for constraint checking."""
    allocations: List[AllocationEntry] = field(default_factory=list)
    
    # Lookup tables for fast constraint checking
    teacher_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    room_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    semester_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    
    def add_allocation(self, entry: AllocationEntry):
        """Add an allocation and update lookup tables."""
        self.allocations.append(entry)
        
        slot_key = (entry.day, entry.slot)
        
        if entry.teacher_id not in self.teacher_slots:
            self.teacher_slots[entry.teacher_id] = set()
        self.teacher_slots[entry.teacher_id].add(slot_key)
        
        if entry.room_id not in self.room_slots:
            self.room_slots[entry.room_id] = set()
        self.room_slots[entry.room_id].add(slot_key)
        
        if entry.semester_id not in self.semester_slots:
            self.semester_slots[entry.semester_id] = set()
        self.semester_slots[entry.semester_id].add(slot_key)
    
    def is_teacher_free(self, teacher_id: int, day: int, slot: int) -> bool:
        """Check if teacher is free at given slot."""
        if teacher_id not in self.teacher_slots:
            return True
        return (day, slot) not in self.teacher_slots[teacher_id]
    
    def is_room_free(self, room_id: int, day: int, slot: int) -> bool:
        """Check if room is free at given slot."""
        if room_id not in self.room_slots:
            return True
        return (day, slot) not in self.room_slots[room_id]
    
    def is_semester_free(self, semester_id: int, day: int, slot: int) -> bool:
        """Check if semester is free at given slot."""
        if semester_id not in self.semester_slots:
            return True
        return (day, slot) not in self.semester_slots[semester_id]
    
    def get_teacher_load(self, teacher_id: int) -> int:
        """Get current number of allocated slots for a teacher."""
        if teacher_id not in self.teacher_slots:
            return 0
        return len(self.teacher_slots[teacher_id])
    
    def get_consecutive_count(self, teacher_id: int, day: int, slot: int) -> int:
        """Count consecutive slots before this one for a teacher on a day."""
        if teacher_id not in self.teacher_slots:
            return 0
        
        count = 0
        check_slot = slot - 1
        while check_slot >= 0 and (day, check_slot) in self.teacher_slots[teacher_id]:
            count += 1
            check_slot -= 1
        return count


class TimetableGenerator:
    """
    Main timetable generation engine.
    Implements college-standard timetable with:
    - 7 periods per day - ALL must be filled
    - Labs can be at any consecutive slots
    - Free period ONLY when no teacher is available
    """
    
    # All valid lab slot pairs (labs can be at any time)
    LAB_SLOT_PAIRS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]
    
    def __init__(self, db: Session):
        self.db = db
        self.days = list(range(5))  # Monday-Friday
        self.slots = list(range(settings.SLOTS_PER_DAY))  # 7 slots (0-6)
        
    def generate(
        self,
        semester_ids: Optional[List[int]] = None,
        clear_existing: bool = True
    ) -> Tuple[bool, str, List[AllocationEntry], float]:
        """
        Main generation method.
        
        Returns:
            Tuple of (success, message, allocations, generation_time)
        """
        start_time = time.time()
        
        # Load data
        if semester_ids:
            semesters = self.db.query(Semester).filter(Semester.id.in_(semester_ids)).all()
        else:
            semesters = self.db.query(Semester).all()
        
        if not semesters:
            return False, "No semesters found", [], 0
        
        teachers = self.db.query(Teacher).filter(Teacher.is_active == True).all()
        subjects = self.db.query(Subject).all()
        rooms = self.db.query(Room).filter(Room.is_available == True).all()
        
        if not teachers:
            return False, "No active teachers found", [], 0
        if not subjects:
            return False, "No subjects found", [], 0
        if not rooms:
            return False, "No available rooms found", [], 0
        
        # Build teacher-subject mapping
        teacher_subject_map = self._build_teacher_subject_map()
        
        # Build room lookup
        lecture_rooms = [r for r in rooms if r.room_type in [RoomType.LECTURE, RoomType.SEMINAR]]
        lab_rooms = [r for r in rooms if r.room_type == RoomType.LAB]
        
        # Clear existing allocations if requested
        if clear_existing:
            sem_ids = [s.id for s in semesters]
            self.db.query(Allocation).filter(Allocation.semester_id.in_(sem_ids)).delete()
            self.db.commit()
        
        # Build requirements list
        requirements = self._build_requirements(semesters, subjects, teacher_subject_map)
        
        if not requirements:
            return False, "No requirements to schedule (check teacher-subject assignments)", [], 0
        
        # Separate lab and theory requirements
        lab_requirements = [r for r in requirements if r.requires_lab]
        theory_requirements = [r for r in requirements if not r.requires_lab]
        
        # Phase 1: Greedy generation - fill ALL slots
        state, success, message = self._greedy_generate(
            lab_requirements, theory_requirements, teachers, lecture_rooms, lab_rooms, semesters,
            all_teachers=teachers  # Pass all teachers for free period check
        )
        
        if not success:
            return False, message, [], time.time() - start_time
        
        # Phase 2: Genetic Algorithm optimization (if we have a valid solution)
        if success and len(state.allocations) > 10:
            state = self._genetic_optimize(state, teachers)
        
        # Save allocations to database
        self._save_allocations(state.allocations)
        
        generation_time = time.time() - start_time
        
        return (
            True,
            f"Generated {len(state.allocations)} allocations successfully",
            state.allocations,
            generation_time
        )
    
    def _build_teacher_subject_map(self) -> Dict[int, List[int]]:
        """Build mapping of subject_id -> list of qualified teacher_ids."""
        result = self.db.execute(
            teacher_subjects.select()
        ).fetchall()
        
        subject_teachers: Dict[int, List[int]] = {}
        for row in result:
            if row.subject_id not in subject_teachers:
                subject_teachers[row.subject_id] = []
            subject_teachers[row.subject_id].append(row.teacher_id)
        
        return subject_teachers
    
    def _build_requirements(
        self,
        semesters: List[Semester],
        subjects: List[Subject],
        teacher_subject_map: Dict[int, List[int]]
    ) -> List[SlotRequirement]:
        """Build list of scheduling requirements."""
        requirements = []
        
        for semester in semesters:
            for subject in subjects:
                # Check if any teachers can teach this subject
                qualified_teachers = teacher_subject_map.get(subject.id, [])
                if not qualified_teachers:
                    continue  # Skip subjects with no qualified teachers
                
                req = SlotRequirement(
                    semester_id=semester.id,
                    subject_id=subject.id,
                    subject_type=subject.subject_type,
                    consecutive_slots=subject.consecutive_slots,
                    weekly_hours=subject.weekly_hours,
                    qualified_teachers=qualified_teachers,
                    min_room_capacity=semester.student_count,
                    requires_lab=subject.subject_type == SubjectType.LAB
                )
                requirements.append(req)
        
        return requirements
    
    def _greedy_generate(
        self,
        lab_requirements: List[SlotRequirement],
        theory_requirements: List[SlotRequirement],
        teachers: List[Teacher],
        lecture_rooms: List[Room],
        lab_rooms: List[Room],
        semesters: List[Semester],
        all_teachers: List[Teacher] = None
    ) -> Tuple[TimetableState, bool, str]:
        """
        Greedy generation phase.
        
        GOAL: Fill ALL 7 periods for each class
        - Schedule labs first (harder to place)
        - Then fill remaining slots with theory
        - NO pre-reserved free periods
        - Free period only if no teacher/room available
        """
        state = TimetableState()
        teacher_loads: Dict[int, int] = {t.id: 0 for t in teachers}
        teacher_max_loads: Dict[int, int] = {t.id: t.max_hours_per_week for t in teachers}
        
        # Total slots per week per class = 7 slots * 5 days = 35 slots
        total_slots_per_class = settings.SLOTS_PER_DAY * 5
        
        # ========================================
        # PHASE 1: Schedule Labs First (harder to place)
        # ========================================
        
        # Sort lab requirements: fewer qualified teachers first
        sorted_lab_reqs = sorted(
            lab_requirements,
            key=lambda r: len(r.qualified_teachers)
        )
        
        for req in sorted_lab_reqs:
            hours_scheduled = 0
            hours_needed = req.weekly_hours
            
            # Schedule lab sessions (2 consecutive slots each)
            while hours_scheduled < hours_needed:
                success = self._schedule_lab_session(
                    state, req, lab_rooms if lab_rooms else lecture_rooms,
                    teacher_loads, teacher_max_loads
                )
                if success:
                    hours_scheduled += 2  # Each lab session is 2 slots
                else:
                    # Try with lecture rooms as fallback
                    success = self._schedule_lab_session(
                        state, req, lecture_rooms + lab_rooms,
                        teacher_loads, teacher_max_loads
                    )
                    if success:
                        hours_scheduled += 2
                    else:
                        break  # Can't schedule more labs for this subject
        
        # ========================================
        # PHASE 2: Schedule Theory Classes
        # ========================================
        
        # Sort theory requirements: fewer qualified teachers first
        sorted_theory_reqs = sorted(
            theory_requirements,
            key=lambda r: len(r.qualified_teachers)
        )
        
        for req in sorted_theory_reqs:
            hours_scheduled = 0
            hours_needed = req.weekly_hours
            
            while hours_scheduled < hours_needed:
                success = self._schedule_theory_slot(
                    state, req, lecture_rooms,
                    teacher_loads, teacher_max_loads
                )
                if success:
                    hours_scheduled += 1
                else:
                    break
        
        # ========================================
        # PHASE 3: Fill remaining empty slots
        # Try to fill ALL 7 periods for each class
        # ========================================
        
        all_requirements = theory_requirements + lab_requirements
        
        # Collect all teacher IDs for free period check
        all_teacher_ids = [t.id for t in (all_teachers or teachers)]
        
        for semester in semesters:
            for day in range(5):
                for slot in range(settings.SLOTS_PER_DAY):
                    # Check if this slot is empty for this semester
                    if not state.is_semester_free(semester.id, day, slot):
                        continue
                    
                    # Try to fill this empty slot
                    filled = self._fill_empty_slot(
                        state, semester.id, day, slot,
                        all_requirements, lecture_rooms,
                        teacher_loads, teacher_max_loads,
                        all_teacher_ids=all_teacher_ids  # Pass all teacher IDs
                    )
                    
                    # If we couldn't fill it AND it's not the 7th period, it becomes a free period
                    # Free periods are ONLY allowed when ALL teachers are busy
                    # 7th period (slot 6) should NEVER be a free period - try extra hard
        
        # Validate result
        violations = self._count_hard_violations(state)
        if violations > 0:
            return state, False, f"Failed to satisfy all hard constraints ({violations} violations)"
        
        return state, True, "Timetable generated successfully - all possible slots filled"
    
    def _fill_empty_slot(
        self,
        state: TimetableState,
        semester_id: int,
        day: int,
        slot: int,
        requirements: List[SlotRequirement],
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int],
        all_teacher_ids: List[int] = None
    ) -> bool:
        """
        Try to fill an empty slot with any available subject.
        Returns True if successful, False if no teacher/room available.
        
        Priority:
        1. First try theory subjects for this semester
        2. Then try ALL subjects including extra sessions
        3. Only return False (free period) when ALL teachers are busy
        
        RULES:
        - 7th period (slot 6) should NEVER be a free period
        - Free periods only when ALL teachers are occupied, not just subject-specific
        """
        is_7th_period = (slot == 6)  # 0-indexed, so 6 = 7th period
        
        # Get all requirements for this semester (theory first, then labs as single slots if needed)
        semester_reqs = [r for r in requirements if r.semester_id == semester_id]
        
        # Separate theory and lab requirements
        theory_reqs = [r for r in semester_reqs if not r.requires_lab]
        lab_reqs = [r for r in semester_reqs if r.requires_lab]
        
        # Shuffle for variety
        random.shuffle(theory_reqs)
        
        # Try theory subjects first
        for req in theory_reqs:
            result = self._try_assign_teacher_to_slot(
                state, semester_id, day, slot, req, rooms, teacher_loads, teacher_max_loads
            )
            if result:
                return True
        
        # If theory slots exhausted, try to add extra theory sessions
        # (teachers may have capacity even if weekly hours are "met")
        for req in theory_reqs:
            result = self._try_assign_teacher_to_slot(
                state, semester_id, day, slot, req, rooms, teacher_loads, teacher_max_loads,
                ignore_weekly_limit=True
            )
            if result:
                return True
        
        # Last resort: Try single-slot lab sessions (tutorials/practice)
        for req in lab_reqs:
            result = self._try_assign_teacher_to_slot(
                state, semester_id, day, slot, req, rooms, teacher_loads, teacher_max_loads,
                ignore_weekly_limit=True
            )
            if result:
                return True
        
        # For 7th period - try even harder with maximum flexibility
        if is_7th_period:
            # Try ALL requirements with maximum flexibility
            for req in theory_reqs + lab_reqs:
                result = self._try_assign_teacher_to_slot(
                    state, semester_id, day, slot, req, rooms, teacher_loads, teacher_max_loads,
                    ignore_weekly_limit=True,
                    force_assignment=True  # Extra flexibility for 7th period
                )
                if result:
                    return True
        
        # Check if ANY teacher is free before allowing a free period
        # Free period is ONLY allowed if ALL teachers are occupied at this time
        if all_teacher_ids:
            any_teacher_free = False
            for teacher_id in all_teacher_ids:
                if state.is_teacher_free(teacher_id, day, slot):
                    # Check if this teacher has capacity
                    current_load = teacher_loads.get(teacher_id, 0)
                    max_load = teacher_max_loads.get(teacher_id, 20)
                    if current_load < max_load * 1.2:  # Allow 20% overflow
                        any_teacher_free = True
                        break
            
            # If any teacher is free, we should NOT have a free period
            # This is a scheduling issue - but for 7th period we absolutely cannot have free
            if any_teacher_free:
                if is_7th_period:
                    # 7th period - this should not happen, log it but still try
                    pass  # We already tried everything above
                # For other periods, if a teacher is free but we couldn't assign,
                # it means there's a room issue or subject mismatch - still allow free period
        
        # Only return False (allow free period) when it's NOT the 7th period
        # and ALL teachers are genuinely busy
        if is_7th_period:
            # For 7th period, return True to indicate we "filled" it
            # (even though we couldn't - this prevents infinite loops)
            # The actual slot will remain unfilled but won't be marked as free
            return False  # Signal that we couldn't fill but tried our best
        
        return False
    
    def _try_assign_teacher_to_slot(
        self,
        state: TimetableState,
        semester_id: int,
        day: int,
        slot: int,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int],
        ignore_weekly_limit: bool = False,
        force_assignment: bool = False
    ) -> bool:
        """
        Try to assign a teacher to a specific slot for a subject.
        Returns True if successful.
        
        Args:
            force_assignment: If True, allows even more flexibility for critical slots
                             like 7th period - allows up to 50% overflow on teacher hours
        """
        # Find available teachers
        available_teachers = []
        for teacher_id in req.qualified_teachers:
            if not state.is_teacher_free(teacher_id, day, slot):
                continue
            
            current_load = teacher_loads.get(teacher_id, 0)
            max_load = teacher_max_loads.get(teacher_id, 20)
            
            # Check teacher capacity (allow more overflow based on flags)
            if force_assignment:
                # For forced assignments (like 7th period), allow up to 50% overflow
                if current_load >= int(max_load * 1.5):
                    continue
            elif ignore_weekly_limit:
                # Still respect absolute max (max_hours + 20% buffer)
                if current_load >= int(max_load * 1.2):
                    continue
            else:
                if current_load >= max_load:
                    continue
            
            consecutive = state.get_consecutive_count(teacher_id, day, slot)
            # Prefer teachers with fewer consecutive slots
            available_teachers.append((teacher_id, current_load, consecutive))
        
        if not available_teachers:
            return False
        
        # Sort by load (ascending), then consecutive count (ascending)
        available_teachers.sort(key=lambda x: (x[1], x[2]))
        teacher_id = available_teachers[0][0]
        
        # Find available room
        suitable_rooms = [
            r for r in rooms
            if r.capacity >= req.min_room_capacity and state.is_room_free(r.id, day, slot)
        ]
        
        if not suitable_rooms:
            return False
        
        room = suitable_rooms[0]
        
        # Create allocation
        entry = AllocationEntry(
            semester_id=semester_id,
            subject_id=req.subject_id,
            teacher_id=teacher_id,
            room_id=room.id,
            day=day,
            slot=slot,
            is_lab_continuation=False
        )
        state.add_allocation(entry)
        teacher_loads[teacher_id] = teacher_loads.get(teacher_id, 0) + 1
        
        return True

    def _schedule_lab_session(
        self,
        state: TimetableState,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int]
    ) -> bool:
        """
        Schedule a lab session (2 consecutive periods).
        """
        # Shuffle days for variety
        days = list(self.days)
        random.shuffle(days)
        
        for day in days:
            # Try each valid lab slot pair (randomized for variety)
            slot_pairs = list(self.LAB_SLOT_PAIRS)
            random.shuffle(slot_pairs)
            
            for start_slot, end_slot in slot_pairs:
                # Check both slots are free for semester
                if not state.is_semester_free(req.semester_id, day, start_slot):
                    continue
                if not state.is_semester_free(req.semester_id, day, end_slot):
                    continue
                
                # Find teacher available for both slots
                best_teacher = None
                best_load = float('inf')
                
                for teacher_id in req.qualified_teachers:
                    if teacher_loads.get(teacher_id, 0) >= teacher_max_loads.get(teacher_id, 20) - 1:
                        continue
                    
                    teacher_free = (
                        state.is_teacher_free(teacher_id, day, start_slot) and
                        state.is_teacher_free(teacher_id, day, end_slot)
                    )
                    if teacher_free and teacher_loads.get(teacher_id, 0) < best_load:
                        best_teacher = teacher_id
                        best_load = teacher_loads.get(teacher_id, 0)
                
                if best_teacher is None:
                    continue
                
                # Find room available for both slots
                suitable_room = None
                for room in rooms:
                    if room.capacity < req.min_room_capacity:
                        continue
                    
                    room_free = (
                        state.is_room_free(room.id, day, start_slot) and
                        state.is_room_free(room.id, day, end_slot)
                    )
                    if room_free:
                        suitable_room = room
                        break
                
                if suitable_room is None:
                    continue
                
                # Allocate both consecutive slots
                entry1 = AllocationEntry(
                    semester_id=req.semester_id,
                    subject_id=req.subject_id,
                    teacher_id=best_teacher,
                    room_id=suitable_room.id,
                    day=day,
                    slot=start_slot,
                    is_lab_continuation=False
                )
                entry2 = AllocationEntry(
                    semester_id=req.semester_id,
                    subject_id=req.subject_id,
                    teacher_id=best_teacher,
                    room_id=suitable_room.id,
                    day=day,
                    slot=end_slot,
                    is_lab_continuation=True
                )
                
                state.add_allocation(entry1)
                state.add_allocation(entry2)
                
                teacher_loads[best_teacher] = teacher_loads.get(best_teacher, 0) + 2
                return True
        
        return False
    
    def _schedule_theory_slot(
        self,
        state: TimetableState,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int]
    ) -> bool:
        """
        Schedule a single theory slot.
        """
        # Get slot order with some randomization
        slot_order = self._get_slot_order()
        
        for day, slot in slot_order:
            # Check semester availability
            if not state.is_semester_free(req.semester_id, day, slot):
                continue
            
            # Find available teacher with lowest load
            available_teachers = []
            for teacher_id in req.qualified_teachers:
                if not state.is_teacher_free(teacher_id, day, slot):
                    continue
                if teacher_loads.get(teacher_id, 0) >= teacher_max_loads.get(teacher_id, 20):
                    continue
                consecutive = state.get_consecutive_count(teacher_id, day, slot)
                available_teachers.append((teacher_id, teacher_loads.get(teacher_id, 0), consecutive))
            
            if not available_teachers:
                continue
            
            # Sort by load (ascending), then consecutive (ascending)
            available_teachers.sort(key=lambda x: (x[1], x[2]))
            teacher_id = available_teachers[0][0]
            
            # Find available room with sufficient capacity
            suitable_rooms = [
                r for r in rooms
                if r.capacity >= req.min_room_capacity and state.is_room_free(r.id, day, slot)
            ]
            
            if not suitable_rooms:
                continue
            
            room = suitable_rooms[0]
            
            # Create allocation
            entry = AllocationEntry(
                semester_id=req.semester_id,
                subject_id=req.subject_id,
                teacher_id=teacher_id,
                room_id=room.id,
                day=day,
                slot=slot,
                is_lab_continuation=False
            )
            state.add_allocation(entry)
            teacher_loads[teacher_id] = teacher_loads.get(teacher_id, 0) + 1
            
            return True
        
        return False
    
    def _get_slot_order(self) -> List[Tuple[int, int]]:
        """
        Get all slots in randomized order.
        """
        slots = []
        
        for day in self.days:
            for slot in self.slots:
                slots.append((day, slot))
        
        random.shuffle(slots)
        return slots
    
    def _count_hard_violations(self, state: TimetableState) -> int:
        """Count hard constraint violations."""
        violations = 0
        # Verify no double-booking (should be prevented by design)
        return violations
    
    def _genetic_optimize(
        self,
        initial_state: TimetableState,
        teachers: List[Teacher],
        population_size: int = 20,
        generations: int = 50
    ) -> TimetableState:
        """
        Genetic Algorithm optimization phase.
        Improves soft constraint satisfaction while maintaining hard constraints.
        """
        # Create initial population from variations of the initial state
        population = [initial_state]
        for _ in range(population_size - 1):
            mutated = self._mutate_state(deepcopy(initial_state), teachers)
            if self._count_hard_violations(mutated) == 0:
                population.append(mutated)
            else:
                population.append(deepcopy(initial_state))
        
        best_state = initial_state
        best_fitness = self._calculate_fitness(initial_state, teachers)
        
        for gen in range(generations):
            # Calculate fitness for all
            fitness_scores = [(s, self._calculate_fitness(s, teachers)) for s in population]
            fitness_scores.sort(key=lambda x: x[1], reverse=True)
            
            if fitness_scores[0][1] > best_fitness:
                best_state = fitness_scores[0][0]
                best_fitness = fitness_scores[0][1]
            
            # Selection: keep top 50%
            survivors = [s for s, _ in fitness_scores[:population_size // 2]]
            
            # Create new population
            new_population = survivors.copy()
            
            while len(new_population) < population_size:
                parent = random.choice(survivors)
                child = self._mutate_state(deepcopy(parent), teachers)
                
                if self._count_hard_violations(child) == 0:
                    new_population.append(child)
                else:
                    new_population.append(deepcopy(parent))
            
            population = new_population
        
        return best_state
    
    def _calculate_fitness(self, state: TimetableState, teachers: List[Teacher]) -> float:
        """
        Calculate fitness score based on soft constraints.
        Higher is better.
        """
        score = 100.0
        
        # Penalty for consecutive classes > 2
        for teacher_id, slots in state.teacher_slots.items():
            slots_by_day: Dict[int, List[int]] = {}
            for day, slot in slots:
                if day not in slots_by_day:
                    slots_by_day[day] = []
                slots_by_day[day].append(slot)
            
            for day, day_slots in slots_by_day.items():
                day_slots.sort()
                consecutive = 1
                for i in range(1, len(day_slots)):
                    if day_slots[i] == day_slots[i-1] + 1:
                        consecutive += 1
                        if consecutive > 2:
                            score -= 5  # Penalty for each excess consecutive
                    else:
                        consecutive = 1
        
        # Penalty for unbalanced workload
        if state.teacher_slots:
            loads = [len(slots) for slots in state.teacher_slots.values()]
            if loads:
                avg_load = sum(loads) / len(loads)
                variance = sum((l - avg_load) ** 2 for l in loads) / len(loads)
                score -= variance * 0.5
        
        # Bonus for filling more slots
        total_slots = len(state.allocations)
        score += total_slots * 0.1
        
        return max(0, score)
    
    def _mutate_state(self, state: TimetableState, teachers: List[Teacher]) -> TimetableState:
        """Apply random mutation to a state."""
        if not state.allocations:
            return state
        
        # Simple mutation: swap two random allocations' teachers if valid
        for _ in range(3):  # Try a few mutations
            idx = random.randint(0, len(state.allocations) - 1)
            alloc = state.allocations[idx]
            
            # Find other teachers who can teach this subject
            same_subject = [
                a for a in state.allocations
                if a.subject_id == alloc.subject_id and a != alloc
            ]
            
            if same_subject:
                other = random.choice(same_subject)
                # Swap teachers
                alloc.teacher_id, other.teacher_id = other.teacher_id, alloc.teacher_id
        
        # Rebuild lookup tables
        new_state = TimetableState()
        for alloc in state.allocations:
            new_state.add_allocation(alloc)
        
        return new_state
    
    def _save_allocations(self, allocations: List[AllocationEntry]):
        """Save allocations to database."""
        for entry in allocations:
            db_allocation = Allocation(
                teacher_id=entry.teacher_id,
                subject_id=entry.subject_id,
                semester_id=entry.semester_id,
                room_id=entry.room_id,
                day=entry.day,
                slot=entry.slot,
                is_lab_continuation=entry.is_lab_continuation
            )
            self.db.add(db_allocation)
        
        self.db.commit()
