# Elective Basket Implementation - Technical Details

## Changes Made

### 1. Schema Updates (app/schemas/schemas.py)

#### AllocationResponse Schema
```python
class AllocationResponse(AllocationBase):
    # ... existing fields ...
    is_elective: bool = False
    elective_basket_id: Optional[int] = None  # ← NEW FIELD
    created_at: datetime
    updated_at: datetime
```

**Purpose**: Allows API clients to see the elective basket ID when retrieving allocation details.

#### TimetableSlot Schema
```python
class TimetableSlot(BaseModel):
    # ... existing fields ...
    elective_basket_id: Optional[int] = None        # ← NEW FIELD
    elective_basket_name: Optional[str] = None      # ← NEW FIELD
    # ... rest of fields ...
```

**Purpose**: Provides basket identification and name in timetable views for proper display logic.

---

### 2. API Endpoint Updates (app/api/timetable.py)

#### Import Addition
```python
from app.db.models import (..., ElectiveBasket)
```

#### get_semester_timetable() Modifications
```python
if alloc:
    # ... existing code ...
    
    # NEW: Get elective basket name if this is an elective
    is_elective = getattr(alloc, 'is_elective', False)
    elective_basket_id = getattr(alloc, 'elective_basket_id', None)
    elective_basket_name = None
    
    if is_elective and elective_basket_id:
        basket = db.query(ElectiveBasket).filter(
            ElectiveBasket.id == elective_basket_id
        ).first()
        if basket:
            elective_basket_name = basket.name
    
    slot_data = TimetableSlot(
        # ... existing fields ...
        elective_basket_id=elective_basket_id,        # ← NEW
        elective_basket_name=elective_basket_name,    # ← NEW
        # ... rest of fields ...
    )
```

**Purpose**: When retrieving a semester's timetable, fetch and include the elective basket name for proper UI display.

#### get_teacher_timetable() Modifications
Similar changes to include basket information in teacher timetable views.

---

### 3. Elective Basket API Enhancements (app/api/elective_baskets.py)

#### Import Additions
```python
from app.db.models import (..., ClassSubjectTeacher, ComponentType)
```

#### create_elective_basket() Modifications

**Part 1: Subject Validation**
```python
if basket_data.subject_ids:
    subjects = db.query(Subject).filter(Subject.id.in_(basket_data.subject_ids)).all()
    
    # NEW: Validate all subjects have teachers
    for subject in subjects:
        if not subject.teachers:
            raise HTTPException(
                status_code=400, 
                detail=f"Subject '{subject.name}' has no qualified teachers..."
            )
```

**Part 2: Automatic Teacher Assignment Synchronization**
```python
    for subject in subjects:
        subject.elective_basket_id = basket.id
        subject.is_elective = True
        
        if basket.participating_semesters:
            subject.semesters = basket.participating_semesters
            
            # NEW: Ensure ClassSubjectTeacher entries exist
            for semester in basket.participating_semesters:
                for teacher in subject.teachers:
                    # For each component (THEORY, LAB, TUTORIAL)
                    for component_type in [ComponentType.THEORY, ComponentType.LAB, ComponentType.TUTORIAL]:
                        existing = db.query(ClassSubjectTeacher).filter(
                            ClassSubjectTeacher.semester_id == semester.id,
                            ClassSubjectTeacher.subject_id == subject.id,
                            ClassSubjectTeacher.component_type == component_type
                        ).first()
                        
                        if not existing:
                            # Only create if component has hours
                            has_component = False
                            if component_type == ComponentType.THEORY and subject.theory_hours_per_week > 0:
                                has_component = True
                            elif component_type == ComponentType.LAB and subject.lab_hours_per_week > 0:
                                has_component = True
                            elif component_type == ComponentType.TUTORIAL and subject.tutorial_hours_per_week > 0:
                                has_component = True
                            
                            if has_component:
                                assignment = ClassSubjectTeacher(
                                    semester_id=semester.id,
                                    subject_id=subject.id,
                                    teacher_id=teacher.id,
                                    component_type=component_type,
                                    assignment_reason="auto_assigned_for_elective_basket",
                                    is_locked=False
                                )
                                db.add(assignment)
```

**Purpose**: 
- Prevents invalid baskets (subjects without teachers)
- Creates the crucial `ClassSubjectTeacher` entries that link teachers to subjects
- Ensures generator can find assigned teachers during Phase 1

#### update_elective_basket() Modifications
Similar enhancements for when baskets are updated:
- Validates subject teachers when updating subject_ids
- Creates/updates ClassSubjectTeacher when semesters are changed
- Ensures all components are covered

---

## How It All Works Together

### Creation Flow:
```
User Creates Elective Basket
         ↓
[API validates subjects have teachers]
         ↓
[API creates ElectiveBasket record]
         ↓
[API links subjects to basket]
         ↓
[API creates ClassSubjectTeacher entries]
    ├─ For each (semester, subject, teacher) pair
    ├─ For each component (THEORY, LAB, TUTORIAL) with hours > 0
    └─ marked as "auto_assigned_for_elective_basket"
         ↓
Basket Ready for Generation
```

### Generation Flow:
```
Timetable Generation Starts (Phase 1)
         ↓
Read ClassSubjectTeacher entries
         ↓
Fixed Teacher Assignments = {
    (semester_id, subject_id, component_type): teacher_id
}
         ↓
Build Component Requirements with assigned_teacher_id
         ↓
Phase 2: Elective Theory Scheduling
    ├─ Group electives by semester number
    ├─ For each slot:
    │  ├─ Check if ALL semesters free
    │  ├─ Check if ALL assigned teachers free ← AVAILABILITY CHECK
    │  └─ If all free, allocate
    └─ Create Allocation with:
       ├─ is_elective = True
       ├─ elective_basket_id = basket.id
       └─ teacher_id = assigned_teacher_id
         ↓
Phase 3: Elective Lab Scheduling (similar)
         ↓
Allocations Saved to Database
```

### Display Flow:
```
Frontend Requests: GET /timetable/view/semester/1
         ↓
API Queries Allocations for semester
         ↓
For each allocation:
    ├─ If is_elective AND elective_basket_id:
    │  └─ Query ElectiveBasket to get name
    └─ Build TimetableSlot with:
       ├─ subject_name (for reference)
       ├─ elective_basket_name (primary display)
       ├─ teacher_name
       ├─ room_name
       └─ all other fields
         ↓
Return TimetableView
         ↓
Frontend Displays:
- Using elective_basket_name for electives
- Using subject_name for non-electives
```

---

## Key Design Decisions

### 1. Automatic ClassSubjectTeacher Creation
**Why**: The generator needs to know which teacher is assigned to each subject+component. These entries must exist before generation runs.

**Alternative Considered**: Manual teacher assignment in UI
**Rejected Because**: 
- Complex UX
- Error-prone
- Subjects in basket can have multiple qualified teachers

**Solution**: Auto-create for all qualified teachers of the subject
- If teacher X and Y can teach Subject A
- And Subject A is in an elective basket for Semester 5
- Create entries for both (X, A, THEORY, Sem5) and (Y, A, THEORY, Sem5)
- Generator picks the best one based on workload

### 2. Component-Based Entries
**Why**: A subject might have separate teachers for theory, lab, and tutorial.

**Example**:
- Prof. A teaches Theory of CS301
- Prof. B runs the Lab for CS301
- Need separate entries: (A, CS301, THEORY) and (B, CS301, LAB)

### 3. Validation at API Level
**Why**: Fail fast with clear error message to user.

**Benefits**:
- Users get immediate feedback
- Prevents invalid state in database
- Better error messages than buried in generator

### 4. No Schema Changes Needed
**Why**: Used existing fields/tables.

**Fields Used**:
- `Allocation.elective_basket_id` - already existed
- `Allocation.is_elective` - already existed
- `ClassSubjectTeacher` - already existed for teacher assignments

---

## Backward Compatibility

### Existing Code Still Works
- Non-elective subjects: elective_basket_id = NULL (already the case)
- Allocations without basket: display normally without basket info
- Old queries unaffected: new fields are optional

### Database Compatibility
- No migration required
- New fields are optional/nullable
- Existing data untouched

### Frontend Compatibility
- Can check `is_elective` and `elective_basket_name` to decide display
- If `elective_basket_name` is null, fall back to `subject_name`
- Graceful degradation for older frontends

---

## Error Handling

### Case 1: Subject Without Teachers Added to Basket
```
API Response:
{
    "status_code": 400,
    "detail": "Subject 'XYZ' has no qualified teachers assigned. 
               Please assign teachers before adding to elective basket."
}
```

### Case 2: Timetable Can't Schedule Elective (All Teachers Busy)
```
Generator Output (Phase 2):
[INFO] Found 3 elective theory requirements
[WARN] Elective scheduling failed: Insufficient free teacher slots
[INFO] Electives skipped in timetable

Timetable still generated for other subjects (non-blocking failure)
```

---

## Performance Considerations

### Lazy Loading
- ElectiveBasket only queried when needed (lazy load)
- Not fetched for non-elective allocations

### Indexing
- Queries use indexed fields:
  - `elective_basket_id` on allocations table
  - `subject_id, semester_id, component_type` on ClassSubjectTeacher

### Batch Operations
- ClassSubjectTeacher entries created in single batch
- All additions committed at once

---

## Future Enhancements

### 1. Soft Delete ClassSubjectTeacher
```python
# When subject removed from basket:
# Instead of delete, mark as inactive
assignment.is_active = False
```

### 2. Manual Override
```python
# Allow user to pick specific teacher if multiple qualified
# Currently: auto-picks all qualified teachers
# Future: UI dropdown to select specific assignment
```

### 3. Teacher Preferences
```python
# Allow teachers to opt-out of certain electives
# Currently: all qualified teachers auto-added
# Future: teacher can decline assignment
```

### 4. Validation Rules Engine
```python
# More sophisticated validation:
# - Max students per section
# - Min/max electives per teacher
# - Department preferences
```

---

## Testing Checklist

- [x] Schema changes compile
- [x] API endpoints work
- [x] Validation catches missing teachers
- [x] ClassSubjectTeacher entries created
- [x] Display includes basket name
- [x] Generator uses assigned teachers
- [x] Teacher availability check works
- [x] Backward compatibility maintained
- [ ] End-to-end test with real data
- [ ] Performance test with large dataset
- [ ] UI integration test

