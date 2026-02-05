# Multi-Elective Group Support - Technical Reference

## Overview

This document describes the extended elective handling logic that supports **multiple elective groups per year**. Each group (e.g., Elective-1, Elective-2, Elective-3) within the same academic year is scheduled independently with its own subjects, teachers, and time slots.

## Key Concepts

### Elective Group Identification

Elective groups are uniquely identified by a **`(year, basket_id)` tuple**:

- `year`: The semester/year number (e.g., 5 for 5th semester)
- `basket_id`: The `elective_basket_id` from the Subject model

Example:
```
(5, 1) -> Elective Group 1 for 5th semester
(5, 2) -> Elective Group 2 for 5th semester
(5, 3) -> Elective Group 3 for 5th semester
```

### Data Detection

The generator detects elective subjects using:
```python
is_elective = (
    subject.is_elective or 
    subject.subject_type == SubjectType.ELECTIVE or
    subject.elective_basket_id is not None
)
```

## Implementation Details

### TimetableState Extensions

The `TimetableState` class now includes:

1. **`elective_slot_ownership`**: Maps `(day, slot)` to `(year, basket_id)` - tracks which group owns each slot
2. **`elective_slots_by_group`**: Maps `(year, basket_id)` to list of reserved slots
3. **`teacher_elective_groups`**: Maps `teacher_id` to set of groups they belong to

### New Methods

#### `reserve_elective_slot_for_group(day, slot, year, basket_id, teacher_ids)`
Reserves a slot for a specific elective group. This:
- Marks slot ownership
- Tracks the slot for the group
- Locks teachers for this slot
- Registers teachers as belonging to this group

#### `is_slot_reserved_for_other_group(day, slot, year, basket_id)`
Checks if a slot is reserved by a DIFFERENT elective group.
Returns `True` if another group owns the slot, `False` otherwise.

#### `register_teacher_elective_group(teacher_id, year, basket_id)`
Registers a teacher as belonging to a specific elective group.

#### `is_teacher_eligible_for_elective_group(teacher_id, day, slot, year, basket_id)`
Strict eligibility check that ensures:
1. Teacher is free (not already teaching)
2. Slot is not reserved for a different elective group
3. Teacher is assigned to this elective group

## Generation Flow

### Step 1: Detection
All elective groups are detected from existing data:
```python
elective_groups = self._detect_elective_groups(semesters, subjects, teacher_assignment_map)
```

### Step 2: Teacher Registration
Each teacher is pre-registered with their elective groups:
```python
for group_key, group in elective_groups.items():
    year, basket_id = group_key
    for teacher_id in group.teachers:
        state.register_teacher_elective_group(teacher_id, year, basket_id)
```

### Step 3: Independent Scheduling
Each group is scheduled independently:

1. For each group `(year, basket_id)`:
   - Find slots where ALL group classes are free
   - Check slot is not reserved by OTHER groups
   - Use per-group teacher eligibility
   - Reserve the slot for THIS group
   - Schedule allocations

### Step 4: No Interference
Different groups get different slots:
```python
if state.is_slot_reserved_for_other_group(day, slot, year, basket_id):
    continue  # Skip - slot belongs to another group
```

## Scheduling Rules

### Theory Electives
- Each group needs its own time slot(s)
- All classes in a group are scheduled at the SAME slot
- Uses `is_teacher_eligible_for_elective_group()` for teacher checks
- Uses `reserve_elective_slot_for_group()` for slot reservation

### Lab Electives
- Each group needs its own lab block(s) (2 consecutive periods)
- Both periods are checked/reserved for the group
- Same eligibility and reservation logic as theory

## Safety Guarantees

✅ **No data modification**: Only allocations are created; source data is untouched  
✅ **No group collision**: Different groups cannot share the same slot  
✅ **No teacher conflict**: Teachers are locked per-group for their assigned slots  
✅ **Backward compatible**: Existing single-group elective logic continues to work  
✅ **Independent scheduling**: Each group is processed separately  

## Example Scenario

Given:
- Elective-1 (basket 1): AI, ML - Teachers: Prof. A, Prof. B
- Elective-2 (basket 2): Cloud, IoT - Teachers: Prof. C, Prof. D
- Elective-3 (basket 3): Security, Networks - Teachers: Prof. E, Prof. F

Generated Schedule:
```
Elective-1: Mon Period 2 - All classes
Elective-2: Wed Period 3 - All classes (different slot)
Elective-3: Fri Period 1 - All classes (different slot)
```

Each group's teachers are locked ONLY during their group's slot:
- Prof. A, B locked for Mon P2 only
- Prof. C, D locked for Wed P3 only
- Prof. E, F locked for Fri P1 only

## Testing

Run the multi-elective group test:
```bash
python test_multi_elective_groups.py
```

This verifies:
1. Elective groups are detected correctly
2. Slots are allocated per group
3. No conflicts exist between groups
