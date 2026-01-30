"""
Debug script to check elective subjects and their scheduling.
Run from the backend directory.
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.db.models import Subject, Semester, Teacher, ElectiveBasket, SubjectType, teacher_subjects

def main():
    db = SessionLocal()
    
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
    for sem_num, sems in semester_by_number.items():
        names = [s.name for s in sems]
        print(f"      Semester {sem_num}: {names}")
    
    # 2. Check elective subjects
    print("\n[2] ELECTIVE SUBJECTS:")
    elective_subjects = db.query(Subject).filter(
        (Subject.is_elective == True) | 
        (Subject.subject_type == SubjectType.ELECTIVE) |
        (Subject.elective_basket_id != None)
    ).all()
    
    if not elective_subjects:
        print("   *** NO ELECTIVE SUBJECTS FOUND! ***")
        print("   To create electives:")
        print("   1. Go to Subjects page, add subject with type Elective")
        print("   2. OR go to Electives page and create Elective Basket")
    else:
        for subj in elective_subjects:
            print(f"   {subj.code}: {subj.name}")
            print(f"      is_elective={subj.is_elective}, type={subj.subject_type}")
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
            issues.append(f"Subject {subj.code} has no teachers")
        if not subj.semesters:
            issues.append(f"Subject {subj.code} not assigned to any class")
        
        # Check if assigned to ALL sections of same semester
        for sem in subj.semesters:
            all_sections = semester_by_number.get(sem.semester_number, [])
            assigned_sections = [s for s in subj.semesters if s.semester_number == sem.semester_number]
            
            if len(assigned_sections) < len(all_sections):
                missing = [s.name for s in all_sections if s not in assigned_sections]
                issues.append(
                    f"Subject {subj.code}: Missing from sections {missing} of Semester {sem.semester_number}"
                )
    
    if issues:
        print("\n*** ISSUES FOUND: ***")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        print("\n*** FIX: Elective subjects must be assigned to ALL sections of the same semester! ***")
    else:
        print("\n   Configuration looks OK")
    
    db.close()

if __name__ == "__main__":
    main()
