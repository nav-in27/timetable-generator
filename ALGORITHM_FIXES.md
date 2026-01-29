# Timetable Generator - Algorithm Fixes

This document describes the fixes for two critical logical issues in the timetable generation algorithm.

---

## Issue 1: Same Subject – Multiple Teachers (BUG FIX)

### Problem
For a given class and subject, different teachers were being assigned on different days (e.g., DBMS taught by 3 different teachers in the same class across the week).

### Root Cause
The original algorithm dynamically selected teachers for each slot based on availability and load. This meant:
- `_schedule_theory_slot()` selected different teachers each time
- `_schedule_lab_session()` similarly picked the "best" teacher for each session
- GA mutation `_mutate_state()` was swapping teachers between allocations

### Fix Implemented

#### 1. New Database Model: `ClassSubjectTeacher`
```python
class ClassSubjectTeacher(Base):
    """Fixed one-to-one mapping of (semester, subject) -> teacher."""
    __tablename__ = "class_subject_teachers"
    
    semester_id: ForeignKey("semesters.id")
    subject_id: ForeignKey("subjects.id")  
    teacher_id: ForeignKey("teachers.id")
    is_locked: Boolean = True
```

**Constraint:** `UniqueConstraint("semester_id", "subject_id")` ensures exactly ONE teacher per (class, subject).

#### 2. Pre-Assignment Phase (Phase 0)

Before ANY slot scheduling, the algorithm now:

```python
def _assign_fixed_teachers(self, semesters, subjects, teacher_subject_map, teacher_by_id):
    """
    Assign exactly ONE teacher per (semester, subject) pair.
    
    Selection criteria:
    1. Subject specialization match (mandatory)
    2. Lowest projected workload (balance)
    3. Highest effectiveness score (quality)
    """
    fixed_assignments: Dict[Tuple[int, int], int] = {}
    projected_workload: Dict[int, int] = {}
    
    for semester in semesters:
        for subject in subjects:
            key = (semester.id, subject.id)
            # Select best available qualified teacher
            selected_teacher_id = ... # Based on workload + experience
            fixed_assignments[key] = selected_teacher_id
            projected_workload[selected_teacher_id] += subject.weekly_hours
    
    return fixed_assignments
```

#### 3. Fixed Teacher Scheduling Methods

New methods that use pre-assigned teachers:
- `_schedule_lab_session_with_fixed_teacher()`
- `_schedule_theory_slot_with_fixed_teacher()`
- `_fill_empty_slot_with_fixed_teacher()`
- `_try_assign_fixed_teacher_to_slot()`

These methods **NEVER dynamically select teachers**. They use:
```python
fixed_teacher_id = fixed_assignments.get((semester_id, subject_id))
```

#### 4. Safe GA Mutation

`_mutate_state_safe()` replaces the old mutation:
- **NEVER swaps teacher assignments**
- Only swaps SLOTS between allocations of the same semester
- Preserves fixed_teacher_assignments dictionary

### Verification

After fix, for any (semester_id, subject_id) pair:
```sql
SELECT DISTINCT teacher_id FROM allocations 
WHERE semester_id = ? AND subject_id = ?
-- Returns exactly 1 row
```

---

## Issue 2: Elective Subjects Not Synchronized (BUG FIX)

### Problem
Elective subjects taken by students from multiple departments were being scheduled at different times in different departments.

### Root Cause
The original algorithm treated each semester independently with no concept of shared elective subjects.

### Fix Implemented

#### 1. New Database Models

**ElectiveGroup:**
```python
class ElectiveGroup(Base):
    """Shared elective subject across multiple semesters."""
    __tablename__ = "elective_groups"
    
    subject_id: ForeignKey("subjects.id")
    teacher_id: ForeignKey("teachers.id")  # Fixed teacher
    hours_per_week: Integer
    elective_code: String (unique)
    is_scheduled: Boolean = False
    scheduled_slots: String  # "day:slot,day:slot,..."
    
    # Many-to-many with semesters
    participating_semesters: relationship(Semester, secondary=elective_group_semesters)
```

**Association Table:**
```python
elective_group_semesters = Table(
    "elective_group_semesters",
    Column("elective_group_id", ForeignKey("elective_groups.id")),
    Column("semester_id", ForeignKey("semesters.id")),
)
```

#### 2. Elective Scheduling Phase (Phase 1)

Electives are scheduled **BEFORE** normal subjects:

```python
def _schedule_elective_group(self, state, elective, rooms, ...):
    """
    Find COMMON slot where:
    1. Assigned teacher is free
    2. ALL participating semesters are free
    3. Suitable room is available
    
    Then:
    - Create allocation for EACH participating semester
    - Mark slot as LOCKED (is_elective=True)
    - Update elective.scheduled_slots
    """
    participating_semester_ids = [s.id for s in elective.participating_semesters]
    
    for day, slot in slot_order:
        # Check teacher free
        if not state.is_teacher_free(elective.teacher_id, day, slot):
            continue
            
        # Check ALL semesters free
        all_free = all(
            state.is_semester_free(sem_id, day, slot) 
            for sem_id in participating_semester_ids
        )
        if not all_free:
            continue
        
        # Schedule for ALL semesters at same slot
        for sem_id in participating_semester_ids:
            entry = AllocationEntry(
                semester_id=sem_id,
                subject_id=elective.subject_id,
                teacher_id=elective.teacher_id,
                day=day, slot=slot,
                is_elective=True,
                elective_group_id=elective.id
            )
            state.add_allocation(entry)
```

#### 3. Locked Elective Slots

In `TimetableState`:
```python
locked_elective_slots: Dict[Tuple[int, int, int], int]  # (semester_id, day, slot) -> elective_group_id

def is_slot_locked(self, semester_id, day, slot) -> bool:
    return (semester_id, day, slot) in self.locked_elective_slots
```

Normal scheduling **skips** locked slots:
```python
if state.is_slot_locked(semester_id, day, slot):
    continue
```

#### 4. Elective Allocations Protected from Mutation

`_mutate_state_safe()` excludes elective allocations:
```python
mutable_allocations = [
    (i, a) for i, a in enumerate(state.allocations)
    if not a.is_elective and not a.is_lab_continuation
]
```

### Verification

After fix, for any elective group:
```sql
SELECT DISTINCT day, slot FROM allocations 
WHERE elective_group_id = ?
GROUP BY semester_id
-- All semesters have SAME day/slot values
```

---

## Issue 3: Same Subject Multiple Times Per Day (BUG FIX)

### Problem
A single subject was being scheduled 2-3 times on the same day for the same class (e.g., DBMS appearing in periods 1, 3, and 5 on Monday for a single class).

### Root Cause
The algorithm had no constraint preventing the same subject from being scheduled multiple times on the same day. It only checked:
- Teacher availability
- Room availability
- Semester slot availability

But not whether the subject was already scheduled that day.

### Fix Implemented

#### 1. New Tracking in `TimetableState`

Added a lookup table to track which subjects are scheduled per (semester, day):

```python
# Key: (semester_id, day), Value: Set of subject_ids scheduled that day
subject_per_day: Dict[Tuple[int, int], Set[int]] = field(default_factory=dict)
```

#### 2. Updated `add_allocation()` Method

Now tracks subject-per-day when adding allocations:

```python
def add_allocation(self, entry: AllocationEntry):
    # ... existing code ...
    
    # ONE SUBJECT PER DAY: Track this subject for this (semester, day)
    day_key = (entry.semester_id, entry.day)
    if day_key not in self.subject_per_day:
        self.subject_per_day[day_key] = set()
    self.subject_per_day[day_key].add(entry.subject_id)
```

#### 3. New Helper Method

```python
def is_subject_scheduled_on_day(self, semester_id: int, day: int, subject_id: int) -> bool:
    """Check if a subject is already scheduled for this semester on this day."""
    day_key = (semester_id, day)
    if day_key not in self.subject_per_day:
        return False
    return subject_id in self.subject_per_day[day_key]
```

#### 4. Constraint Enforced In All Scheduling Functions

The following functions now check this constraint BEFORE scheduling:

- `_schedule_theory_slot_with_fixed_teacher()` - Theory classes
- `_schedule_lab_session_with_fixed_teacher()` - Lab sessions (2 consecutive periods)
- `_try_assign_fixed_teacher_to_slot()` - Empty slot filling
- `_try_assign_teacher_to_slot()` - Dynamic teacher assignment
- `_schedule_lab_session()` - Lab sessions (non-fixed teacher)
- `_schedule_theory_slot()` - Theory classes (non-fixed teacher)

Example check:
```python
# ONE SUBJECT PER DAY: Skip if this subject is already scheduled on this day
if state.is_subject_scheduled_on_day(req.semester_id, day, req.subject_id):
    continue
```

### Verification

After fix, for any (semester_id, day) pair:
```sql
SELECT subject_id, COUNT(*) as count FROM allocations 
WHERE semester_id = ? AND day = ?
GROUP BY subject_id
HAVING count > 1
-- Returns 0 rows (no subject appears more than once per day)
```

**Note:** Labs still occupy 2 consecutive slots, but they count as ONE subject occurrence for that day.

---

## Issue 4: Lab Continuity Bug (BUG FIX)

### Problem
Lab subjects were being scheduled as separate single periods instead of continuous two-period blocks. Labs were appearing:
- In non-consecutive slots (e.g., periods 1 and 3)
- Before lunch (violating academic rules)
- Split across different days

### Academic Rule (HARD CONSTRAINT)
Labs MUST occupy EXACTLY TWO CONTINUOUS PERIODS:
- Both periods on the SAME DAY
- Back-to-back (consecutive slots)
- ONLY in these valid blocks:
  * 4th + 5th period (slots 3, 4 in 0-indexed) OR
  * 6th + 7th period (slots 5, 6 in 0-indexed)
- Labs BEFORE lunch are NOT allowed

### Root Cause
The original algorithm allowed labs in ANY consecutive slots:
```python
# OLD (WRONG):
LAB_SLOT_PAIRS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]
```

Additionally, GA mutation could split lab blocks by swapping individual periods.

### Fix Implemented

#### 1. Valid Lab Blocks Restricted

```python
# NEW (CORRECT):
# Labs ONLY allowed in post-lunch blocks
VALID_LAB_BLOCKS = [(3, 4), (5, 6)]  # 4th+5th or 6th+7th period only

class TimetableGenerator:
    LAB_SLOT_PAIRS = [(3, 4), (5, 6)]  # ONLY valid lab blocks
```

#### 2. Lab Block Tracking in TimetableState

Added tracking to ensure lab blocks are treated as ATOMIC UNITS:

```python
# Key: (semester_id, day, start_slot)
# Value: (subject_id, teacher_id, room_id, end_slot)
lab_blocks: Dict[Tuple[int, int, int], Tuple[int, int, int, int]]

def register_lab_block(self, semester_id, day, start_slot, end_slot, 
                       subject_id, teacher_id, room_id):
    """Register a lab block as an atomic unit."""
    block_key = (semester_id, day, start_slot)
    self.lab_blocks[block_key] = (subject_id, teacher_id, room_id, end_slot)

def is_slot_in_lab_block(self, semester_id, day, slot) -> bool:
    """Check if a slot is part of a LAB BLOCK."""
    # Returns True if slot is start OR end of a lab block

def get_lab_block_for_slot(self, semester_id, day, slot) -> Optional[Tuple[int, int]]:
    """Get the (start_slot, end_slot) of the lab block containing this slot."""
```

#### 3. Lab Block Registration During Scheduling

When scheduling a lab, both periods are registered as an atomic block:

```python
# In _schedule_lab_session_with_fixed_teacher():
state.add_allocation(entry1)  # Start slot
state.add_allocation(entry2)  # End slot (is_lab_continuation=True)

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
```

#### 4. Safe GA Mutation for Lab Blocks

`_mutate_state_safe()` now handles labs as atomic units:

```python
def _mutate_state_safe(self, state, teachers, fixed_assignments):
    # Separate theory and lab allocations
    theory_allocations = []
    lab_start_allocations = []  # Only start slots of lab blocks
    
    for i, a in enumerate(state.allocations):
        if a.is_elective:
            continue  # Never mutate electives
        if a.is_lab_continuation:
            continue  # Skip (handled with start slots)
        if state.is_slot_in_lab_block(a.semester_id, a.day, a.slot):
            lab_start_allocations.append((i, a))
        else:
            theory_allocations.append((i, a))
    
    # MUTATION TYPE 1: Swap theory allocations (individual slots)
    # ... (normal theory swaps)
    
    # MUTATION TYPE 2: Move lab block to different valid lab block slot
    # BOTH periods move together as ONE unit
    if lab_start_allocations and random.random() < 0.3:
        # Find the lab block and its continuation
        # Move BOTH to a new valid lab block position
        lab_alloc.day = new_day
        lab_alloc.slot = new_start
        continuation_alloc.day = new_day
        continuation_alloc.slot = new_end
```

### Pseudocode: Lab Block Assignment

```
FUNCTION schedule_lab_block(semester, subject, teacher, rooms):
    VALID_BLOCKS = [(3, 4), (5, 6)]  # Post-lunch only
    
    FOR each day in [Mon, Tue, Wed, Thu, Fri]:
        # Check if subject already scheduled this day
        IF subject_on_day(semester, day, subject):
            CONTINUE
        
        FOR each (start_slot, end_slot) in VALID_BLOCKS:
            # Check both slots are free
            IF NOT semester_free(semester, day, start_slot):
                CONTINUE
            IF NOT semester_free(semester, day, end_slot):
                CONTINUE
            
            # Check teacher available for both
            IF NOT teacher_free(teacher, day, start_slot):
                CONTINUE
            IF NOT teacher_free(teacher, day, end_slot):
                CONTINUE
            
            # Find room available for both
            room = find_room(rooms, day, start_slot, end_slot)
            IF room IS NULL:
                CONTINUE
            
            # ALLOCATE BOTH SLOTS AS ATOMIC BLOCK
            alloc1 = Allocation(semester, subject, teacher, room, 
                               day, start_slot, is_lab_continuation=False)
            alloc2 = Allocation(semester, subject, teacher, room, 
                               day, end_slot, is_lab_continuation=True)
            
            state.add_allocation(alloc1)
            state.add_allocation(alloc2)
            
            # REGISTER AS ATOMIC UNIT
            state.register_lab_block(semester, day, start_slot, end_slot, 
                                     subject, teacher, room)
            
            RETURN SUCCESS
    
    RETURN FAILURE
```

### Verification

After fix, for any lab subject:
```sql
-- All lab allocations should have is_lab_continuation pairs
SELECT a1.day, a1.slot, a2.slot
FROM allocations a1
JOIN allocations a2 ON a1.semester_id = a2.semester_id 
                   AND a1.subject_id = a2.subject_id 
                   AND a1.day = a2.day
WHERE a1.is_lab_continuation = FALSE 
  AND a2.is_lab_continuation = TRUE
  AND a2.slot = a1.slot + 1
  AND a1.slot IN (3, 5)  -- Only valid start slots
-- All labs should match this pattern
```

### How Lab Continuity is Guaranteed

1. **At Scheduling Time**:
   - Labs are ONLY scheduled in valid blocks: (3,4) or (5,6)
   - Both periods are allocated together in a single operation
   - The lab block is registered as an atomic unit in `lab_blocks`

2. **At Mutation Time**:
   - Lab blocks are identified by checking `is_slot_in_lab_block()`
   - Individual lab periods are NEVER swapped
   - Lab blocks can only move to OTHER valid lab block positions
   - Both periods (start + continuation) move together

3. **At State Rebuild Time**:
   - Lab blocks are re-registered from allocations
   - Verification ensures start + continuation are consecutive

---

## Algorithm Flow (Final)

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 0: PREPROCESSING                    │
├─────────────────────────────────────────────────────────────┤
│ 1. Load all semesters, subjects, teachers, rooms            │
│ 2. Build teacher-subject qualification map                   │
│ 3. _assign_fixed_teachers():                                 │
│    - For each (semester, subject):                           │
│      → Select ONE teacher (lowest load + highest score)      │
│      → Store in fixed_assignments dict                       │
│    - Result: (semester_id, subject_id) → teacher_id          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                PHASE 1: ELECTIVE SCHEDULING                  │
├─────────────────────────────────────────────────────────────┤
│ For each ElectiveGroup (is_active=True):                    │
│ 1. Get participating_semester_ids                            │
│ 2. For each (day, slot):                                     │
│    - Check teacher free at (day, slot)                       │
│    - Check ALL semesters free at (day, slot)                 │
│    - If all free:                                            │
│      → Create allocation for EACH semester                   │
│      → Mark as is_elective=True                              │
│      → Add to locked_elective_slots                          │
│ 3. Store scheduled_slots in ElectiveGroup                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                PHASE 2: NORMAL SCHEDULING                    │
├─────────────────────────────────────────────────────────────┤
│ 2a. Schedule Labs (2 consecutive slots):                     │
│     - Use _schedule_lab_session_with_fixed_teacher()         │
│     - Skip locked elective slots                             │
│     - Use FIXED teacher from fixed_assignments               │
│                                                              │
│ 2b. Schedule Theory (single slots):                          │
│     - Use _schedule_theory_slot_with_fixed_teacher()         │
│     - Skip locked elective slots                             │
│     - Use FIXED teacher from fixed_assignments               │
│                                                              │
│ 2c. Fill Empty Slots:                                        │
│     - Use _fill_empty_slot_with_fixed_teacher()              │
│     - Skip locked elective slots                             │
│     - Use FIXED teacher from fixed_assignments               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 PHASE 3: GA OPTIMIZATION                     │
├─────────────────────────────────────────────────────────────┤
│ _genetic_optimize() with constraints:                        │
│ - NEVER change teacher assignments                           │
│ - NEVER move elective slots                                  │
│ - Only swap SLOTS between non-elective allocations           │
│                                                              │
│ _mutate_state_safe():                                        │
│ - Filter out is_elective=True allocations                    │
│ - Swap (day, slot) between allocations of same semester      │
│ - Preserve fixed_teacher_assignments                         │
│ - Preserve locked_elective_slots                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 4: SAVE                             │
├─────────────────────────────────────────────────────────────┤
│ 1. _save_allocations(): Write allocations to DB              │
│ 2. _save_fixed_assignments(): Write ClassSubjectTeacher      │
│    records for future reference                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Constraint Summary

### HARD CONSTRAINTS (Enforced by Prevention)

| Constraint | Enforcement |
|------------|-------------|
| One teacher per (class, subject) | Pre-assignment in Phase 0 |
| Same elective = same slot across depts | Shared scheduling in Phase 1 |
| One subject per day per class | `is_subject_scheduled_on_day()` check |
| **Lab blocks are atomic** | `register_lab_block()` + atomic mutation |
| **Labs only in valid blocks** | `LAB_SLOT_PAIRS = [(3,4), (5,6)]` |
| No teacher double booking | `is_teacher_free()` check |
| No room conflicts | `is_room_free()` check |
| Teacher must be qualified | `teacher_subject_map` |

### SOFT CONSTRAINTS (Optimized by GA)

| Constraint | Optimization |
|------------|--------------|
| Max 2 consecutive classes | Fitness penalty |
| Balanced workload | Variance penalty |
| Fill all 7 periods | Slot count bonus |

---

## Files Modified

1. **`backend/app/db/models.py`**
   - Added `ClassSubjectTeacher` model
   - Added `ElectiveGroup` model
   - Added `elective_group_semesters` association table

2. **`backend/app/services/generator.py`**
   - Updated imports to include new models
   - Added `SlotRequirement.assigned_teacher_id`
   - Added `AllocationEntry.is_elective`, `elective_group_id`
   - Added `TimetableState.fixed_teacher_assignments`, `locked_elective_slots`
   - Added `TimetableState.is_slot_locked()`
   - Added `_assign_fixed_teachers()`
   - Added `_schedule_elective_group()`
   - Added `_schedule_lab_session_with_fixed_teacher()`
   - Added `_schedule_theory_slot_with_fixed_teacher()`
   - Added `_fill_empty_slot_with_fixed_teacher()`
   - Added `_try_assign_fixed_teacher_to_slot()`
   - Added `_mutate_state_safe()`
   - Added `_save_fixed_assignments()`
   - Modified `generate()` with 4-phase flow
   - Modified `_genetic_optimize()` to use safe mutation
   - Modified `_greedy_generate()` to use fixed teachers

---

## Migration Notes

After deploying these changes:

1. **Database Migration Required:**
   ```bash
   python -c "from app.db.base import Base; from app.db.session import engine; from app.db.models import *; Base.metadata.create_all(bind=engine)"
   ```

2. **Elective Groups Must Be Created:**
   Before electives sync properly, create `ElectiveGroup` records with:
   - `subject_id`: The elective subject
   - `teacher_id`: Fixed teacher for this elective
   - `participating_semesters`: List of semesters taking this elective
   - `hours_per_week`: Required hours

3. **Clear Existing Timetables:**
   Re-generate timetables to use the new algorithm:
   ```python
   generator.generate(clear_existing=True)
   ```
