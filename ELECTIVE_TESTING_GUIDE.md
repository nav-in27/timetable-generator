# Elective Basket Fixes - Testing Guide

## Overview
This guide helps verify that the two main elective basket issues are fixed:
1. ✅ Timetable displays elective basket name instead of individual subject name
2. ✅ Teachers assigned to electives are checked for availability during elective slots

## Quick Test Using API

### Test 1: Check Elective Subject Name Display

#### Prerequisites:
- Backend running on `http://localhost:8000`
- At least one elective basket created with subjects
- Timetable generated

#### Steps:

**1. Get Semester Timetable:**
```bash
curl -X GET "http://localhost:8000/timetable/view/semester/1"
```

**2. Check Response:**
Look for allocations with `is_elective=true`:
```json
{
  "entity_type": "semester",
  "entity_id": 1,
  "entity_name": "Semester 1",
  "days": [
    {
      "day": 0,
      "day_name": "Monday",
      "slots": [
        {
          "allocation_id": 123,
          "teacher_name": "Prof. Smith",
          "subject_name": "Artificial Intelligence",
          "subject_code": "CS301",
          "elective_basket_id": 5,
          "elective_basket_name": "Open Elective 1 - 5th Semester",
          "is_elective": true,
          "room_name": "Room 201"
        }
      ]
    }
  ]
}
```

**3. Verify:**
- ✅ `elective_basket_id` is present and not null
- ✅ `elective_basket_name` shows the basket name, not the subject name
- ✅ `subject_name` shows the actual subject (for reference)
- ✅ `is_elective` is `true`

---

### Test 2: Check Teacher Availability Validation

#### Prerequisites:
- Backend running
- Some teachers and subjects set up

#### Step 1: Create Subject Without Teachers
```bash
curl -X POST "http://localhost:8000/subjects/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Subject",
    "code": "TEST101",
    "theory_hours_per_week": 3,
    "lab_hours_per_week": 0,
    "tutorial_hours_per_week": 0,
    "is_elective": false,
    "semester_ids": [1]
  }'
```

#### Step 2: Try to Add to Elective Basket (Should Fail)
```bash
curl -X POST "http://localhost:8000/elective-baskets/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Elective Test",
    "code": "ELEC_TEST",
    "semester_number": 3,
    "theory_hours_per_week": 3,
    "lab_hours_per_week": 0,
    "tutorial_hours_per_week": 0,
    "semester_ids": [1],
    "subject_ids": [<TEST_SUBJECT_ID>]
  }'
```

**Expected Result:**
```json
{
  "detail": "Subject 'Test Subject' has no qualified teachers assigned. Please assign teachers before adding to elective basket."
}
```

#### Step 3: Assign Teachers to Subject
```bash
curl -X PUT "http://localhost:8000/teachers/{teacher_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_ids": [<TEST_SUBJECT_ID>]
  }'
```

#### Step 4: Try Again (Should Succeed)
Repeat Step 2, should now succeed and create the basket.

---

### Test 3: Verify ClassSubjectTeacher Entries Created

After creating an elective basket with subjects:

```bash
# Query the database directly or via API
# Check that ClassSubjectTeacher entries were created

# In Python/SQLAlchemy (pseudocode):
# SELECT * FROM class_subject_teacher 
# WHERE subject_id IN (subjects_of_basket)
# AND semester_id IN (semesters_of_basket)
```

The system should have created entries with:
- `assignment_reason = "auto_assigned_for_elective_basket"`
- All components that have hours (THEORY, LAB, TUTORIAL)
- All teachers assigned to the subject
- All participating semesters

---

### Test 4: Full Workflow Test

#### Step 1: Create Elective Basket with Multiple Subjects
```
UI Actions:
1. Go to Electives Management
2. Click "New Elective Basket"
3. Enter Name: "Open Elective 1"
4. Enter Code: "OE1"
5. Enter Semester: 5
6. Enter Hours: Theory=3, Lab=2, Tutorial=0
7. Select Semesters: (Select 5th semester classes)
8. Select Subjects: AI, ML, Cloud Computing
9. Click Save
```

**Verify:**
- System accepts the basket
- System creates teacher assignments automatically
- No error messages about missing teachers

#### Step 2: Generate Timetable
```
UI Actions:
1. Go to Generate Timetable
2. Select all semesters (or just 5th semester)
3. Click Generate
4. Wait for completion
```

**Verify:**
- Generation completes successfully
- No errors about teacher conflicts
- Timetable shows allocations

#### Step 3: View Timetable
```
UI Actions:
1. Go to Timetable View
2. Select 5th Semester
3. View the week
```

**Verify:**
- For elective slots, see all 3 subjects (AI, ML, Cloud) scheduled at the same time
- ✅ Display shows "Open Elective 1" name (from basket)
- ✅ All 3 subjects are scheduled in different rooms (or same room if capacity allows)
- ✅ Teachers shown are available at that slot

#### Step 4: Check Teacher Timetable
```
UI Actions:
1. Go to Teacher Timetable
2. Select one teacher (who teaches an elective)
3. View their schedule
```

**Verify:**
- Teacher appears at the elective slot
- Teacher is free (no conflicts)
- Shows the subject they're teaching

---

## Expected Behavior Summary

### Elective Basket Display ✅
- Individual subject name: `AI`, `ML`, `Cloud Computing`
- Basket name: `Open Elective 1 - 5th Semester`
- **Display in timetable**: Shows basket name when viewing class/teacher timetable
- **Allocation response**: Includes both `subject_name` and `elective_basket_name`

### Teacher Availability ✅
- System validates teachers before creating basket
- System auto-creates teacher-subject mappings
- Generator checks teacher availability during elective slot
- Electives only scheduled if teachers are free

---

## Troubleshooting

### Issue: Elective basket name shows as NULL
**Cause**: Allocation not saved with `elective_basket_id`
**Solution**: 
1. Check database: `SELECT * FROM allocations WHERE id = ?`
2. Verify `elective_basket_id` is set
3. Re-run timetable generation

### Issue: "No qualified teachers" error
**Cause**: Subject has no teachers assigned
**Solution**:
1. Go to Teachers page
2. Select a teacher
3. Add the subject to their profile
4. Try creating basket again

### Issue: Teacher shows at same time in multiple classes
**Cause**: Teacher availability check failed during generation
**Solution**:
1. Check `ClassSubjectTeacher` entries were created
2. Re-run timetable generation
3. Check logs for conflicts

---

## Database Inspection

To verify the fixes at DB level:

```sql
-- Check elective baskets
SELECT * FROM elective_baskets;

-- Check elective subjects
SELECT id, name, is_elective, elective_basket_id 
FROM subjects 
WHERE is_elective = true;

-- Check teacher assignments for electives
SELECT cst.*, s.name as subject_name, t.name as teacher_name, sem.name as semester_name
FROM class_subject_teacher cst
JOIN subjects s ON cst.subject_id = s.id
JOIN teachers t ON cst.teacher_id = t.id
JOIN semesters sem ON cst.semester_id = sem.id
WHERE s.is_elective = true
ORDER BY s.elective_basket_id, sem.id;

-- Check allocations
SELECT a.*, s.name as subject_name, t.name as teacher_name, eb.name as basket_name
FROM allocations a
JOIN subjects s ON a.subject_id = s.id
JOIN teachers t ON a.teacher_id = t.id
LEFT JOIN elective_baskets eb ON a.elective_basket_id = eb.id
WHERE a.is_elective = true
ORDER BY a.day, a.slot;
```

---

## Notes for Developers

### How Fixes Work:

1. **Display Fix**:
   - `TimetableSlot` includes both subject and basket info
   - Frontend can choose to display basket name instead of subject name
   - Maintains backward compatibility (both fields available)

2. **Availability Fix**:
   - Elective basket API validates teachers exist
   - Auto-creates `ClassSubjectTeacher` entries
   - Generator's existing teacher availability check works with these entries
   - Phase 2 & 3 of generator check teacher availability before scheduling

### No Schema Changes:
- All tables already exist
- Using existing `elective_basket_id` field in `Allocation`
- Using existing `ClassSubjectTeacher` for teacher mapping
- No migrations needed

### Backward Compatibility:
- Non-elective allocations still work the same
- Existing queries still work
- Only electives have basket information

