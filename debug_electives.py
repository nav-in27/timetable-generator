"""
Debug script to check elective subjects and their scheduling.
"""
import sys
import os
sys.path.insert(0, 'backend')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from app.db.session import get_db
from app.db.models import Subject, Semester, Teacher, ElectiveBasket, teacher_subjects

def main():
    db = next(get_db())
    
    print("="*60)
    print("ELECTIVE DEBUGGING REPORT")
    print("="*60)
    
    # 1. Check all semesters/classes
    print("\n[1] SEMESTERS/CLASSES:")
    semesters = db.query(Semester).all()
    semester_by_number = {}
    for sem in semesters:
        print(f"   ID={sem.id}: {sem.name} (SemNum: {sem.semester_number})")
        if sem.semester_number not in semester_by_number:
            semester_by_number[sem.semester_number] = []
        semester_by_number[sem.semester_number].append(sem)
    
    print(f"\n   Semester groups (for elective sync):")
    for sem_num, sems in sorted(semester_by_number.items()):
        names = [s.name for s in sems]
        print(f"      Semester {sem_num}: {names}")
    
    # 2. Check elective subjects - use is_elective flag or elective_basket_id
    print("\n[2] ELECTIVE SUBJECTS:")
    elective_subjects = db.query(Subject).filter(
        (Subject.is_elective == True) | 
        (Subject.elective_basket_id != None)
    ).all()
    
    # Also check subjects with subject_type containing 'elective'
    all_subjects = db.query(Subject).all()
    for subj in all_subjects:
        if 'elective' in str(subj.subject_type).lower() and subj not in elective_subjects:
            elective_subjects.append(subj)
    
    if not elective_subjects:
        print("   *** NO ELECTIVE SUBJECTS FOUND! ***")
        print("\n   To create electives:")
        print("   1. Go to Subjects page -> Add subject with is_elective=True")
        print("   2. Make sure to assign it to ALL classes of that semester")
        print("   3. Assign a teacher who can teach it")
    else:
        for subj in elective_subjects:
            print(f"\n   {subj.code}: {subj.name}")
            print(f"      is_elective={subj.is_elective}, type={subj.subject_type}")
            print(f"      elective_basket_id={subj.elective_basket_id}")
            assigned_sems = subj.semesters
            if assigned_sems:
                print(f"      Assigned to: {[s.name for s in assigned_sems]}")
            else:
                print("      Assigned to: *** NONE - NOT ASSIGNED TO ANY CLASS! ***")
            teachers = subj.teachers
            if teachers:
                print(f"      Teachers: {[t.name for t in teachers]}")
            else:
                print("      Teachers: *** NONE - NO TEACHER CAN TEACH THIS! ***")
    
    # 3. Check elective baskets
    print("\n[3] ELECTIVE BASKETS:")
    baskets = db.query(ElectiveBasket).all()
    if not baskets:
        print("   No elective baskets found")
    else:
        for basket in baskets:
            print(f"   {basket.code}: {basket.name} (Semester {basket.semester_number})")
            if basket.subjects:
                print(f"      Subjects: {[s.code for s in basket.subjects]}")
            else:
                print("      Subjects: NONE")
    
    # 4. DIAGNOSIS
    print("\n" + "="*60)
    print("DIAGNOSIS:")
    print("="*60)
    
    issues = []
    
    if not elective_subjects:
        issues.append("No elective subjects exist")
    
    for subj in elective_subjects:
        if not subj.teachers:
            issues.append(f"Subject {subj.code} has no teachers assigned")
        if not subj.semesters:
            issues.append(f"Subject {subj.code} not assigned to any class")
        
        # Check if assigned to ALL sections of same semester
        assigned_sem_numbers = set()
        for sem in subj.semesters:
            assigned_sem_numbers.add(sem.semester_number)
        
        for sem_num in assigned_sem_numbers:
            all_sections = semester_by_number.get(sem_num, [])
            assigned_sections = [s for s in subj.semesters if s.semester_number == sem_num]
            
            if len(assigned_sections) < len(all_sections):
                missing = [s.name for s in all_sections if s not in assigned_sections]
                issues.append(
                    f"Elective {subj.code}: Missing from sections {missing} of Semester {sem_num}"
                )
    
    if issues:
        print("\n*** ISSUES FOUND: ***")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        print("\n*** CRITICAL: Elective subjects MUST be assigned to ALL sections ***")
        print("*** of the same semester for synchronized scheduling to work! ***")
    else:
        if elective_subjects:
            print("\n   Configuration looks OK - electives should sync!")
        else:
            print("\n   No electives to sync")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
