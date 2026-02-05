# Elective Basket Scheduling - Data Model & Architecture

## Current System Analysis

### Existing Data Model (Already Implemented ✅)

#### 1. ElectiveBasket Table
```python
class ElectiveBasket(Base):
    id: Mapped[int]
    name: str                          # e.g., "Open Elective 1"
    code: str                          # e.g., "OE1-S5"
    semester_number: int               # e.g., 5 for all 5th sem classes
    
    # Common hours for ALL subjects in basket
    theory_hours_per_week: int         # e.g., 3
    lab_hours_per_week: int            # e.g., 0 or 2 (lab blocks)
    tutorial_hours_per_week: int       # e.g., 0
    
    # Scheduling state
    is_scheduled: bool                 # Flag after scheduling
    scheduled_slots: Optional[str]     # JSON: "theory:0:2,lab:1:3:4"
    
    # Relationships
    subjects: List[Subject]            # Alternative subjects in basket
    participating_semesters: List[Semester]  # Classes that use this basket
```

**Why This Works**:
- ✅ Single basket → Multiple subjects (alternatives for students)
- ✅ Single basket → Multiple participating classes (semesters)
- ✅ All classes get SAME common slots
- ✅ Tracks what's been scheduled for auditing

#### 2. Subject-Basket Link
```python
class Subject(Base):
    elective_basket_id: Optional[int]   # NULL if not elective, or basket ID
    is_elective: bool                   # Quick flag for queries
```

**Why This Works**:
- ✅ Quick lookup: all subjects in basket
- ✅ Quick lookup: is this subject elective?
- ✅ Clean relationship without join table needed

#### 3. Allocation Table (Already Has Elective Fields)
```python
class Allocation(Base):
    # ... normal fields ...
    is_elective: bool                   # Mark this allocation as elective
    elective_basket_id: Optional[int]   # Which basket this came from
```

**Why This Works**:
- ✅ Track which basket each elective allocation belongs to
- ✅ Quick filter: find all allocations for a basket
- ✅ Enables audit trail

#### 4. ClassSubjectTeacher (Teacher Assignment)
```python
class ClassSubjectTeacher(Base):
    semester_id: int                    # Which class
    subject_id: int                     # Which subject
    teacher_id: int                     # Assigned teacher
    component_type: ComponentType       # THEORY, LAB, TUTORIAL
    assignment_reason: str              # "auto_assigned_for_elective_basket"
    is_locked: bool                     # Teacher fixed?
```

**Why This Works**:
- ✅ Links teacher → subject → class
- ✅ Different teachers can teach same subject to different classes
- ✅ Supports different teachers for different components (Theory vs Lab)
- ✅ Audit trail via assignment_reason

---

## Current Generation Flow (7-Phase Model)

### Phase 0: Data Validation
```
✓ Checks total hours ≤ available slots
✓ Validates subjects/teachers exist
✓ Computes hour breakdowns
```

### Phase 1: Lock Teacher Assignments
```
✓ Reads ClassSubjectTeacher entries
✓ Builds fixed_assignments: (semester_id, subject_id, component_type) → teacher_id
✓ Validates teacher capacity
```

### Phase 2: ELECTIVE THEORY SCHEDULING ← KEY PHASE
```
For each semester_number group:
  1. Collect all elective theory requirements for that semester number
  2. Find common (day, slot) that ALL participating classes are free
  3. Check ALL assigned teachers are free at that slot
  4. Allocate subject to EACH participating class at same (day, slot)
  5. Mark slot as locked for all participating classes
  6. Track allocated slot in elective_basket.scheduled_slots

Key: Group by semester_number, not by basket, ensures:
  - All classes of same semester get same elective slot
  - Multiple electives of same semester sync together
```

### Phase 3: ELECTIVE LAB SCHEDULING
```
Similar to Phase 2, but:
- Works with lab blocks (2 consecutive periods)
- Uses VALID_LAB_BLOCKS = [(3,4), (5,6)]
- Ensures lab atomicity (both periods allocated together)
```

### Phase 4-7: Regular Scheduling
```
Phase 4: Regular lab blocks (non-elective)
Phase 5: Theory & tutorial fill (greedy)
Phase 6: Final validation (soft - report only)
Phase 7: Save to database
```

---

## How Teacher Availability is Ensured ✅

### Current Mechanism (Already Working)

```python
# In Phase 2: _schedule_elective_theory()

for day, slot in slot_order:
    # 1. Check if ALL participating classes are free
    all_free = all(
        state.is_semester_free(sid, day, slot) 
        for sid in all_sem_ids  # All classes of same semester_number
    )
    if not all_free:
        continue
    
    # 2. Check if ALL assigned teachers are free
    all_teachers_free = all(
        state.is_teacher_free(r.assigned_teacher_id, day, slot) 
        for r in reqs if r.assigned_teacher_id
    )
    if not all_teachers_free:
        continue  # ← Teacher busy, skip this slot
    
    # 3. Only allocate if BOTH conditions pass
    for req, room in slot_allocations:
        entry = AllocationEntry(...)
        state.add_allocation(entry)  # Updates teacher_slots, semester_slots
```

### State Tracking
```python
class TimetableState:
    teacher_slots: Dict[int, Set[Tuple[int, int]]]  # teacher_id → set of (day, slot)
    semester_slots: Dict[int, Set[Tuple[int, int]]] # semester_id → set of (day, slot)
    
    def add_allocation(entry: AllocationEntry):
        # Mark slot as taken
        self.teacher_slots[entry.teacher_id].add((entry.day, entry.slot))
        self.semester_slots[entry.semester_id].add((entry.day, entry.slot))
        
    def is_teacher_free(teacher_id, day, slot) -> bool:
        return (day, slot) not in self.teacher_slots.get(teacher_id, set())
```

**Result**: Teacher cannot be double-booked at same (day, slot) across ANY class.

---

## Proposed Enhancement: ElectiveBasketSchedulingPlan

To make the code even cleaner and more maintainable, I propose a new helper class:

```python
@dataclass
class ElectiveBasketSchedulingPlan:
    """
    Represents a planned allocation of an elective basket.
    Generated during Phase 2, used to guide allocation.
    
    This makes the logic explicit and testable.
    """
    basket_id: int
    basket_name: str
    semester_number: int
    
    # Participating classes
    participating_semester_ids: List[int]  # All classes that use this basket
    
    # Requirements per class (which subject chosen by which class)
    class_subject_map: Dict[int, int]      # semester_id → chosen_subject_id
    
    # Assigned teachers per subject
    subject_teacher_map: Dict[int, int]    # subject_id → teacher_id
    
    # Planned allocation
    component_type: ComponentType           # THEORY or LAB
    allocated_day: Optional[int] = None
    allocated_start_slot: Optional[int] = None
    allocated_end_slot: Optional[int] = None  # For labs: start+1
    
    # Status
    is_allocated: bool = False
    failure_reason: Optional[str] = None

    def can_allocate_at(self, day: int, start_slot: int, state: TimetableState) -> bool:
        """Check if this plan can be allocated at given day/slot."""
        # Check all participating classes are free
        for sem_id in self.participating_semester_ids:
            if not state.is_semester_free(sem_id, day, start_slot):
                return False
            if self.component_type == ComponentType.LAB:
                if not state.is_semester_free(sem_id, day, start_slot + 1):
                    return False
        
        # Check all teachers are free
        for subject_id, teacher_id in self.subject_teacher_map.items():
            if not state.is_teacher_free(teacher_id, day, start_slot):
                return False
            if self.component_type == ComponentType.LAB:
                if not state.is_teacher_free(teacher_id, day, start_slot + 1):
                    return False
        
        return True

    def allocate_at(self, day: int, start_slot: int, state: TimetableState, 
                    rooms: List[Room]) -> List[AllocationEntry]:
        """Allocate this plan at given day/slot. Returns list of entries."""
        if not self.can_allocate_at(day, start_slot, state):
            self.failure_reason = f"Cannot allocate at ({day}, {start_slot})"
            return []
        
        entries = []
        end_slot = start_slot + 1 if self.component_type == ComponentType.LAB else start_slot
        
        for sem_id, subject_id in self.class_subject_map.items():
            teacher_id = self.subject_teacher_map[subject_id]
            room = self._find_room(sem_id, subject_id, state, rooms)
            
            if self.component_type == ComponentType.LAB:
                # Create 2 entries for lab
                for slot in [start_slot, start_slot + 1]:
                    entry = AllocationEntry(
                        semester_id=sem_id,
                        subject_id=subject_id,
                        teacher_id=teacher_id,
                        room_id=room.id,
                        day=day,
                        slot=slot,
                        component_type=ComponentType.LAB,
                        is_lab_continuation=(slot == start_slot + 1),
                        is_elective=True,
                        elective_basket_id=self.basket_id
                    )
                    entries.append(entry)
                    state.add_allocation(entry)
            else:
                # Single entry for theory
                entry = AllocationEntry(
                    semester_id=sem_id,
                    subject_id=subject_id,
                    teacher_id=teacher_id,
                    room_id=room.id,
                    day=day,
                    slot=start_slot,
                    component_type=ComponentType.THEORY,
                    is_elective=True,
                    elective_basket_id=self.basket_id
                )
                entries.append(entry)
                state.add_allocation(entry)
        
        self.is_allocated = True
        self.allocated_day = day
        self.allocated_start_slot = start_slot
        self.allocated_end_slot = end_slot
        return entries

    def _find_room(self, sem_id: int, subject_id: int, state: TimetableState, 
                   rooms: List[Room]) -> Room:
        """Find appropriate room for this subject at allocated slot."""
        # Get capacity needed for this class
        sem = next(s for s in semesters if s.id == sem_id)
        capacity_needed = sem.student_count
        
        # Find room at allocated slot
        room = next(
            (r for r in rooms 
             if r.capacity >= capacity_needed
             and state.is_room_free(r.id, self.allocated_day, self.allocated_start_slot)
             and (self.component_type == ComponentType.THEORY or 
                  state.is_room_free(r.id, self.allocated_day, self.allocated_start_slot + 1))),
            None
        )
        return room
```

---

## Benefits of This Approach

### 1. **Separation of Concerns**
- ✅ Planning logic separate from scheduling logic
- ✅ Each component has a single responsibility
- ✅ Easy to unit test each part

### 2. **Explicit State Tracking**
- ✅ `ElectiveBasketSchedulingPlan` makes intentions clear
- ✅ Developers can see what's being checked before allocation
- ✅ Easier debugging (print plan before/after allocation)

### 3. **Reusable**
- ✅ Can build ALL plans upfront
- ✅ Can test if all plans can be satisfied
- ✅ Can retry with different slot orders

### 4. **Better Error Messages**
- ✅ `failure_reason` explains why allocation failed
- ✅ Can log all failed plans for debugging

---

## Implementation Strategy

### Step 1: Create ElectiveBasketSchedulingPlan Class
- Add to `generator.py`
- Encapsulates allocation logic

### Step 2: Refactor Phase 2
```python
def _schedule_elective_theory(self, ...):
    # 1. Build plans from baskets
    plans = self._build_elective_theory_plans(baskets, semesters, subject_teacher_map)
    
    # 2. Try to allocate each plan
    allocated = 0
    for plan in plans:
        for day, slot in self._get_randomized_slot_order():
            if plan.allocate_at(day, slot, state, rooms):
                allocated += len(plan.allocations)
                break
        else:
            print(f"   [WARN] Failed to allocate {plan.basket_name}: {plan.failure_reason}")
    
    return PhaseResult(True, "Phase 2", f"Allocated {allocated} elective slots", allocated)
```

### Step 3: Refactor Phase 3 (Labs)
- Similar approach but with lab-specific constraints

---

## Validation Checklist

### Constraint 1: Elective Basket Synchronization
- ✅ All subjects of basket scheduled at same (day, slot)
- ✅ All participating classes get same slot
- ✅ Verified in `plan.can_allocate_at()` check

### Constraint 2: Teacher Availability
- ✅ No teacher double-booking at same (day, slot)
- ✅ Checked before allocation in `can_allocate_at()`
- ✅ Updated in `state.add_allocation()`

### Constraint 3: Room Availability
- ✅ Rooms not double-booked
- ✅ Room capacity ≥ class size
- ✅ Found in `_find_room()`

### Constraint 4: Lab Atomicity
- ✅ Lab blocks are 2 consecutive periods
- ✅ Both periods checked and marked as taken
- ✅ `is_lab_continuation` flag tracks second period

### Constraint 5: No Subject Repetition
- ✅ Handled by Phase 5 (subject_daily_counts)
- ✅ Checked before any allocation

---

## Example Flow

```
INPUT:
- ElectiveBasket: "Open Elective 1" (AI, ML, CloudComp)
  - Semester 5
  - 3 classes participate: 5A, 5B, 5C
  - Each class chose one subject (5A→AI, 5B→ML, 5C→CloudComp)
  - 3 hours theory/week

- Teachers: Prof.X (AI), Prof.Y (ML), Prof.Z (CloudComp)

PHASE 1: Lock assignments
- (5A, AI, THEORY) → Prof.X
- (5B, ML, THEORY) → Prof.Y
- (5C, CloudComp, THEORY) → Prof.Z

PHASE 2: Build plan
- Plan: basket_id=1, semester_number=5
  - participating_semesters=[5A, 5B, 5C]
  - class_subject_map={5A→AI, 5B→ML, 5C→CloudComp}
  - subject_teacher_map={AI→ProfX, ML→ProfY, CloudComp→ProfZ}

PHASE 2: Try allocation
- Slot (Mon, 2): 
  - Check 5A free? ✓
  - Check 5B free? ✓
  - Check 5C free? ✓
  - Check ProfX free? ✓
  - Check ProfY free? ✓
  - Check ProfZ free? ✓
  - Allocate!

OUTPUT:
- Allocation(5A, AI, ProfX, Mon, 2, Room201, is_elective=true, basket_id=1)
- Allocation(5B, ML, ProfY, Mon, 2, Room202, is_elective=true, basket_id=1)
- Allocation(5C, CloudComp, ProfZ, Mon, 2, Room203, is_elective=true, basket_id=1)

All 3 classes have elective at same time!
All teachers are available!
No conflicts!
```

---

## Summary

The current system **already implements** all required constraints:
1. ✅ Elective basket synchronization (same slot across classes)
2. ✅ Teacher availability checking
3. ✅ Room allocation
4. ✅ Lab atomicity
5. ✅ Modular 7-phase design

The proposed `ElectiveBasketSchedulingPlan` class would:
- Make the logic more explicit
- Improve testability
- Provide better debugging information
- Not change any core functionality

**Recommendation**: The current implementation is solid. The proposed enhancement is optional but recommended for long-term maintainability.

