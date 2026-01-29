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
