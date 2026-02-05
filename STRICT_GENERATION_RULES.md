# READ-ONLY Timetable Generation Engine

## ⚠️ CRITICAL SAFETY RULE

**The generator does NOT modify any existing data:**
- ❌ Does NOT delete/recreate teachers
- ❌ Does NOT modify subjects
- ❌ Does NOT change class assignments
- ❌ Does NOT auto-assign teachers
- ✅ ONLY reads existing mappings
- ✅ ONLY creates new Allocation records

---

## Data Flow

```
┌────────────────────────────────────────────────────────────┐
│                    EXISTING DATA (READ-ONLY)                │
├────────────────────────────────────────────────────────────┤
│  ClassSubjectTeacher: teacher ↔ class ↔ subject mapping   │
│  teacher_subjects: teacher ↔ subject specializations       │
│  semester.subjects: class ↔ subject assignments            │
│  subject.is_elective: elective detection                   │
│  subject.elective_basket_id: elective grouping             │
└─────────────────────────┬──────────────────────────────────┘
                          │ READ
                          ▼
┌────────────────────────────────────────────────────────────┐
│              IN-MEMORY GENERATION STATE                     │
├────────────────────────────────────────────────────────────┤
│  teacher_assignment_map: (class, subject, type) → teacher  │
│  elective_teacher_locks: (day, slot) → Set[teachers]       │
│  allocations: List of scheduled slots                       │
└─────────────────────────┬──────────────────────────────────┘
                          │ WRITE (new records only)
                          ▼
┌────────────────────────────────────────────────────────────┐
│                    Allocation TABLE                         │
│                   (NEW RECORDS ONLY)                        │
└────────────────────────────────────────────────────────────┘
```

---

## Generation Steps

| Step | Action | Data Safety |
|------|--------|-------------|
| 1 | Read semesters, teachers, subjects, rooms | ✅ READ-ONLY |
| 2 | Read teacher↔class↔subject mappings | ✅ READ-ONLY |
| 3 | Detect elective groups by year | ✅ READ-ONLY |
| 4 | Schedule electives (lock teachers in-memory) | ✅ TEMP LOCKS |
| 5 | Schedule labs | ✅ IN-MEMORY |
| 6 | Schedule theory/tutorials | ✅ IN-MEMORY |
| 7 | Save allocations | ✅ NEW RECORDS ONLY |

---

## Teacher Assignment Rules

### Source Priority
1. **ClassSubjectTeacher table** (admin-entered, highest priority)
2. **teacher_subjects relationship** (fallback if no ClassSubjectTeacher)

### NO Auto-Assignment
```python
# If no mapping exists, subject is SKIPPED
if teacher_id is None:
    print(f"[NO MAPPING] {subject.code} - skipped")
    continue  # Do not guess or infer
```

### NO Teacher Rotation
```python
# Use the FIRST teacher found, never rotate
teacher_id = teachers_for_subject[0]  # Deterministic
```

---

## Elective Handling

### Detection (READ-ONLY)
```python
is_elective = (
    subject.is_elective or 
    subject.subject_type == SubjectType.ELECTIVE or
    subject.elective_basket_id is not None
)
```

### Grouping by Year
```python
ELECTIVE_GROUP[year] = {
    subjects: [subject_ids],
    teachers: {teacher_ids},
    classes: [semester_ids]
}
```

### Temporary Time Locks
```python
# Lock is IN-MEMORY only, never saved to database
state.lock_elective_teachers_temporarily(day, slot, elective_teachers)
```

### Teacher Protection
During elective slot:
- ✅ Elective teachers are BUSY
- ✅ Cannot be used by other subjects
- ✅ Cannot be used by other years
- ✅ Lock is temporary (cleared after generation)

---

## Free Period Handling

```python
# If no eligible teacher exists for a slot
if not filled:
    # Mark as FREE in generation output
    free_periods += 1
    # DO NOT modify subject hours
    # DO NOT modify teacher data
```

---

## Guarantees

| Guarantee | How |
|-----------|-----|
| Existing data unchanged | Only READS from DB, no UPDATE/DELETE on source tables |
| Teachers never in wrong class | Uses ONLY existing teacher↔class↔subject mappings |
| Elective isolation | Temporary in-memory locks during generation |
| Elective synchronization | All electives of same year scheduled together |
| Never fails | Returns partial timetable with FREE periods |

---

## Console Output Example

```
============================================================
READ-ONLY TIMETABLE GENERATION ENGINE
============================================================
⚠️ DATA SAFETY: Existing data will NOT be modified

[STEP 1] READING EXISTING DATA...
   READ: 4 classes, 10 teachers, 15 subjects, 5 rooms

[STEP 2] READING TEACHER ASSIGNMENTS...
   READ: Class 1, Subject 3, theory → Teacher 5
   READ: Class 1, Subject 4, lab → Teacher 2
   READ: 12 teacher↔class↔subject mappings

[STEP 3] DETECTING ELECTIVE GROUPS...
   Year 3: 2 electives, 2 teachers, 2 classes

[STEP 4] SCHEDULING ELECTIVES (with temporary teacher locks)...
   Year 3: Scheduling 3 elective hours
   Scheduled 6 elective theory slots

[STEP 5] SCHEDULING REGULAR LABS...
   Scheduled 8 regular lab slots

[STEP 6] SCHEDULING THEORY & TUTORIALS...
      CSE 3rd Sem A...
         → 25 subjects + 3 FREE
      CSE 3rd Sem B...
         → 28 subjects

[STEP 7] SAVING ALLOCATIONS (source data unchanged)...
   ✔ Saved 140 allocations

============================================================
GENERATION COMPLETE - EXISTING DATA UNCHANGED
============================================================
```

---

## Testing

1. **Run project:**
   ```bash
   python run_project.py
   ```

2. **Verify data safety:**
   - Check ClassSubjectTeacher table before/after generation
   - Check teacher_subjects table before/after generation
   - Only Allocation table should have new records

3. **Test elective isolation:**
   - Schedule electives for Year 3
   - Verify Year 3 elective teachers don't appear in other classes during elective time
