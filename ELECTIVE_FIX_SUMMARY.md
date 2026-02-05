# Elective Basket Assignment Fixes

## Problems Identified

### Problem 1: Incorrect Subject Name Display
**Issue**: When generating timetables with electives, the system was displaying the individual subject name (e.g., "AI", "ML", "Cloud Computing") instead of the elective basket name (e.g., "Open Elective 1 - 5th Semester").

**Root Cause**: The timetable API endpoints were not retrieving or displaying the elective basket information, only the individual subject name.

**Solution Implemented**:
- Updated `AllocationResponse` schema to include `elective_basket_id` field
- Updated `TimetableSlot` schema to include both `elective_basket_id` and `elective_basket_name` fields
- Modified both timetable API endpoints (`/view/semester/{semester_id}` and `/view/teacher/{teacher_id}`) to:
  - Retrieve elective basket information when allocations are electives
  - Display the elective basket name in the UI when applicable
  - Fall back to subject name for non-elective subjects

### Problem 2: Teacher Availability Not Ensured
**Issue**: Teachers assigned to electives were not being properly validated for availability during the elective time slot. The generator might assign a teacher who is already teaching another class during that slot.

**Root Cause**: When elective subjects were added to a basket, the system was not creating the necessary `ClassSubjectTeacher` entries that link teachers to subjects for specific semesters and components. Additionally, the validation logic in the elective basket APIs was not checking for teacher availability.

**Solution Implemented**:

#### 2a. Elective Basket API Enhancements
- **Teacher Validation**: Added validation to ensure all subjects added to an elective basket have qualified teachers assigned
- **ClassSubjectTeacher Synchronization**: When subjects are added to a basket, the system now automatically creates `ClassSubjectTeacher` entries for:
  - All participating semesters
  - All qualified teachers of the subject
  - Only for components that have allocated hours (theory, lab, tutorial)

- **Semester Synchronization**: When semesters are assigned to a basket, the system now:
  - Synchronizes all basket subjects to the new semesters
  - Creates new `ClassSubjectTeacher` entries for any missing (semester, subject, teacher, component) combinations

#### 2b. Generator Teacher Availability Check
The existing generator logic (Phase 1 & 2) already implements:
- `state.is_teacher_free(teacher_id, day, slot)` - Checks if a teacher is free at a specific time slot
- This check is used in elective scheduling to ensure all teachers for electives are free:
  ```python
  # Check if ALL teachers are free
  all_teachers_free = all(
      state.is_teacher_free(r.assigned_teacher_id, day, slot) 
      for r in reqs if r.assigned_teacher_id
  )
  ```

The fix ensures that:
1. `ClassSubjectTeacher` entries are properly created so teachers can be assigned
2. Teachers must be available during the elective slot for the elective to be scheduled
3. Multiple subjects in the same basket can share the same time slot if their teachers are available

## Modified Files

### 1. Backend API Schema (`app/schemas/schemas.py`)
- Added `elective_basket_id: Optional[int]` to `AllocationResponse`
- Added `elective_basket_id: Optional[int]` and `elective_basket_name: Optional[str]` to `TimetableSlot`

### 2. Backend Timetable API (`app/api/timetable.py`)
- Imported `ElectiveBasket` model
- Updated `get_semester_timetable()` endpoint to:
  - Retrieve elective basket name for elective allocations
  - Include basket info in `TimetableSlot` response
- Updated `get_teacher_timetable()` endpoint similarly

### 3. Backend Elective Baskets API (`app/api/elective_baskets.py`)
- Imported `ClassSubjectTeacher` and `ComponentType` models
- Enhanced `create_elective_basket()` to:
  - Validate all subjects have teachers
  - Auto-create `ClassSubjectTeacher` entries for all components
- Enhanced `update_elective_basket()` to:
  - Validate all subjects have teachers when updating
  - Auto-create missing `ClassSubjectTeacher` entries
  - Handle semester updates with proper teacher synchronization

## How It Works Now

### Creating/Updating an Elective Basket:

1. **User selects subjects and semesters** for the elective basket via UI
2. **API validates**:
   - Each subject has at least one qualified teacher
   - Subjects exist and are valid
3. **API automatically creates** `ClassSubjectTeacher` entries:
   - For each (semester, subject, teacher, component) combination
   - Only for components with allocated hours
   - With `assignment_reason = "auto_assigned_for_elective_basket"`

### During Timetable Generation:

1. **Phase 1** (_assign_fixed_teachers):
   - Reads `ClassSubjectTeacher` entries
   - Uses these to determine assigned teachers for each subject/component
   - Validates teacher workload capacity

2. **Phase 2** (Elective Theory Scheduling):
   - Checks if ALL elective subjects have assigned teachers
   - Verifies ALL teachers are free at the proposed slot
   - Only allocates if all conditions are met
   - Creates allocations with `is_elective=True` and `elective_basket_id` set

3. **Phase 3** (Elective Lab Scheduling):
   - Similar validation and scheduling for lab components
   - Ensures atomic 2-period blocks for labs

### During Timetable Display:

1. **Frontend requests** `/timetable/view/semester/{id}`
2. **API returns** allocations with:
   - `subject_name` and `subject_code` from the subject
   - `elective_basket_id` and `elective_basket_name` (if elective)
3. **Frontend displays**:
   - Elective basket name with subject name as subtitle (suggested UI)
   - Or just basket name if preferred
   - Shows in teacher timetable as well

## Testing Recommendations

### Test Case 1: Create Elective Basket with Valid Teachers
1. Create 3 subjects (AI, ML, Cloud Computing)
2. Assign multiple teachers to each subject
3. Create an elective basket with these subjects
4. **Expected**: System accepts and creates teacher assignments

### Test Case 2: Try to Add Subject Without Teachers
1. Create a subject with NO teachers
2. Try to add to elective basket
3. **Expected**: System rejects with error message about missing teachers

### Test Case 3: Generate Timetable and Check Display
1. Create elective basket with 3 subjects
2. Generate timetable
3. View semester timetable via API
4. **Expected**: 
   - Allocation responses include `elective_basket_name`
   - All 3 subjects scheduled at same time slot
   - Different rooms for each subject (or same room if capacity allows)
   - All teachers are free at that slot

### Test Case 4: Teacher Availability Constraint
1. Assign Teacher X to both a regular subject (Mon 10 AM) AND an elective basket
2. Generate timetable
3. **Expected**: 
   - Elective basket NOT scheduled at Mon 10 AM
   - Teacher X should be free at the elective slot

## Database Notes

No schema changes required. The system uses existing tables:
- `Allocation` - already has `elective_basket_id` and `is_elective` fields
- `ClassSubjectTeacher` - already exists for teacher-subject mapping
- `ElectiveBasket` - existing model for basket definitions

## Future Enhancements

1. **UI Improvements**:
   - Show elective basket in subject name with visual indicator
   - Allow direct assignment of teachers to subjects from basket view

2. **Advanced Validation**:
   - Check teacher qualifications for elective subjects
   - Validate teacher availability patterns before basket creation

3. **Reporting**:
   - Generate reports showing elective basket allocations
   - Track elective enrollment vs. capacity

