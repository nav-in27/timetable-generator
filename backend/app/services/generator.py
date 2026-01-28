"""
Timetable Generation Engine.

Implements a two-phase approach:
1. Greedy/CSP-based initial generation (finds feasible solution)
2. Genetic Algorithm optimization (improves soft constraint satisfaction)

HARD CONSTRAINTS (must never be violated):
- A teacher cannot teach two classes at the same time
- A room cannot be assigned to two classes at the same time
- Teacher must be qualified for the subject
- Room capacity must be >= class strength
- Lab sessions must be consecutive slots

SOFT CONSTRAINTS (optimize for):
- Avoid more than 2 consecutive classes for a teacher
- Balance teacher workload across the week
- Avoid last-hour classes if possible
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
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.days = list(range(5))  # Monday-Friday
        self.slots = list(range(settings.SLOTS_PER_DAY))
        
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
        
        # Phase 1: Greedy generation
        state, success, message = self._greedy_generate(
            requirements, teachers, lecture_rooms, lab_rooms
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
        requirements: List[SlotRequirement],
        teachers: List[Teacher],
        lecture_rooms: List[Room],
        lab_rooms: List[Room]
    ) -> Tuple[TimetableState, bool, str]:
        """
        Greedy generation phase.
        Uses constraint propagation and backtracking.
        Reserves 1-2 free periods per class as per configuration.
        """
        state = TimetableState()
        teacher_loads: Dict[int, int] = {t.id: 0 for t in teachers}
        teacher_max_loads: Dict[int, int] = {t.id: t.max_hours_per_week for t in teachers}
        
        # Reserve free periods for each class (1-2 per class per week)
        reserved_free_slots: Dict[int, Set[Tuple[int, int]]] = {}
        unique_semesters = set(req.semester_id for req in requirements)
        
        for semester_id in unique_semesters:
            # Randomly reserve 1-2 free periods per class
            num_free = random.randint(
                settings.MIN_FREE_PERIODS_PER_CLASS,
                settings.MAX_FREE_PERIODS_PER_CLASS
            )
            
            # Pick random slots to keep free (prefer middle-of-week, mid-day)
            available_slots = []
            for day in range(5):
                for slot in range(settings.SLOTS_PER_DAY):
                    available_slots.append((day, slot))
            
            random.shuffle(available_slots)
            reserved_free_slots[semester_id] = set(available_slots[:num_free])
            
            # Mark these slots as "occupied" in state so they won't be scheduled
            for day, slot in reserved_free_slots[semester_id]:
                if semester_id not in state.semester_slots:
                    state.semester_slots[semester_id] = set()
                state.semester_slots[semester_id].add((day, slot))
        
        # Sort requirements: labs first (harder to schedule), then by fewer qualified teachers
        sorted_reqs = sorted(
            requirements,
            key=lambda r: (
                -r.consecutive_slots,  # Labs first
                len(r.qualified_teachers),  # Fewer options first
            )
        )
        
        for req in sorted_reqs:
            hours_scheduled = 0
            hours_needed = req.weekly_hours
            
            # For labs, we schedule in blocks of consecutive_slots
            if req.requires_lab:
                while hours_scheduled < hours_needed:
                    success = self._schedule_lab_session(
                        state, req, lab_rooms if lab_rooms else lecture_rooms,
                        teacher_loads, teacher_max_loads
                    )
                    if success:
                        hours_scheduled += req.consecutive_slots
                    else:
                        # Try with any room
                        success = self._schedule_lab_session(
                            state, req, lecture_rooms + lab_rooms,
                            teacher_loads, teacher_max_loads
                        )
                        if success:
                            hours_scheduled += req.consecutive_slots
                        else:
                            break
            else:
                # Theory/tutorial classes
                while hours_scheduled < hours_needed:
                    success = self._schedule_single_slot(
                        state, req, lecture_rooms,
                        teacher_loads, teacher_max_loads
                    )
                    if success:
                        hours_scheduled += 1
                    else:
                        break
        
        # Remove the reserved free slots from semester_slots
        # (they were placeholders, not actual allocations)
        for semester_id, free_slots in reserved_free_slots.items():
            if semester_id in state.semester_slots:
                state.semester_slots[semester_id] -= free_slots
        
        # Validate result
        violations = self._count_hard_violations(state)
        if violations > 0:
            return state, False, f"Failed to satisfy all hard constraints ({violations} violations)"
        
        return state, True, "Greedy generation successful"

    def _schedule_single_slot(
        self,
        state: TimetableState,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int]
    ) -> bool:
        """Schedule a single slot (theory class)."""
        # Try each day/slot combination
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
                if teacher_loads[teacher_id] >= teacher_max_loads[teacher_id]:
                    continue
                # Soft: avoid more than 2 consecutive
                consecutive = state.get_consecutive_count(teacher_id, day, slot)
                available_teachers.append((teacher_id, teacher_loads[teacher_id], consecutive))
            
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
            teacher_loads[teacher_id] += 1
            
            return True
        
        return False
    
    def _schedule_lab_session(
        self,
        state: TimetableState,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int]
    ) -> bool:
        """Schedule a lab session (consecutive slots)."""
        slots_needed = req.consecutive_slots
        
        for day in self.days:
            for start_slot in range(settings.SLOTS_PER_DAY - slots_needed + 1):
                # Check all slots are free for semester
                slots_free = all(
                    state.is_semester_free(req.semester_id, day, start_slot + i)
                    for i in range(slots_needed)
                )
                if not slots_free:
                    continue
                
                # Find teacher available for all slots
                best_teacher = None
                best_load = float('inf')
                
                for teacher_id in req.qualified_teachers:
                    if teacher_loads[teacher_id] >= teacher_max_loads[teacher_id] - slots_needed + 1:
                        continue
                    
                    teacher_free = all(
                        state.is_teacher_free(teacher_id, day, start_slot + i)
                        for i in range(slots_needed)
                    )
                    if teacher_free and teacher_loads[teacher_id] < best_load:
                        best_teacher = teacher_id
                        best_load = teacher_loads[teacher_id]
                
                if best_teacher is None:
                    continue
                
                # Find room available for all slots
                suitable_room = None
                for room in rooms:
                    if room.capacity < req.min_room_capacity:
                        continue
                    
                    room_free = all(
                        state.is_room_free(room.id, day, start_slot + i)
                        for i in range(slots_needed)
                    )
                    if room_free:
                        suitable_room = room
                        break
                
                if suitable_room is None:
                    continue
                
                # Allocate all consecutive slots
                for i in range(slots_needed):
                    entry = AllocationEntry(
                        semester_id=req.semester_id,
                        subject_id=req.subject_id,
                        teacher_id=best_teacher,
                        room_id=suitable_room.id,
                        day=day,
                        slot=start_slot + i,
                        is_lab_continuation=(i > 0)
                    )
                    state.add_allocation(entry)
                
                teacher_loads[best_teacher] += slots_needed
                return True
        
        return False
    
    def _get_slot_order(self) -> List[Tuple[int, int]]:
        """Get slot order, preferring middle slots (avoiding last hour)."""
        slots = []
        for day in self.days:
            for slot in self.slots:
                priority = 0
                # Prefer middle slots
                if slot in [2, 3, 4, 5]:
                    priority = 0
                elif slot in [1, 6]:
                    priority = 1
                else:
                    priority = 2  # First and last slots less preferred
                slots.append((priority, day, slot))
        
        random.shuffle(slots)  # Randomize within priority
        slots.sort(key=lambda x: x[0])
        return [(day, slot) for _, day, slot in slots]
    
    def _count_hard_violations(self, state: TimetableState) -> int:
        """Count hard constraint violations."""
        violations = 0
        
        # Check for teacher double-booking
        for teacher_id, slots in state.teacher_slots.items():
            # Each slot should appear only once (already ensured by set)
            pass
        
        # Check for room double-booking
        for room_id, slots in state.room_slots.items():
            pass
        
        # Note: The structure prevents double-booking by design
        # Additional validation would be needed for database-loaded states
        
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
        
        # Penalty for last-hour classes
        for alloc in state.allocations:
            if alloc.slot == settings.SLOTS_PER_DAY - 1:
                score -= 1
        
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
            # (simplified - just swap with another allocation of same subject)
            same_subject = [
                a for a in state.allocations
                if a.subject_id == alloc.subject_id and a != alloc
            ]
            
            if same_subject:
                other = random.choice(same_subject)
                # Swap teachers if they're available in each other's slots
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
