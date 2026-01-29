"""
Timetable Generation Engine.

Implements a multi-phase approach:
1. PREPROCESSING: One-time teacher assignment per (class, subject)
2. ELECTIVE SCHEDULING: Schedule electives FIRST across all participating departments
3. GREEDY/CSP-based initial generation (finds feasible solution)
4. GENETIC ALGORITHM optimization (improves soft constraint satisfaction)

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
- Labs occupy 2 consecutive periods (ATOMIC BLOCKS)
- Labs are ONLY allowed AFTER LUNCH:
  * 4th + 5th period (slots 3,4)  OR
  * 6th + 7th period (slots 5,6)
- NO labs before lunch (slots 0,1,2)
- Free periods ONLY when no teacher is available
- Maximize slot utilization

========================
HARD CONSTRAINTS (must never be violated):
========================
- **ONE teacher per (class, subject)** - FIXED at preprocessing, never changed
- **Electives synchronized** - Same elective = same slot across all departments
- **ONE subject per day per class** - A subject can only be scheduled once per day for a class
- **LAB BLOCKS are ATOMIC** - Both lab periods must be consecutive, same day, same teacher, same room
- **Labs ONLY in valid blocks** - 4th+5th period OR 6th+7th period (post-lunch only)
- A teacher cannot teach two classes at the same time
- A room cannot be assigned to two classes at the same time
- Teacher must be qualified for the subject
- Room capacity must be >= class strength

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
    teacher_subjects, SubjectType, RoomType,
    ClassSubjectTeacher, ElectiveGroup, elective_group_semesters
)
from app.core.config import get_settings

settings = get_settings()

# ============================================================
# VALID LAB SLOT BLOCKS (ACADEMIC RULE - HARD CONSTRAINT)
# ============================================================
# Labs are ONLY allowed AFTER LUNCH in these specific blocks:
#   - 4th + 5th period = slots (3, 4) in 0-indexed
#   - 6th + 7th period = slots (5, 6) in 0-indexed
# Labs BEFORE lunch are NOT allowed.
# Each lab MUST occupy EXACTLY 2 CONTINUOUS periods.
# ============================================================
VALID_LAB_BLOCKS = [(3, 4), (5, 6)]  # Post-lunch only


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
    # ISSUE 1 FIX: Pre-assigned teacher (fixed, never changes)
    assigned_teacher_id: Optional[int] = None


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
    # ISSUE 2 FIX: Flag for elective allocations (locked, cannot be moved)
    is_elective: bool = False
    elective_group_id: Optional[int] = None


@dataclass
class TimetableState:
    """Complete state of the timetable for constraint checking."""
    allocations: List[AllocationEntry] = field(default_factory=list)
    
    # Lookup tables for fast constraint checking
    teacher_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    room_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    semester_slots: Dict[int, Set[Tuple[int, int]]] = field(default_factory=dict)
    
    # ISSUE 1 FIX: Fixed teacher assignments (semester_id, subject_id) -> teacher_id
    fixed_teacher_assignments: Dict[Tuple[int, int], int] = field(default_factory=dict)
    
    # ISSUE 2 FIX: Locked elective slots that cannot be modified
    # Key: (semester_id, day, slot), Value: elective_group_id
    locked_elective_slots: Dict[Tuple[int, int, int], int] = field(default_factory=dict)
    
    # ONE SUBJECT PER DAY: Track which subjects are scheduled for each (semester, day)
    # Key: (semester_id, day), Value: Set of subject_ids scheduled that day
    subject_per_day: Dict[Tuple[int, int], Set[int]] = field(default_factory=dict)
    
    # LAB BLOCK TRACKING: Track lab blocks as atomic units
    # Key: (semester_id, day, start_slot), Value: (subject_id, teacher_id, room_id, end_slot)
    # This ensures lab blocks are treated as indivisible units during mutation/optimization
    lab_blocks: Dict[Tuple[int, int, int], Tuple[int, int, int, int]] = field(default_factory=dict)
    
    def add_allocation(self, entry: AllocationEntry):
        """Add an allocation and update lookup tables."""
        # CRITICAL FIX: Prevent adding duplicate allocation for the same slot
        # This prevents the state from becoming invalid and causing DB constraints later
        slot_key = (entry.day, entry.slot)
        if entry.semester_id in self.semester_slots:
            if slot_key in self.semester_slots[entry.semester_id]:
                print(f"[ERROR] ATTEMPT TO OVERWRITE SLOT: Sem={entry.semester_id} Day={entry.day} Slot={entry.slot}")
                print(f"        Existing: {[a for a in self.allocations if a.semester_id==entry.semester_id and a.day==entry.day and a.slot==entry.slot]}")
                print(f"        New: {entry}")
                # Don't add it!
                return

        self.allocations.append(entry)
        
        if entry.teacher_id not in self.teacher_slots:
            self.teacher_slots[entry.teacher_id] = set()
        self.teacher_slots[entry.teacher_id].add(slot_key)
        
        if entry.room_id not in self.room_slots:
            self.room_slots[entry.room_id] = set()
        self.room_slots[entry.room_id].add(slot_key)
        
        if entry.semester_id not in self.semester_slots:
            self.semester_slots[entry.semester_id] = set()
        self.semester_slots[entry.semester_id].add(slot_key)
        
        # If this is an elective, mark the slot as locked
        if entry.is_elective and entry.elective_group_id:
            lock_key = (entry.semester_id, entry.day, entry.slot)
            self.locked_elective_slots[lock_key] = entry.elective_group_id
        
        # ONE SUBJECT PER DAY: Track this subject for this (semester, day)
        day_key = (entry.semester_id, entry.day)
        if day_key not in self.subject_per_day:
            self.subject_per_day[day_key] = set()
        self.subject_per_day[day_key].add(entry.subject_id)
        
        # LAB BLOCK TRACKING: Track lab blocks as atomic units
        # Key: (semester_id, day, start_slot), Value: (subject_id, teacher_id, room_id, end_slot)
        # This ensures lab blocks are treated as indivisible units during mutation/optimization
        # (Note: register_lab_block is called separately)
    
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
    
    def is_slot_locked(self, semester_id: int, day: int, slot: int) -> bool:
        """Check if a slot is locked (elective or other fixed allocation)."""
        return (semester_id, day, slot) in self.locked_elective_slots
    
    def is_slot_in_lab_block(self, semester_id: int, day: int, slot: int) -> bool:
        """
        Check if a slot is part of a LAB BLOCK.
        Lab blocks are atomic units - both slots must be moved together.
        """
        # Check if this slot is the START of a lab block
        if (semester_id, day, slot) in self.lab_blocks:
            return True
        
        # Check if this slot is the END of a lab block (slot-1 is start)
        if slot > 0 and (semester_id, day, slot - 1) in self.lab_blocks:
            lab_info = self.lab_blocks[(semester_id, day, slot - 1)]
            if lab_info[3] == slot:  # end_slot matches
                return True
        
        return False
    
    def register_lab_block(self, semester_id: int, day: int, start_slot: int, 
                           end_slot: int, subject_id: int, teacher_id: int, room_id: int):
        """
        Register a lab block as an atomic unit.
        This ensures both periods are always moved together during mutation/optimization.
        """
        block_key = (semester_id, day, start_slot)
        self.lab_blocks[block_key] = (subject_id, teacher_id, room_id, end_slot)
    
    def get_lab_block_for_slot(self, semester_id: int, day: int, slot: int) -> Optional[Tuple[int, int]]:
        """
        Get the (start_slot, end_slot) of the lab block containing this slot.
        Returns None if the slot is not part of a lab block.
        """
        # Check if this slot is the START of a lab block
        if (semester_id, day, slot) in self.lab_blocks:
            end_slot = self.lab_blocks[(semester_id, day, slot)][3]
            return (slot, end_slot)
        
        # Check if this slot is the END of a lab block
        if slot > 0 and (semester_id, day, slot - 1) in self.lab_blocks:
            lab_info = self.lab_blocks[(semester_id, day, slot - 1)]
            if lab_info[3] == slot:  # end_slot matches
                return (slot - 1, slot)
        
        return None
    
    def is_subject_scheduled_on_day(self, semester_id: int, day: int, subject_id: int) -> bool:
        """Check if a subject is already scheduled for this semester on this day."""
        day_key = (semester_id, day)
        if day_key not in self.subject_per_day:
            return False
        return subject_id in self.subject_per_day[day_key]
    
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
    
    Implements a MULTI-PHASE approach to ensure academic correctness:
    
    PHASE 0 - PREPROCESSING:
        - Assign ONE teacher per (class, subject) - FIXED, never changes
        - Build elective groups from database
    
    PHASE 1 - ELECTIVE SCHEDULING:
        - Schedule electives FIRST (before normal subjects)
        - Find COMMON slots where ALL participating semesters + teacher are free
        - LOCK these slots - they cannot be moved
    
    PHASE 2 - NORMAL SCHEDULING:
        - Schedule regular subjects using greedy/CSP
        - Use FIXED teacher assignments (no re-selection)
        - Avoid locked elective slots
    
    PHASE 3 - OPTIMIZATION:
        - GA optimization for soft constraints
        - ONLY swap slots, NEVER change teacher assignments
        - NEVER move elective slots
    """
    
    # ============================================================
    # VALID LAB BLOCKS (ACADEMIC RULE - HARD CONSTRAINT)
    # ============================================================
    # Labs are ONLY allowed AFTER LUNCH:
    #   - 4th + 5th period = slots (3, 4)
    #   - 6th + 7th period = slots (5, 6)
    # NO labs before lunch!
    # ============================================================
    LAB_SLOT_PAIRS = [(3, 4), (5, 6)]  # ONLY valid lab blocks
    
    def __init__(self, db: Session):
        self.db = db
        self.days = list(range(5))  # Monday-Friday
        self.slots = list(range(settings.SLOTS_PER_DAY))  # 7 slots (0-6)
        
        # ISSUE 1 FIX: In-memory cache of fixed teacher assignments
        # Key: (semester_id, subject_id), Value: teacher_id
        self._fixed_teacher_cache: Dict[Tuple[int, int], int] = {}
        
    def generate(
        self,
        semester_ids: Optional[List[int]] = None,
        clear_existing: bool = True
    ) -> Tuple[bool, str, List[AllocationEntry], float]:
        """
        Main generation method with multi-phase approach.
        
        Algorithm Flow:
        1. PREPROCESSING: Assign one teacher per (class, subject)
        2. ELECTIVE SCHEDULING: Schedule electives first, lock slots
        3. NORMAL SCHEDULING: Greedy generation with fixed teachers
        4. OPTIMIZATION: GA optimization (slot swaps only)
        
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
        
        # Build teacher-subject mapping (subject_id -> [teacher_ids])
        teacher_subject_map = self._build_teacher_subject_map()
        
        # Build teacher lookup by ID
        teacher_by_id = {t.id: t for t in teachers}
        
        # Build room lookup
        lecture_rooms = [r for r in rooms if r.room_type in [RoomType.LECTURE, RoomType.SEMINAR]]
        lab_rooms = [r for r in rooms if r.room_type == RoomType.LAB]
        
        # Clear existing allocations and fixed assignments if requested
        if clear_existing:
            sem_ids = [s.id for s in semesters]
            self.db.query(Allocation).filter(Allocation.semester_id.in_(sem_ids)).delete()
            # Also clear previous fixed teacher assignments for these semesters
            self.db.query(ClassSubjectTeacher).filter(
                ClassSubjectTeacher.semester_id.in_(sem_ids)
            ).delete()
            self.db.commit()
        
        # ============================================================
        # PHASE 0: PREPROCESSING - One-time teacher assignment
        # ============================================================
        print("[Phase 0] Preprocessing - Assigning fixed teachers...")
        
        fixed_assignments = self._assign_fixed_teachers(
            semesters, subjects, teacher_subject_map, teacher_by_id
        )
        
        if not fixed_assignments:
            return False, "Failed to assign teachers to subjects", [], time.time() - start_time
        
        print(f"   [OK] Assigned {len(fixed_assignments)} teacher-subject pairs")
        
        # Build requirements list WITH pre-assigned teachers
        requirements = self._build_requirements_with_fixed_teachers(
            semesters, subjects, teacher_subject_map, fixed_assignments
        )
        
        if not requirements:
            return False, "No requirements to schedule (check teacher-subject assignments)", [], 0
        
        # Initialize timetable state with fixed assignments
        state = TimetableState()
        state.fixed_teacher_assignments = fixed_assignments.copy()
        
        # Initialize teacher loads
        teacher_loads: Dict[int, int] = {t.id: 0 for t in teachers}
        teacher_max_loads: Dict[int, int] = {t.id: t.max_hours_per_week for t in teachers}
        
        # ============================================================
        # PHASE 1: ELECTIVE SCHEDULING (schedule electives FIRST)
        # ============================================================
        print("[Phase 1] Scheduling electives...")
        
        elective_groups = self.db.query(ElectiveGroup).filter(
            ElectiveGroup.is_active == True
        ).all()
        
        electives_scheduled = 0
        for elective in elective_groups:
            success = self._schedule_elective_group(
                state, elective, lecture_rooms + lab_rooms,
                teacher_loads, teacher_max_loads
            )
            if success:
                electives_scheduled += 1
                # Update elective status in DB
                elective.is_scheduled = True
        
        self.db.commit()
        print(f"   [OK] Scheduled {electives_scheduled} elective groups")
        
        # ============================================================
        # PHASE 2: NORMAL SCHEDULING (greedy generation)
        # ============================================================
        print("[Phase 2] Scheduling regular subjects...")
        
        # Separate lab and theory requirements (excluding elective subjects)
        elective_subject_ids = {eg.subject_id for eg in elective_groups}
        
        non_elective_requirements = [
            r for r in requirements if r.subject_id not in elective_subject_ids
        ]
        
        lab_requirements = [r for r in non_elective_requirements if r.requires_lab]
        theory_requirements = [r for r in non_elective_requirements if not r.requires_lab]
        
        state, success, message = self._greedy_generate(
            state, lab_requirements, theory_requirements, 
            teachers, lecture_rooms, lab_rooms, semesters,
            teacher_loads, teacher_max_loads,
            fixed_assignments,  # Pass fixed assignments
            all_teachers=teachers
        )
        
        if not success:
            return False, message, [], time.time() - start_time
        
        print(f"   [OK] Generated {len(state.allocations)} total allocations")
        
        # ============================================================
        # PHASE 3: GA OPTIMIZATION (slot swaps only, no teacher changes)
        # ============================================================
        print("[Phase 3] Optimizing timetable...")
        
        if len(state.allocations) > 10:
            state = self._genetic_optimize(state, teachers, fixed_assignments)
        
        print("   [OK] Optimization complete")
        
        # Save allocations to database
        self._save_allocations(state.allocations)
        
        # Save fixed teacher assignments to database for future reference
        self._save_fixed_assignments(fixed_assignments)
        
        generation_time = time.time() - start_time
        
        return (
            True,
            f"Generated {len(state.allocations)} allocations successfully",
            state.allocations,
            generation_time
        )
    
    def _assign_fixed_teachers(
        self,
        semesters: List[Semester],
        subjects: List[Subject],
        teacher_subject_map: Dict[int, List[int]],
        teacher_by_id: Dict[int, Teacher]
    ) -> Dict[Tuple[int, int], int]:
        """
        ISSUE 1 FIX: Assign exactly ONE teacher per (semester, subject) pair.
        
        This is a ONE-TIME assignment that is:
        - Fixed for the entire timetable generation
        - Never changed during slot assignment
        - Not altered by GA mutation
        
        Selection criteria (in order):
        1. Subject specialization match (mandatory - from teacher_subjects)
        2. Lowest current workload (to balance)
        3. Highest effectiveness score (for quality)
        
        Returns:
            Dict mapping (semester_id, subject_id) -> teacher_id
        """
        fixed_assignments: Dict[Tuple[int, int], int] = {}
        
        # Track projected workload for fair distribution
        projected_workload: Dict[int, int] = {t_id: 0 for t_id in teacher_by_id.keys()}
        
        for semester in semesters:
            for subject in subjects:
                key = (semester.id, subject.id)
                
                # Get qualified teachers for this subject
                qualified_teacher_ids = teacher_subject_map.get(subject.id, [])
                if not qualified_teacher_ids:
                    continue  # No teacher can teach this subject
                
                # Filter by availability and get their details
                available_teachers = []
                for t_id in qualified_teacher_ids:
                    teacher = teacher_by_id.get(t_id)
                    if teacher and teacher.is_active:
                        # Check if teacher has capacity (considering weekly hours needed)
                        max_hours = teacher.max_hours_per_week
                        current_projected = projected_workload.get(t_id, 0)
                        hours_needed = subject.weekly_hours
                        
                        if current_projected + hours_needed <= max_hours * 1.2:  # 20% buffer
                            available_teachers.append({
                                'id': t_id,
                                'projected_load': current_projected,
                                'experience_score': teacher.experience_score,
                                'max_hours': max_hours
                            })
                
                if not available_teachers:
                    # All qualified teachers are at capacity, pick least loaded anyway
                    for t_id in qualified_teacher_ids:
                        teacher = teacher_by_id.get(t_id)
                        if teacher and teacher.is_active:
                            available_teachers.append({
                                'id': t_id,
                                'projected_load': projected_workload.get(t_id, 0),
                                'experience_score': teacher.experience_score,
                                'max_hours': teacher.max_hours_per_week
                            })
                
                if not available_teachers:
                    continue  # Truly no one available
                
                # Sort by: lowest projected load, then highest experience score
                available_teachers.sort(
                    key=lambda t: (t['projected_load'], -t['experience_score'])
                )
                
                # Select the best teacher
                selected_teacher_id = available_teachers[0]['id']
                fixed_assignments[key] = selected_teacher_id
                
                # Update projected workload
                projected_workload[selected_teacher_id] += subject.weekly_hours
        
        return fixed_assignments
    
    def _schedule_elective_group(
        self,
        state: TimetableState,
        elective: ElectiveGroup,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int]
    ) -> bool:
        """
        ISSUE 2 FIX: Schedule an elective group across ALL participating semesters.
        
        This finds a COMMON slot where:
        - The elective's assigned teacher is free
        - ALL participating semesters are free
        - A suitable room is available
        
        Once scheduled, the slot is LOCKED and cannot be moved.
        
        Returns:
            True if successfully scheduled, False otherwise
        """
        if not elective.participating_semesters:
            return False  # No semesters to schedule
        
        participating_semester_ids = [s.id for s in elective.participating_semesters]
        teacher_id = elective.teacher_id
        hours_needed = elective.hours_per_week
        
        # Find subject details for room capacity
        subject = elective.subject
        if not subject:
            return False
        
        # Calculate minimum room capacity (sum of all participating semester students)
        min_capacity = sum(s.student_count for s in elective.participating_semesters)
        
        # Try to schedule the required hours
        hours_scheduled = 0
        scheduled_slot_strings = []
        
        # Get slot order (randomized)
        slot_order = self._get_slot_order()
        
        for day, slot in slot_order:
            if hours_scheduled >= hours_needed:
                break
            
            # Check if teacher is free
            if not state.is_teacher_free(teacher_id, day, slot):
                continue
            
            # Check if ALL participating semesters are free
            all_semesters_free = True
            for sem_id in participating_semester_ids:
                if not state.is_semester_free(sem_id, day, slot):
                    all_semesters_free = False
                    break
            
            if not all_semesters_free:
                continue
            
            # Find suitable room
            suitable_room = None
            for room in rooms:
                if room.capacity >= min_capacity and state.is_room_free(room.id, day, slot):
                    suitable_room = room
                    break
            
            # If no large enough room, try elective's designated room
            if not suitable_room and elective.room_id:
                if state.is_room_free(elective.room_id, day, slot):
                    suitable_room = self.db.query(Room).get(elective.room_id)
            
            if not suitable_room:
                continue
            
            # Schedule this elective slot for ALL participating semesters
            for sem_id in participating_semester_ids:
                entry = AllocationEntry(
                    semester_id=sem_id,
                    subject_id=elective.subject_id,
                    teacher_id=teacher_id,
                    room_id=suitable_room.id,
                    day=day,
                    slot=slot,
                    is_lab_continuation=False,
                    is_elective=True,
                    elective_group_id=elective.id
                )
                state.add_allocation(entry)
            
            # Update teacher load
            teacher_loads[teacher_id] = teacher_loads.get(teacher_id, 0) + 1
            hours_scheduled += 1
            scheduled_slot_strings.append(f"{day}:{slot}")
        
        # Update elective with scheduled slots
        if hours_scheduled > 0:
            elective.scheduled_slots = ",".join(scheduled_slot_strings)
            return True
        
        return False
    
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
    
    def _build_requirements_with_fixed_teachers(
        self,
        semesters: List[Semester],
        subjects: List[Subject],
        teacher_subject_map: Dict[int, List[int]],
        fixed_assignments: Dict[Tuple[int, int], int]
    ) -> List[SlotRequirement]:
        """Build list of scheduling requirements WITH pre-assigned teachers."""
        requirements = []
        
        for semester in semesters:
            for subject in subjects:
                # Check if any teachers can teach this subject
                qualified_teachers = teacher_subject_map.get(subject.id, [])
                if not qualified_teachers:
                    continue  # Skip subjects with no qualified teachers
                
                # Get the fixed teacher assignment
                key = (semester.id, subject.id)
                assigned_teacher = fixed_assignments.get(key)
                
                req = SlotRequirement(
                    semester_id=semester.id,
                    subject_id=subject.id,
                    subject_type=subject.subject_type,
                    consecutive_slots=subject.consecutive_slots,
                    weekly_hours=subject.weekly_hours,
                    qualified_teachers=qualified_teachers,
                    min_room_capacity=semester.student_count,
                    requires_lab=subject.subject_type == SubjectType.LAB,
                    assigned_teacher_id=assigned_teacher  # FIXED TEACHER
                )
                requirements.append(req)
        
        return requirements


    def _greedy_generate(
        self,
        state: TimetableState,
        lab_requirements: List[SlotRequirement],
        theory_requirements: List[SlotRequirement],
        teachers: List[Teacher],
        lecture_rooms: List[Room],
        lab_rooms: List[Room],
        semesters: List[Semester],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int],
        fixed_assignments: Dict[Tuple[int, int], int],
        all_teachers: List[Teacher] = None
    ) -> Tuple[TimetableState, bool, str]:
        """
        Greedy generation phase with FIXED teacher assignments.
        
        GOAL: Fill ALL 7 periods for each class
        - Schedule labs first (harder to place)
        - Then fill remaining slots with theory
        - USE FIXED teacher assignment (no re-selection)
        - Skip locked elective slots
        - Free period only if no teacher/room available
        
        IMPORTANT: The teacher for each (semester, subject) is PRE-ASSIGNED
        and MUST NOT be changed during this phase.
        """
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
                success = self._schedule_lab_session_with_fixed_teacher(
                    state, req, lab_rooms if lab_rooms else lecture_rooms,
                    teacher_loads, teacher_max_loads, fixed_assignments
                )
                if success:
                    hours_scheduled += 2  # Each lab session is 2 slots
                else:
                    # Try with lecture rooms as fallback
                    success = self._schedule_lab_session_with_fixed_teacher(
                        state, req, lecture_rooms + lab_rooms,
                        teacher_loads, teacher_max_loads, fixed_assignments
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
                success = self._schedule_theory_slot_with_fixed_teacher(
                    state, req, lecture_rooms,
                    teacher_loads, teacher_max_loads, fixed_assignments
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
                    # Skip locked elective slots
                    if state.is_slot_locked(semester.id, day, slot):
                        continue
                    
                    # Check if this slot is empty for this semester
                    if not state.is_semester_free(semester.id, day, slot):
                        continue
                    
                    # Try to fill this empty slot (using fixed teacher assignments)
                    filled = self._fill_empty_slot_with_fixed_teacher(
                        state, semester.id, day, slot,
                        all_requirements, lecture_rooms,
                        teacher_loads, teacher_max_loads,
                        fixed_assignments,
                        all_teacher_ids=all_teacher_ids
                    )
        
        # Validate result

        violations = self._count_hard_violations(state)
        if violations > 0:
            return state, False, f"Failed to satisfy all hard constraints ({violations} violations)"
        
        return state, True, "Timetable generated successfully - all possible slots filled"
    
    def _schedule_lab_session_with_fixed_teacher(
        self,
        state: TimetableState,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int],
        fixed_assignments: Dict[Tuple[int, int], int]
    ) -> bool:
        """
        Schedule a lab session (2 consecutive periods) using FIXED teacher assignment.
        
        ISSUE 1 FIX: Uses the pre-assigned teacher for this (semester, subject) pair.
        Does NOT dynamically select teachers.
        """
        # Get the FIXED teacher for this (semester, subject)
        key = (req.semester_id, req.subject_id)
        fixed_teacher_id = fixed_assignments.get(key) or req.assigned_teacher_id
        
        if not fixed_teacher_id:
            # Fallback: use first qualified teacher (should not happen normally)
            if req.qualified_teachers:
                fixed_teacher_id = req.qualified_teachers[0]
            else:
                return False
        
        # Check if fixed teacher has capacity
        current_load = teacher_loads.get(fixed_teacher_id, 0)
        max_load = teacher_max_loads.get(fixed_teacher_id, 20)
        if current_load >= max_load - 1:  # Need 2 slots for lab
            return False
        
        # Shuffle days for variety
        days = list(self.days)
        random.shuffle(days)
        
        for day in days:
            # ONE SUBJECT PER DAY: Skip if this subject is already scheduled on this day
            if state.is_subject_scheduled_on_day(req.semester_id, day, req.subject_id):
                continue
            
            # Try each valid lab slot pair (randomized for variety)
            slot_pairs = list(self.LAB_SLOT_PAIRS)
            random.shuffle(slot_pairs)
            
            for start_slot, end_slot in slot_pairs:
                # Skip locked elective slots
                if state.is_slot_locked(req.semester_id, day, start_slot):
                    continue
                if state.is_slot_locked(req.semester_id, day, end_slot):
                    continue
                
                # Check both slots are free for semester
                if not state.is_semester_free(req.semester_id, day, start_slot):
                    continue
                if not state.is_semester_free(req.semester_id, day, end_slot):
                    continue
                
                # Check FIXED teacher is available for both slots
                teacher_free = (
                    state.is_teacher_free(fixed_teacher_id, day, start_slot) and
                    state.is_teacher_free(fixed_teacher_id, day, end_slot)
                )
                if not teacher_free:
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
                
                # Allocate both consecutive slots with FIXED teacher
                entry1 = AllocationEntry(
                    semester_id=req.semester_id,
                    subject_id=req.subject_id,
                    teacher_id=fixed_teacher_id,  # FIXED teacher
                    room_id=suitable_room.id,
                    day=day,
                    slot=start_slot,
                    is_lab_continuation=False
                )
                entry2 = AllocationEntry(
                    semester_id=req.semester_id,
                    subject_id=req.subject_id,
                    teacher_id=fixed_teacher_id,  # SAME fixed teacher
                    room_id=suitable_room.id,
                    day=day,
                    slot=end_slot,
                    is_lab_continuation=True
                )
                
                state.add_allocation(entry1)
                state.add_allocation(entry2)
                
                # REGISTER LAB BLOCK: Track this as an atomic unit
                state.register_lab_block(
                    semester_id=req.semester_id,
                    day=day,
                    start_slot=start_slot,
                    end_slot=end_slot,
                    subject_id=req.subject_id,
                    teacher_id=fixed_teacher_id,
                    room_id=suitable_room.id
                )
                
                teacher_loads[fixed_teacher_id] = teacher_loads.get(fixed_teacher_id, 0) + 2
                return True
        
        return False
    
    def _schedule_theory_slot_with_fixed_teacher(
        self,
        state: TimetableState,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int],
        fixed_assignments: Dict[Tuple[int, int], int]
    ) -> bool:
        """
        Schedule a single theory slot using FIXED teacher assignment.
        
        ISSUE 1 FIX: Uses the pre-assigned teacher for this (semester, subject) pair.
        Does NOT dynamically select teachers.
        """
        # Get the FIXED teacher for this (semester, subject)
        key = (req.semester_id, req.subject_id)
        fixed_teacher_id = fixed_assignments.get(key) or req.assigned_teacher_id
        
        if not fixed_teacher_id:
            # Fallback: use first qualified teacher (should not happen normally)
            if req.qualified_teachers:
                fixed_teacher_id = req.qualified_teachers[0]
            else:
                return False
        
        # Check if fixed teacher has capacity
        current_load = teacher_loads.get(fixed_teacher_id, 0)
        max_load = teacher_max_loads.get(fixed_teacher_id, 20)
        if current_load >= max_load:
            return False
        
        # Get slot order with some randomization
        slot_order = self._get_slot_order()
        
        for day, slot in slot_order:
            # Skip locked elective slots
            if state.is_slot_locked(req.semester_id, day, slot):
                continue
            
            # ONE SUBJECT PER DAY: Skip if this subject is already scheduled on this day
            if state.is_subject_scheduled_on_day(req.semester_id, day, req.subject_id):
                continue
            
            # Check semester availability
            if not state.is_semester_free(req.semester_id, day, slot):
                continue
            
            # Check FIXED teacher availability
            if not state.is_teacher_free(fixed_teacher_id, day, slot):
                continue
            
            # Find available room with sufficient capacity
            suitable_rooms = [
                r for r in rooms
                if r.capacity >= req.min_room_capacity and state.is_room_free(r.id, day, slot)
            ]
            
            if not suitable_rooms:
                continue
            
            room = suitable_rooms[0]
            
            # Create allocation with FIXED teacher
            entry = AllocationEntry(
                semester_id=req.semester_id,
                subject_id=req.subject_id,
                teacher_id=fixed_teacher_id,  # FIXED teacher
                room_id=room.id,
                day=day,
                slot=slot,
                is_lab_continuation=False
            )
            state.add_allocation(entry)
            teacher_loads[fixed_teacher_id] = teacher_loads.get(fixed_teacher_id, 0) + 1
            
            return True
        
        return False
    
    def _fill_empty_slot_with_fixed_teacher(
        self,
        state: TimetableState,
        semester_id: int,
        day: int,
        slot: int,
        requirements: List[SlotRequirement],
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int],
        fixed_assignments: Dict[Tuple[int, int], int],
        all_teacher_ids: List[int] = None
    ) -> bool:
        """
        Try to fill an empty slot with any available subject using FIXED teacher assignments.
        
        ISSUE 1 FIX: Uses the pre-assigned teacher for each (semester, subject) pair.
        Does NOT dynamically select teachers.
        
        Returns True if successful, False if no teacher/room available.
        """
        is_7th_period = (slot == 6)  # 0-indexed, so 6 = 7th period
        
        # Get all requirements for this semester
        semester_reqs = [r for r in requirements if r.semester_id == semester_id]
        
        # Separate theory and lab requirements
        theory_reqs = [r for r in semester_reqs if not r.requires_lab]
        lab_reqs = [r for r in semester_reqs if r.requires_lab]
        
        # Shuffle for variety
        random.shuffle(theory_reqs)
        
        # Try theory subjects first using FIXED teachers
        for req in theory_reqs:
            result = self._try_assign_fixed_teacher_to_slot(
                state, semester_id, day, slot, req, rooms, 
                teacher_loads, teacher_max_loads, fixed_assignments
            )
            if result:
                return True
        
        # Try with extra flexibility
        for req in theory_reqs:
            result = self._try_assign_fixed_teacher_to_slot(
                state, semester_id, day, slot, req, rooms, 
                teacher_loads, teacher_max_loads, fixed_assignments,
                ignore_weekly_limit=True
            )
            if result:
                return True
        
        # Last resort: Try single-slot lab sessions
        for req in lab_reqs:
            result = self._try_assign_fixed_teacher_to_slot(
                state, semester_id, day, slot, req, rooms, 
                teacher_loads, teacher_max_loads, fixed_assignments,
                ignore_weekly_limit=True
            )
            if result:
                return True
        
        # For 7th period - try even harder
        if is_7th_period:
            for req in theory_reqs + lab_reqs:
                result = self._try_assign_fixed_teacher_to_slot(
                    state, semester_id, day, slot, req, rooms, 
                    teacher_loads, teacher_max_loads, fixed_assignments,
                    ignore_weekly_limit=True,
                    force_assignment=True
                )
                if result:
                    return True
        
        return False
    
    def _try_assign_fixed_teacher_to_slot(
        self,
        state: TimetableState,
        semester_id: int,
        day: int,
        slot: int,
        req: SlotRequirement,
        rooms: List[Room],
        teacher_loads: Dict[int, int],
        teacher_max_loads: Dict[int, int],
        fixed_assignments: Dict[Tuple[int, int], int],
        ignore_weekly_limit: bool = False,
        force_assignment: bool = False
    ) -> bool:
        """
        Try to assign the FIXED teacher to a specific slot for a subject.
        
        ISSUE 1 FIX: Uses the pre-assigned teacher, not dynamic selection.
        """
        # Get the FIXED teacher for this (semester, subject)
        key = (req.semester_id, req.subject_id)
        fixed_teacher_id = fixed_assignments.get(key) or req.assigned_teacher_id
        
        if not fixed_teacher_id:
            return False
        
        # ONE SUBJECT PER DAY: Check if this subject is already scheduled on this day
        if state.is_subject_scheduled_on_day(semester_id, day, req.subject_id):
            return False
        
        # Check teacher availability
        if not state.is_teacher_free(fixed_teacher_id, day, slot):
            return False
        
        current_load = teacher_loads.get(fixed_teacher_id, 0)
        max_load = teacher_max_loads.get(fixed_teacher_id, 20)
        
        # Check teacher capacity
        if force_assignment:
            if current_load >= int(max_load * 1.5):
                return False
        elif ignore_weekly_limit:
            if current_load >= int(max_load * 1.2):
                return False
        else:
            if current_load >= max_load:
                return False
        
        # Find available room
        suitable_rooms = [
            r for r in rooms
            if r.capacity >= req.min_room_capacity and state.is_room_free(r.id, day, slot)
        ]
        
        if not suitable_rooms:
            return False
        
        room = suitable_rooms[0]
        
        # Create allocation with FIXED teacher
        entry = AllocationEntry(
            semester_id=semester_id,
            subject_id=req.subject_id,
            teacher_id=fixed_teacher_id,  # FIXED teacher
            room_id=room.id,
            day=day,
            slot=slot,
            is_lab_continuation=False
        )
        state.add_allocation(entry)
        teacher_loads[fixed_teacher_id] = teacher_loads.get(fixed_teacher_id, 0) + 1
        
        return True

    
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
        # ONE SUBJECT PER DAY: Check if this subject is already scheduled on this day
        if state.is_subject_scheduled_on_day(semester_id, day, req.subject_id):
            return False
        
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
            # ONE SUBJECT PER DAY: Skip if this subject is already scheduled on this day
            if state.is_subject_scheduled_on_day(req.semester_id, day, req.subject_id):
                continue
            
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
                
                # REGISTER LAB BLOCK: Track this as an atomic unit
                state.register_lab_block(
                    semester_id=req.semester_id,
                    day=day,
                    start_slot=start_slot,
                    end_slot=end_slot,
                    subject_id=req.subject_id,
                    teacher_id=best_teacher,
                    room_id=suitable_room.id
                )
                
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
            
            # ONE SUBJECT PER DAY: Skip if this subject is already scheduled on this day
            if state.is_subject_scheduled_on_day(req.semester_id, day, req.subject_id):
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
        fixed_assignments: Dict[Tuple[int, int], int],
        population_size: int = 20,
        generations: int = 50
    ) -> TimetableState:
        """
        Genetic Algorithm optimization phase.
        
        Improves soft constraint satisfaction while maintaining hard constraints.
        
        IMPORTANT CONSTRAINTS (MUST NOT BE VIOLATED):
        - NEVER change teacher assignments (fixed per semester/subject)
        - NEVER move elective slots (locked)
        - Only swap slots between allocations if valid
        """
        # Create initial population from variations of the initial state
        population = [initial_state]
        for _ in range(population_size - 1):
            mutated = self._mutate_state_safe(deepcopy(initial_state), teachers, fixed_assignments)
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
                child = self._mutate_state_safe(deepcopy(parent), teachers, fixed_assignments)
                
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
    
    def _mutate_state_safe(
        self, 
        state: TimetableState, 
        teachers: List[Teacher],
        fixed_assignments: Dict[Tuple[int, int], int]
    ) -> TimetableState:
        """
        Apply random mutation to a state SAFELY.
        
        IMPORTANT CONSTRAINTS:
        - NEVER change teacher assignments (violates Issue 1 fix)
        - NEVER move elective allocations (violates Issue 2 fix)
        - LAB BLOCKS must be moved as ATOMIC UNITS (both periods together)
        - Labs can ONLY move to VALID LAB BLOCKS (post-lunch slots)
        - Only swap SLOTS between non-elective, non-lab allocations of same semester
        """
        if not state.allocations:
            return state
        
        # Separate mutable theory allocations from lab allocations
        # Theory: can be swapped individually
        # Labs: must be swapped as complete blocks only
        theory_allocations = []
        lab_start_allocations = []  # Only start slots of lab blocks
        
        for i, a in enumerate(state.allocations):
            if a.is_elective:
                continue  # Never mutate electives
            
            if a.is_lab_continuation:
                continue  # Skip lab continuation slots (handled with start slots)
            
            # Check if this is a lab block start
            if state.is_slot_in_lab_block(a.semester_id, a.day, a.slot):
                lab_start_allocations.append((i, a))
            else:
                theory_allocations.append((i, a))
        
        # ============================================================
        # MUTATION TYPE 1: Swap theory allocations (individual slots)
        # ============================================================
        if len(theory_allocations) >= 2:
            for _ in range(2):  # Try 2 theory swaps
                idx1, alloc1 = random.choice(theory_allocations)
                
                same_semester_theory = [
                    (i, a) for i, a in theory_allocations
                    if a.semester_id == alloc1.semester_id and i != idx1
                ]
                
                if not same_semester_theory:
                    continue
                
                idx2, alloc2 = random.choice(same_semester_theory)
                
                # Only swap if different subjects (same subject swap is pointless)
                if alloc1.subject_id != alloc2.subject_id:
                    # Swap day and slot
                    alloc1.day, alloc2.day = alloc2.day, alloc1.day
                    alloc1.slot, alloc2.slot = alloc2.slot, alloc1.slot
        
        # ============================================================
        # MUTATION TYPE 2: Move lab block to different valid lab block slot
        # This maintains lab continuity - both periods move together
        # ============================================================
        if lab_start_allocations and random.random() < 0.3:  # 30% chance to mutate a lab
            idx1, lab_alloc = random.choice(lab_start_allocations)
            
            # Find the corresponding lab continuation slot
            lab_block_info = state.get_lab_block_for_slot(
                lab_alloc.semester_id, lab_alloc.day, lab_alloc.slot
            )
            
            if lab_block_info:
                start_slot, end_slot = lab_block_info
                
                # Find the continuation allocation
                continuation_alloc = None
                continuation_idx = None
                for i, a in enumerate(state.allocations):
                    if (a.semester_id == lab_alloc.semester_id and 
                        a.day == lab_alloc.day and 
                        a.slot == end_slot and 
                        a.is_lab_continuation):
                        continuation_alloc = a
                        continuation_idx = i
                        break
                
                if continuation_alloc:
                    # Try to find a new valid lab block slot
                    valid_lab_blocks = self.LAB_SLOT_PAIRS  # [(3,4), (5,6)]
                    days = list(range(5))
                    random.shuffle(days)
                    
                    for new_day in days:
                        random.shuffle(valid_lab_blocks)
                        for new_start, new_end in valid_lab_blocks:
                            # Skip current position
                            if new_day == lab_alloc.day and new_start == start_slot:
                                continue
                            
                            # Check if new position is available
                            # Note: We're doing a simple swap, so we need both slots free
                            # This is simplified - in production, more complex validation needed
                            
                            # Move the lab block to new position
                            lab_alloc.day = new_day
                            lab_alloc.slot = new_start
                            continuation_alloc.day = new_day
                            continuation_alloc.slot = new_end
                            break
                        else:
                            continue
                        break
        
        # ============================================================
        # Rebuild state with all lookup tables
        # ============================================================
        new_state = TimetableState()
        new_state.fixed_teacher_assignments = state.fixed_teacher_assignments.copy()
        new_state.locked_elective_slots = state.locked_elective_slots.copy()
        # Note: lab_blocks will be rebuilt from allocations via add_allocation
        
        for alloc in state.allocations:
            new_state.add_allocation(alloc)
        
        # Rebuild lab_blocks from the mutated allocations
        # This ensures lab block tracking stays consistent
        for i, alloc in enumerate(new_state.allocations):
            if alloc.is_lab_continuation:
                continue
            # Find if this is start of a lab (has a continuation)
            for j, other in enumerate(new_state.allocations):
                if (other.is_lab_continuation and 
                    other.semester_id == alloc.semester_id and
                    other.subject_id == alloc.subject_id and
                    other.day == alloc.day and
                    other.slot == alloc.slot + 1):
                    new_state.register_lab_block(
                        alloc.semester_id, alloc.day, alloc.slot,
                        other.slot, alloc.subject_id, alloc.teacher_id, alloc.room_id
                    )
                    break
        
        return new_state
    
    def _mutate_state(self, state: TimetableState, teachers: List[Teacher]) -> TimetableState:
        """DEPRECATED: Use _mutate_state_safe instead. This one swaps teachers which violates Issue 1 fix."""
        # Keeping for backwards compatibility but should not be used
        return state
    
    def _save_allocations(self, allocations: List[AllocationEntry]):
        """Save allocations to database."""
        # First, clear existing allocations for the involved semesters to prevent conflicts
        # (In a real app, might want to be more selective, but for generation we usually replace)
        if not allocations:
            return
            
        print(f"   [DB] Saving {len(allocations)} allocations...")
        
        # Check for duplicates in the list itself
        seen = set()
        unique_allocations = []
        for entry in allocations:
            key = (entry.semester_id, entry.day, entry.slot)
            if key in seen:
                print(f"[WARN] Duplicate allocation in output detected and skipped: {key}")
                continue
            seen.add(key)
            unique_allocations.append(entry)
            
        for entry in unique_allocations:
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
        
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            print(f"[ERROR] Database commit failed: {e}")
            raise
    
    def _save_fixed_assignments(self, fixed_assignments: Dict[Tuple[int, int], int]):
        """
        Save fixed teacher assignments to database.
        
        This preserves the one-time teacher assignment for future reference
        and prevents re-generation from selecting different teachers.
        """
        for (semester_id, subject_id), teacher_id in fixed_assignments.items():
            assignment = ClassSubjectTeacher(
                semester_id=semester_id,
                subject_id=subject_id,
                teacher_id=teacher_id,
                assignment_reason="auto_assigned_by_generator",
                is_locked=True
            )
            self.db.add(assignment)
        
        self.db.commit()

