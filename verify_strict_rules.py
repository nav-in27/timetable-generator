"""
Verify Strict Generation Rules:
1. Teacher Assignment Locking - Teachers only appear in assigned classes
2. Elective Lab Allocation - Elective labs are scheduled (not free periods)
3. Elective Synchronization - Same time across all sections of a year
"""
import sys
import os

# Change to root directory for correct DB path
os.chdir(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, 'backend')

from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.db.models import (
    Allocation, ClassSubjectTeacher, Subject, Semester, Teacher,
    SubjectType, ComponentType
)
from collections import defaultdict

# Ensure tables exist
Base.metadata.create_all(bind=engine)

def verify_strict_rules():
    db = SessionLocal()
    
    print("=" * 70)
    print("STRICT GENERATION RULES VERIFICATION")
    print("=" * 70)
    
    # 1. Build Teacher Assignment Map
    print("\n[RULE 1] TEACHER ASSIGNMENT LOCKING")
    print("-" * 50)
    
    cst_entries = db.query(ClassSubjectTeacher).all()
    teacher_map = {}
    for cst in cst_entries:
        key = (cst.semester_id, cst.subject_id, cst.component_type.value)
        teacher_map[key] = cst.teacher_id
    
    print(f"Loaded {len(teacher_map)} teacher-class-subject mappings")
    
    # 2. Check all allocations
    allocations = db.query(Allocation).all()
    print(f"Total allocations to verify: {len(allocations)}")
    
    violations = []
    for alloc in allocations:
        comp_type = alloc.component_type.value if alloc.component_type else 'theory'
        key = (alloc.semester_id, alloc.subject_id, comp_type)
        
        expected_teacher = teacher_map.get(key)
        if expected_teacher and alloc.teacher_id != expected_teacher:
            violations.append({
                'semester_id': alloc.semester_id,
                'subject_id': alloc.subject_id,
                'expected': expected_teacher,
                'actual': alloc.teacher_id,
                'day': alloc.day,
                'slot': alloc.slot
            })
    
    if violations:
        print(f"❌ FAILED: {len(violations)} teacher assignment violations found!")
        for v in violations[:5]:
            print(f"   Semester {v['semester_id']}, Subject {v['subject_id']}: "
                  f"Expected Teacher {v['expected']}, Got {v['actual']}")
    else:
        print("✅ PASSED: All allocations use correct assigned teachers")
    
    # 3. Check Elective Lab Allocation
    print("\n[RULE 2] ELECTIVE LAB ALLOCATION")
    print("-" * 50)
    
    # Find elective subjects with lab hours
    elective_subjects = db.query(Subject).filter(
        (Subject.is_elective == True) | 
        (Subject.subject_type == SubjectType.ELECTIVE)
    ).all()
    
    elective_ids = [s.id for s in elective_subjects]
    print(f"Found {len(elective_subjects)} elective subjects")
    
    # Check if elective labs exist
    elective_lab_allocs = db.query(Allocation).filter(
        Allocation.subject_id.in_(elective_ids),
        Allocation.component_type == ComponentType.LAB
    ).all()
    
    print(f"Elective lab allocations: {len(elective_lab_allocs)}")
    
    # Check for electives with lab hours but no allocations
    missing_elective_labs = []
    for subj in elective_subjects:
        if subj.lab_hours_per_week > 0:
            labs_for_subj = [a for a in elective_lab_allocs if a.subject_id == subj.id]
            if not labs_for_subj:
                missing_elective_labs.append(subj)
    
    if missing_elective_labs:
        print(f"⚠️ WARNING: {len(missing_elective_labs)} elective subjects with lab hours have no lab allocations:")
        for s in missing_elective_labs[:3]:
            print(f"   {s.code} - {s.name} (lab_hours={s.lab_hours_per_week})")
    else:
        print("✅ PASSED: All elective subjects with lab hours have lab allocations")
    
    # 4. Check Elective Synchronization
    print("\n[RULE 3] ELECTIVE TIME SYNCHRONIZATION")
    print("-" * 50)
    
    elective_allocs = db.query(Allocation).filter(
        Allocation.is_elective == True
    ).all()
    
    print(f"Total elective allocations: {len(elective_allocs)}")
    
    # Group by semester_number -> (day, slot) -> list of semester_ids
    semesters = {s.id: s for s in db.query(Semester).all()}
    
    elective_slots_by_year = defaultdict(lambda: defaultdict(set))
    for alloc in elective_allocs:
        sem = semesters.get(alloc.semester_id)
        if sem:
            year = sem.semester_number
            slot_key = (alloc.day, alloc.slot)
            elective_slots_by_year[year][slot_key].add(alloc.semester_id)
    
    # Check if all sections of a year have elective at same slots
    sync_issues = []
    for year, slots in elective_slots_by_year.items():
        year_sems = [s.id for s in semesters.values() if s.semester_number == year]
        
        for slot_key, sems_with_elective in slots.items():
            missing = set(year_sems) - sems_with_elective
            if missing and len(sems_with_elective) > 0:
                sync_issues.append({
                    'year': year,
                    'slot': slot_key,
                    'have': list(sems_with_elective),
                    'missing': list(missing)
                })
    
    if sync_issues:
        print(f"⚠️ WARNING: {len(sync_issues)} elective sync issues:")
        for issue in sync_issues[:3]:
            print(f"   Year {issue['year']}, Slot {issue['slot']}: "
                  f"Have={issue['have']}, Missing={issue['missing']}")
    else:
        print("✅ PASSED: All electives are synchronized across sections")
    
    # 5. Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    
    total_issues = len(violations) + len(missing_elective_labs) + len(sync_issues)
    
    if total_issues == 0:
        print("🎉 ALL STRICT RULES VERIFIED SUCCESSFULLY!")
    else:
        print(f"⚠️ Found {total_issues} potential issues to review")
    
    print(f"\nStats:")
    print(f"  - Total Allocations: {len(allocations)}")
    print(f"  - Teacher Violations: {len(violations)}")
    print(f"  - Missing Elective Labs: {len(missing_elective_labs)}")
    print(f"  - Elective Sync Issues: {len(sync_issues)}")
    
    db.close()

if __name__ == "__main__":
    verify_strict_rules()
