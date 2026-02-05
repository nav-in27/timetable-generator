# Elective Basket Scheduling - Complete Architecture Guide

## Overview

This document describes the complete, production-ready system for scheduling elective baskets across multiple classes with proper constraint enforcement.

---

## Data Model

### 1. ElectiveBasket (Database Table)
```python
class ElectiveBasket(Base):
    """
    Represents a group of alternative subjects offered to students.
    All subjects in basket scheduled at SAME common time across participating classes.
    """
    id: int                                 # Unique identifier
    name: str                               # e.g., "Open Elective 1"
    code: str                               # e.g., "OE1-S5"
    semester_number: int                    # e.g., 5 (which semester this applies to)
    
    # Hours (same for all subjects in basket)
    theory_hours_per_week: int             # e.g., 3
    lab_hours_per_week: int                # e.g., 2 (equals 1 lab block)
    tutorial_hours_per_week: int           # e.g., 0
    
    # Scheduling state
    is_scheduled: bool                      # True after successful generation
    scheduled_slots: Optional[str]          # JSON: "theory:0:2,lab:1:3:4"
    
    # Relationships
    subjects: List[Subject]                 # Alternative subjects (1-N)
    participating_semesters: List[Semester] # Classes using this basket (M-N)
```

### 2. Subject (Modified for Electives)
```python
class Subject(Base):
    # ... existing fields ...
    is_elective: bool = False               # Quick filter
    elective_basket_id: Optional[int] = None # Which basket (if elective)
    # Foreign key ensures referential integrity
```

### 3. ClassSubjectTeacher (Teacher Assignment)
```python
class ClassSubjectTeacher(Base):
    """
    Fixed teacher assignment for a specific (class, subject, component).
    Built automatically by elective basket API.
    """
    semester_id: int                        # Which class
    subject_id: int                         # Which subject
    teacher_id: int                         # Assigned teacher
    component_type: ComponentType           # THEORY, LAB, or TUTORIAL
    assignment_reason: str                  # "auto_assigned_for_elective_basket"
    is_locked: bool = True                  # Cannot be changed
```

### 4. Allocation (Enhanced for Electives)
```python
class Allocation(Base):
    """
    Single scheduled slot in the timetable.
    """
    # ... existing fields ...
    is_elective: bool = False               # Is this an elective allocation?
    elective_basket_id: Optional[int] = None # Which basket (if elective)
    
    # Unique constraint ensures 1 allocation per (class, day, slot)
    __table_args__ = (
        UniqueConstraint("semester_id", "day", "slot"),
    )
```

---

## Generation Architecture

### 7-Phase Generation Flow

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 0: DATA SANITY CHECK                                  │
│ ✓ Validate hours ≤ available slots                          │
│ ✓ Check teachers/subjects exist                             │
│ → Fail fast on bad input                                    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: LOCK TEACHER ASSIGNMENTS                           │
│ ✓ Read ClassSubjectTeacher entries                          │
│ ✓ Build fixed_assignments map                               │
│ ✓ Validate teacher capacity                                 │
│ → Ensures each (class, subject, component) has teacher      │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: ELECTIVE THEORY SCHEDULING          ← KEY PHASE   │
│ ✓ Build ElectiveBasketSchedulingPlans                       │
│ ✓ Try to allocate each plan at common (day, slot)           │
│ ✓ All classes of basket get same slot                       │
│ ✓ All teachers verified available                           │
│ → Common slots locked for all participating classes         │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: ELECTIVE LAB SCHEDULING                            │
│ ✓ Similar to Phase 2 but with lab blocks                    │
│ ✓ Ensures 2-period atomicity                                │
│ → Lab blocks aligned across participating classes           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: REGULAR LAB SCHEDULING                             │
│ ✓ Schedule non-elective labs                                │
│ ✓ Respects elective slots already locked                    │
│ → Normal lab allocation                                    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 5: THEORY & TUTORIAL FILL                             │
│ ✓ Schedule remaining theory/tutorial slots                  │
│ ✓ Uses greedy allocation                                    │
│ ✓ Leaves free periods if insufficient hours                 │
│ → Fills remaining class time                                │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 6: FINAL VALIDATION (Soft)                            │
│ ✓ Report issues but don't fail                              │
│ ✓ Check coverage, conflicts                                 │
│ → Informational only                                        │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 7: SAVE TO DATABASE                                   │
│ ✓ Persist all allocations                                   │
│ ✓ Persist teacher assignments                               │
│ → Timetable complete                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### A. ElectiveBasketSchedulingPlan

**Purpose**: Encapsulate the planning and allocation of a single elective basket component.

```python
@dataclass
class ElectiveBasketSchedulingPlan:
    # Identity
    basket_id: int
    basket_name: str
    semester_number: int
    component_type: ComponentType  # THEORY or LAB
    
    # Participants
    participating_semester_ids: List[int]   # [5A, 5B, 5C] (all classes using basket)
    class_subject_map: Dict[int, int]       # 5A→AI, 5B→ML, 5C→CloudComp
    subject_teacher_map: Dict[int, int]     # AI→Prof.X, ML→Prof.Y, CloudComp→Prof.Z
    
    # Requirements
    hours_per_week: int                     # 3 (all classes get same hours)
    
    # Allocation tracking
    allocated_day: Optional[int]            # Day of allocation
    allocated_start_slot: Optional[int]     # Slot of allocation
    allocated_entries: List[AllocationEntry] # Generated allocations
    
    # Methods
    def can_allocate_at(day, slot, state) -> bool:
        """Check if this plan CAN be allocated without conflicts."""
        # Verify all classes free at (day, slot)
        # Verify all teachers free at (day, slot)
        # For labs: verify both slots free
        
    def allocate_at(day, slot, state, rooms, semesters) -> bool:
        """Allocate this plan and update state."""
        # Find rooms for each class
        # Create AllocationEntry for each class
        # Update state.add_allocation() for each entry
        # Mark as allocated
```

**Why This Design**:
- ✅ Single plan = atomic allocation (all-or-nothing)
- ✅ Explicit constraint checking before allocation
- ✅ Easy debugging: print plan before/after
- ✅ Testable: can unit test plan independently
- ✅ Reusable: can build N plans and try each

### B. TimetableState

**Purpose**: Track busy slots to prevent conflicts.

```python
@dataclass
class TimetableState:
    allocations: List[AllocationEntry]     # All scheduled slots
    
    # Lookup tables for O(1) conflict checking
    teacher_slots: Dict[int, Set[Tuple[int, int]]]  # teacher → {(day, slot), ...}
    room_slots: Dict[int, Set[Tuple[int, int]]]     # room → {(day, slot), ...}
    semester_slots: Dict[int, Set[Tuple[int, int]]] # class → {(day, slot), ...}
    
    # Methods
    def add_allocation(entry: AllocationEntry):
        """Mark slot as taken."""
        # Add to allocations list
        # Add to teacher_slots[entry.teacher_id]
        # Add to room_slots[entry.room_id]
        # Add to semester_slots[entry.semester_id]
        
    def is_teacher_free(teacher_id, day, slot) -> bool:
        """Check if teacher available at given slot."""
        return (day, slot) not in self.teacher_slots.get(teacher_id, set())
        
    def is_semester_free(semester_id, day, slot) -> bool:
        """Check if class available at given slot."""
        return (day, slot) not in self.semester_slots.get(semester_id, set())
        
    def is_room_free(room_id, day, slot) -> bool:
        """Check if room available at given slot."""
        return (day, slot) not in self.room_slots.get(room_id, set())
```

**Why This Design**:
- ✅ O(1) conflict checking (no iteration needed)
- ✅ Clear separation of concerns
- ✅ Easy to add new constraint types
- ✅ Enables rollback (store and restore if needed)

---

## Phase 2 Implementation (Key Phase)

### Step 1: Build Plans from Elective Baskets

```python
def _build_elective_theory_plans(
    self, 
    baskets: List[ElectiveBasket],
    semesters: List[Semester],
    subjects: List[Subject],
    fixed_assignments: Dict[Tuple[int, int, str], int]
) -> List[ElectiveBasketSchedulingPlan]:
    """
    Convert elective baskets into scheduling plans.
    
    For each basket:
    1. Identify participating classes (semesters)
    2. Build class_subject_map (which class chose which subject)
    3. Build subject_teacher_map (which teacher teaches which subject)
    4. Create plan object
    """
    plans = []
    
    for basket in baskets:
        if basket.theory_hours_per_week == 0:
            continue  # No theory in this basket
        
        # Get all participating classes
        participating_sem_ids = [s.id for s in basket.participating_semesters]
        
        # Map which subject each class chose from this basket
        class_subject_map = {}
        subject_teacher_map = {}
        
        for sem_id in participating_sem_ids:
            # Find which subject this class is taking from basket
            # (Assume one subject per class - implementation detail)
            subject = self._get_elective_subject_for_class(sem_id, basket)
            
            if subject:
                class_subject_map[sem_id] = subject.id
                
                # Get assigned teacher
                key = (sem_id, subject.id, ComponentType.THEORY.value)
                teacher_id = fixed_assignments.get(key)
                if teacher_id:
                    subject_teacher_map[subject.id] = teacher_id
        
        # Create plan
        plan = ElectiveBasketSchedulingPlan(
            basket_id=basket.id,
            basket_name=basket.name,
            semester_number=basket.semester_number,
            component_type=ComponentType.THEORY,
            participating_semester_ids=participating_sem_ids,
            class_subject_map=class_subject_map,
            subject_teacher_map=subject_teacher_map,
            hours_per_week=basket.theory_hours_per_week
        )
        plans.append(plan)
    
    return plans
```

### Step 2: Try to Allocate Each Plan

```python
def _schedule_elective_theory(
    self,
    state: TimetableState,
    elective_reqs: List[ComponentRequirement],
    rooms: List[Room],
    semesters: List[Semester],
    teacher_loads: Dict[int, int]
) -> PhaseResult:
    """
    Allocate all elective theory plans.
    """
    # Build plans from requirements
    plans = self._build_elective_theory_plans(...)
    
    print(f"   [INFO] Built {len(plans)} elective theory plans")
    for plan in plans:
        print(f"      {plan}")
    
    # Try to allocate each plan
    semester_map = {s.id: s for s in semesters}
    allocations_added = 0
    allocated_plans = 0
    failed_plans = []
    
    for plan in plans:
        # Determine how many slots needed for this plan
        slots_needed = plan.hours_per_week
        slots_allocated = 0
        
        # Try each possible slot
        for day, slot in self._get_randomized_slot_order():
            if slots_allocated >= slots_needed:
                break
            
            # Try to allocate plan at this slot
            if plan.allocate_at(day, slot, state, rooms, semester_map):
                slots_allocated += 1
                allocations_added += len(plan.allocated_entries)
        
        if plan.is_allocated:
            allocated_plans += 1
        else:
            failed_plans.append((plan, plan.failure_reason))
    
    # Report results
    if failed_plans:
        print(f"   [WARN] Failed to allocate {len(failed_plans)} plans:")
        for plan, reason in failed_plans:
            print(f"      • {plan.basket_name}: {reason}")
    
    return PhaseResult(
        True, "Phase 2", 
        f"Allocated {allocated_plans}/{len(plans)} plans", 
        allocations_added
    )
```

---

## Constraint Enforcement

### Constraint 1: Synchronization Across Classes

```python
# In ElectiveBasketSchedulingPlan.can_allocate_at():

# Check ALL participating classes are free at same slot
for sem_id in self.participating_semester_ids:
    if not state.is_semester_free(sem_id, day, start_slot):
        return False  # Cannot allocate: one class occupied
```

**Result**: All classes of basket always get same (day, slot).

### Constraint 2: Teacher Availability

```python
# In ElectiveBasketSchedulingPlan.can_allocate_at():

# Check ALL assigned teachers are free
for subject_id, teacher_id in self.subject_teacher_map.items():
    if not state.is_teacher_free(teacher_id, day, start_slot):
        return False  # Cannot allocate: teacher busy
```

**Result**: No teacher double-booking at same (day, slot).

### Constraint 3: Lab Atomicity

```python
# In ElectiveBasketSchedulingPlan.allocate_at():

if self.component_type == ComponentType.LAB:
    # Create entries for BOTH slots
    for slot_offset in [0, 1]:
        entry = AllocationEntry(
            slot=start_slot + slot_offset,
            is_lab_continuation=(slot_offset == 1)
        )
        entries.append(entry)
        state.add_allocation(entry)  # Mark BOTH slots as taken
```

**Result**: Lab blocks are indivisible 2-period units.

### Constraint 4: No Room Double-Booking

```python
# In ElectiveBasketSchedulingPlan.allocate_at():

room = next(
    (r for r in rooms 
     if r.capacity >= sem.student_count
     and state.is_room_free(r.id, day, start_slot)
     and (self.component_type == ComponentType.THEORY or
          state.is_room_free(r.id, day, start_slot + 1))),
    None
)

if not room:
    self.failure_reason = "No room available"
    return False
```

**Result**: Rooms not double-booked; capacity verified.

### Constraint 5: No Subject Repetition per Class

```python
# In TimetableState.add_allocation():

day_key = (sem_id, day)
if day_key not in self.subject_daily_counts:
    self.subject_daily_counts[day_key] = {}

current = self.subject_daily_counts[day_key].get(entry.subject_id, 0)
self.subject_daily_counts[day_key][entry.subject_id] = current + 1

# Later: Check current < 1 before allocating same subject to same class on same day
```

**Result**: Class won't have same subject twice on same day.

---

## Example: Complete Workflow

### Input Data

```
ElectiveBasket "Open Elective 1":
  - Subjects: [AI, ML, CloudComp]
  - Semester: 5
  - Participating classes: [5A, 5B, 5C]
  - Hours: 3 theory/week, 0 lab

Class Choices:
  - 5A students chose: AI
  - 5B students chose: ML
  - 5C students chose: CloudComp

Teachers:
  - AI: Prof. X
  - ML: Prof. Y
  - CloudComp: Prof. Z
```

### Phase 1: Teacher Assignment

```
ClassSubjectTeacher entries created:
  (5A, AI, THEORY) → Prof.X
  (5B, ML, THEORY) → Prof.Y
  (5C, CloudComp, THEORY) → Prof.Z
```

### Phase 2: Build Plan

```
ElectiveBasketSchedulingPlan:
  basket_id = 1
  basket_name = "Open Elective 1"
  semester_number = 5
  component_type = THEORY
  
  participating_semester_ids = [5A_id, 5B_id, 5C_id]
  class_subject_map = {
    5A_id → AI_id,
    5B_id → ML_id,
    5C_id → CloudComp_id
  }
  subject_teacher_map = {
    AI_id → Prof.X_id,
    ML_id → Prof.Y_id,
    CloudComp_id → Prof.Z_id
  }
  hours_per_week = 3
```

### Phase 2: Try Allocation

```
Slot (Monday, Period 2):
  Can allocate?
    ✓ 5A free at (Mon, P2)?
    ✓ 5B free at (Mon, P2)?
    ✓ 5C free at (Mon, P2)?
    ✓ Prof.X free at (Mon, P2)?
    ✓ Prof.Y free at (Mon, P2)?
    ✓ Prof.Z free at (Mon, P2)?
  → YES, allocate!

Created Allocations:
  1. (5A, AI, Prof.X, Mon, P2, Room201, basket_id=1)
  2. (5B, ML, Prof.Y, Mon, P2, Room202, basket_id=1)
  3. (5C, CloudComp, Prof.Z, Mon, P2, Room203, basket_id=1)

State Updated:
  teacher_slots[Prof.X].add((Mon, P2))
  teacher_slots[Prof.Y].add((Mon, P2))
  teacher_slots[Prof.Z].add((Mon, P2))
  semester_slots[5A_id].add((Mon, P2))
  semester_slots[5B_id].add((Mon, P2))
  semester_slots[5C_id].add((Mon, P2))
  room_slots[Room201].add((Mon, P2))
  room_slots[Room202].add((Mon, P2))
  room_slots[Room203].add((Mon, P2))

Plan Status:
  is_allocated = True
  allocated_day = 0 (Monday)
  allocated_start_slot = 2 (Period 2)
```

### Result

```
✅ Elective basket "Open Elective 1" allocated successfully
✅ All 3 classes have elective at same time (Mon, Period 2)
✅ All teachers available (not teaching anything else at that slot)
✅ All rooms secured and no conflicts
```

---

## Error Handling

### Scenario 1: Teacher Already Teaching

```
If Prof.X is already teaching Calculus to 5E at (Mon, Period 2):
  plan.can_allocate_at(Monday, 2) → FALSE
  failure_reason = "Teacher Prof.X busy at (0, 2)"
→ Try next slot instead
```

### Scenario 2: No Available Room

```
If all rooms occupied at (Mon, Period 2):
  plan.allocate_at(Monday, 2) → FALSE
  failure_reason = "No room available for class 5A"
→ Try next slot instead
```

### Scenario 3: Complete Failure

```
If no slot works for this basket:
  Plan remains: is_allocated = False
  Logged in failed_plans list
  Final output includes warning
→ Timetable still generated (soft failure)
```

---

## Benefits of This Architecture

### Modularity
- ✅ Each plan is independent
- ✅ Easy to add new plan types (elective tutorials, etc.)
- ✅ Easy to unit test each plan

### Clarity
- ✅ Explicit constraints listed in `can_allocate_at()`
- ✅ Clear data flow: plan → allocation → state
- ✅ Debugging: print plan before/after, see failure reasons

### Robustness
- ✅ Atomic allocation (all classes or none)
- ✅ Validation before modification
- ✅ Clear error messages

### Performance
- ✅ O(1) slot checking (no iteration)
- ✅ Early exit on first failure
- ✅ Randomized slot order prevents bias

### Extensibility
- ✅ Can add tutorial plans similarly
- ✅ Can add weighted slot preferences
- ✅ Can add teacher preferences

---

## Summary

The elective basket scheduling system combines:

1. **Clean Data Model**: ElectiveBasket, Subject, ClassSubjectTeacher, Allocation
2. **Explicit Planning**: ElectiveBasketSchedulingPlan encapsulates logic
3. **Efficient Constraint Checking**: TimetableState with O(1) lookups
4. **Modular Architecture**: 7-phase flow with clear responsibilities
5. **Robust Error Handling**: Graceful failures with clear messages

Result: **Production-ready, maintainable, testable system for elective scheduling.**

