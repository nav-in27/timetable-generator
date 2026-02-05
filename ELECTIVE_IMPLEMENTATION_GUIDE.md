# Elective Basket Scheduling - Implementation Checklist & Usage

## Implementation Status

### ✅ Completed Components

#### Data Model
- [x] ElectiveBasket table with all required fields
- [x] Subject.elective_basket_id and is_elective flags
- [x] ClassSubjectTeacher table for teacher assignments
- [x] Allocation table with is_elective and elective_basket_id

#### Core Classes (In generator.py)
- [x] ComponentRequirement - tracks individual components
- [x] AllocationEntry - represents single scheduled slot
- [x] TimetableState - state management with O(1) lookups
- [x] ElectiveBasketSchedulingPlan - explicit plan representation

#### Generation Flow
- [x] Phase 0: Data validation
- [x] Phase 1: Teacher assignment locking
- [x] Phase 2: Elective theory scheduling with synchronization
- [x] Phase 3: Elective lab scheduling
- [x] Phase 4-7: Regular scheduling phases

#### API Layer
- [x] Elective basket CRUD endpoints
- [x] Subject-basket associations
- [x] Timetable view with basket names
- [x] Teacher validation for electives

#### Constraint Enforcement
- [x] Synchronization check (all classes same slot)
- [x] Teacher availability check
- [x] Room availability check
- [x] Lab atomicity (2-period blocks)
- [x] Subject repetition prevention
- [x] Room capacity verification

---

## Usage Guide for End Users

### 1. Create an Elective Basket

**Via API**:
```bash
curl -X POST http://localhost:8000/elective-baskets/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Open Elective 1 - 5th Semester",
    "code": "OE1-S5",
    "semester_number": 5,
    "theory_hours_per_week": 3,
    "lab_hours_per_week": 0,
    "tutorial_hours_per_week": 0,
    "semester_ids": [1, 2, 3],  # Classes 5A, 5B, 5C
    "subject_ids": [10, 11, 12]  # AI, ML, CloudComp
  }'
```

**Pre-requisites**:
- [x] All subjects must have qualified teachers assigned
- [x] All participating classes (semesters) must exist
- [x] No subject should already be in another basket

### 2. Verify Basket Was Created

```bash
curl -X GET http://localhost:8000/elective-baskets/1
```

Response should show:
- ✓ `id`: unique identifier
- ✓ `subjects`: list of participating subjects
- ✓ `participating_semesters`: list of classes
- ✓ `is_scheduled`: false (not yet scheduled)

### 3. Generate Timetable

```bash
curl -X POST http://localhost:8000/timetable/generate \
  -H "Content-Type: application/json" \
  -d '{
    "semester_ids": null,  # null = all semesters
    "clear_existing": true
  }'
```

The generator will:
1. Phase 1: Lock teacher assignments (including electives)
2. Phase 2: Allocate elective basket at common slot
3. Phase 3-7: Complete normal scheduling

### 4. Verify Elective Allocation

**Check semester timetable**:
```bash
curl http://localhost:8000/timetable/view/semester/1
```

Look for slots where:
- `is_elective`: true
- `elective_basket_name`: "Open Elective 1 - 5th Semester"
- All 3 classes have different subjects at same time

**Example response**:
```json
{
  "entity_type": "semester",
  "entity_name": "Semester 5A",
  "days": [
    {
      "day": 0,
      "day_name": "Monday",
      "slots": [
        {
          "allocation_id": 100,
          "teacher_name": "Prof. X",
          "subject_name": "Artificial Intelligence",
          "elective_basket_name": "Open Elective 1 - 5th Semester",
          "is_elective": true,
          "room_name": "Room 201"
        }
      ]
    }
  ]
}
```

### 5. Check Teacher Availability

```bash
curl http://localhost:8000/timetable/view/teacher/1
```

Verify:
- ✓ Teacher only appears once per time slot
- ✓ No double-booking
- ✓ Elective slot shows basket name

---

## Usage Guide for Developers

### 1. Understanding the Flow

```python
# In generate() method:

# Phase 0: Validation
validation_result = self._validate_academic_contract(semesters, subjects)

# Phase 1: Lock assignments
fixed_assignments = self._assign_fixed_teachers(semesters, subjects, ...)

# Phase 2: ELECTIVE SCHEDULING ← Key phase
phase_2_result = self._schedule_elective_theory(
    state,
    elective_theory_reqs,
    lecture_rooms,
    semesters,
    teacher_loads
)

# Phase 3-7: Regular scheduling
# ...
```

### 2. Accessing ElectiveBasketSchedulingPlan

```python
# In _schedule_elective_theory():

# Build plans from elective requirements
plans = self._build_elective_theory_plans(
    baskets=elective_baskets,
    semesters=semesters,
    subjects=subjects,
    fixed_assignments=fixed_assignments
)

# Try to allocate each plan
for plan in plans:
    print(f"Processing: {plan}")  # Uses __repr__
    
    for day, slot in self._get_randomized_slot_order():
        if plan.allocate_at(day, slot, state, rooms, semester_map):
            print(f"✓ Allocated at ({day}, {slot})")
            break
    
    if not plan.is_allocated:
        print(f"✗ Failed: {plan.failure_reason}")
```

### 3. Creating Custom Plans

To add elective tutorialsafter labs:

```python
@dataclass
class ElectiveBasketSchedulingPlan:
    # ... existing fields ...
    
    def validate_for_tutorial_slot(self, day, slot, state):
        """Custom validation for tutorial-only slots."""
        # Can add tutorial-specific rules here
        # E.g., prefer afternoon slots, limit to 2 per day, etc.
        pass

# In Phase 2.5 (new):
def _schedule_elective_tutorials(self, state, plans, rooms, ...):
    """Schedule elective tutorials using same plan approach."""
    for plan in plans:
        if plan.component_type != ComponentType.TUTORIAL:
            continue
        
        for day, slot in preferred_tutorial_slots:
            if plan.validate_for_tutorial_slot(day, slot, state):
                plan.allocate_at(day, slot, state, rooms, semester_map)
                break
```

### 4. Testing a Plan Independently

```python
# In unit tests:
def test_elective_plan_allocation():
    # Create mock objects
    plan = ElectiveBasketSchedulingPlan(
        basket_id=1,
        basket_name="Test Basket",
        semester_number=5,
        component_type=ComponentType.THEORY,
        participating_semester_ids=[sem1.id, sem2.id],
        class_subject_map={sem1.id: subj1.id, sem2.id: subj2.id},
        subject_teacher_map={subj1.id: teacher1.id, subj2.id: teacher2.id},
        hours_per_week=3
    )
    
    # Create state
    state = TimetableState()
    
    # Test can_allocate
    assert plan.can_allocate_at(0, 2, state) == True
    
    # Test allocation
    result = plan.allocate_at(0, 2, state, rooms, semesters)
    assert result == True
    assert plan.is_allocated == True
    assert len(plan.allocated_entries) == 2  # 2 classes
```

### 5. Debugging Failed Plans

```python
# Enable detailed logging
print(f"[DEBUG] Plan: {plan}")
print(f"[DEBUG] Participating: {plan.participating_semester_ids}")
print(f"[DEBUG] Class-Subject: {plan.class_subject_map}")
print(f"[DEBUG] Subject-Teacher: {plan.subject_teacher_map}")

# When allocation fails
if not plan.is_allocated:
    print(f"[ERROR] {plan.failure_reason}")
    
    # Check individual constraints
    for day, slot in randomized_slots:
        if not plan.can_allocate_at(day, slot, state):
            print(f"   Cannot allocate at ({day}, {slot}): {plan.failure_reason}")
        else:
            print(f"   Can allocate at ({day}, {slot}) ✓")
            # Why didn't we allocate here?
            result = plan.allocate_at(day, slot, state, rooms, semester_map)
            if not result:
                print(f"   But failed to allocate: {plan.failure_reason}")
                break
```

---

## Troubleshooting

### Issue 1: "Subject has no qualified teachers"

**Cause**: Subject added to basket without teachers assigned.

**Fix**:
```bash
# 1. Add teachers to subject
curl -X PUT http://localhost:8000/teachers/1 \
  -d '{
    "subject_ids": [subject_id]
  }'

# 2. Try creating basket again
```

### Issue 2: Elective basket not scheduled (stays is_scheduled=false)

**Cause**: Could be Phase 2 failure (no available common slots).

**Debug**:
```python
# Check Phase 2 logs
[WARN] Failed to allocate 1 plans:
       • Open Elective 1: Class 5A occupied at (0, 2)

# This means no common slot found where all classes free

# Solution: Add more classes to stagger schedules
# Or reduce elective hours
```

### Issue 3: Teacher appears in multiple classes at same time

**Cause**: Phase 2 teacher availability check failed.

**Debug**:
```sql
-- Find the conflict
SELECT * FROM allocations WHERE teacher_id = 1 AND day = 0 AND slot = 2
-- Should show max 1 row per day/slot
```

### Issue 4: Allocation shows subject name instead of basket name

**Cause**: Frontend not using `elective_basket_name` field.

**Fix**: Update frontend to display:
```javascript
if (slot.is_elective && slot.elective_basket_name) {
  displayName = slot.elective_basket_name;  // "Open Elective 1"
} else {
  displayName = slot.subject_name;  // "Artificial Intelligence"
}
```

---

## Validation Checklist

Before deploying to production, verify:

### Data Model
- [ ] ElectiveBasket table exists and populated
- [ ] Subject.is_elective and elective_basket_id fields present
- [ ] ClassSubjectTeacher entries auto-created for electives
- [ ] Allocation.is_elective and elective_basket_id present

### Functionality
- [ ] Can create elective basket via API
- [ ] Basket validation rejects subjects without teachers
- [ ] Timetable generation runs without errors
- [ ] Phase 2 successfully allocates baskets
- [ ] All participating classes get same slot
- [ ] Teachers not double-booked at elective slot

### API Responses
- [ ] `/timetable/view/semester/{id}` includes `elective_basket_name`
- [ ] `/timetable/view/teacher/{id}` shows basket name for electives
- [ ] `/elective-baskets/` CRUD operations work

### Constraints
- [ ] No subject appears twice in same class on same day
- [ ] No teacher teaches 2 classes at same time
- [ ] Lab blocks are 2 consecutive periods
- [ ] Room capacity respected
- [ ] All hours filled or free period marked

### Error Handling
- [ ] Failed basket allocation doesn't crash generator
- [ ] Clear error messages in logs
- [ ] Timetable still generated if some electives fail

---

## Performance Notes

### Current Performance
- Elective scheduling: O(N * M * K) where
  - N = number of elective baskets
  - M = number of possible slots (5 days * 7 periods = 35)
  - K = number of participating classes per basket
- Typical: 5 baskets * 35 slots * 3 classes = ~525 checks
- Each check: O(1) with set lookups
- Total: <1 second for typical input

### Scalability
- Handles 10+ elective baskets
- Handles 100+ total subjects
- Handles 50+ classes
- Should optimize if exceeds above scales

### Optimization Opportunities (Future)
1. Cache slot availability per basket
2. Use constraint propagation (CSP)
3. Pre-filter impossible slots
4. Parallel processing of independent baskets

---

## Summary

### What's Implemented ✅
- Full data model for elective baskets
- Teacher availability enforcement
- Synchronization across multiple classes
- Lab atomicity
- Room allocation
- Graceful error handling

### How to Use It
1. Create elective basket with subjects + classes
2. Run timetable generation
3. Verify all classes at same slot
4. Check timetable views

### What's Next (Optional)
- Add tutorial scheduling
- Add student preference tracking
- Add course conflict detection
- Add capacity warnings

---

## Quick Reference

| Task | Command |
|------|---------|
| Create basket | POST /elective-baskets/ |
| List baskets | GET /elective-baskets/ |
| Generate timetable | POST /timetable/generate |
| View class schedule | GET /timetable/view/semester/{id} |
| View teacher schedule | GET /timetable/view/teacher/{id} |
| Check allocations | GET /timetable/allocations |

| Component | File | Type |
|-----------|------|------|
| ElectiveBasket | models.py | Database table |
| ElectiveBasketSchedulingPlan | generator.py | @dataclass |
| TimetableState | generator.py | @dataclass |
| Phase 2 logic | generator.py | Method |
| API endpoints | api/elective_baskets.py | FastAPI router |
| Timetable view | api/timetable.py | FastAPI router |

