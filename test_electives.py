"""Test timetable generation with focus on electives."""
import sys
import os
sys.path.insert(0, 'backend')
os.environ['PYTHONIOENCODING'] = 'utf-8'

import traceback

def test_generation():
    print("=" * 60)
    print("TIMETABLE GENERATION TEST - ELECTIVE FOCUS")
    print("=" * 60)
    
    try:
        from app.db.session import get_db
        from app.db.models import Teacher, Subject, Semester, Room
        
        db = next(get_db())
        
        # Check elective subjects first
        print("\n[ELECTIVES IN DATABASE]")
        electives = db.query(Subject).filter(Subject.is_elective == True).all()
        for e in electives:
            teachers = [t.name for t in e.teachers]
            semesters = [s.name for s in e.semesters]
            print(f"  {e.code}: Teachers={teachers}, Classes={semesters}")
        
        print("\n[STARTING GENERATION]")
        from app.services.generator import TimetableGenerator
        
        gen = TimetableGenerator(db)
        success, msg, allocs, time_taken = gen.generate()
        
        print(f"\n{'='*60}")
        print(f"Result:")
        print(f"  Success: {success}")
        print(f"  Message: {msg}")
        print(f"  Total Allocations: {len(allocs)}")
        print(f"  Time: {time_taken:.2f}s")
        
        # Check for elective allocations
        elective_allocs = [a for a in allocs if a.is_elective]
        print(f"\n  ELECTIVE Allocations: {len(elective_allocs)}")
        
        if elective_allocs:
            print("\n[ELECTIVE SCHEDULE]")
            for a in elective_allocs:
                subject = db.query(Subject).filter(Subject.id == a.subject_id).first()
                semester = db.query(Semester).filter(Semester.id == a.semester_id).first()
                print(f"  {subject.code if subject else a.subject_id} -> {semester.name if semester else a.semester_id} (Day {a.day+1}, Slot {a.slot+1})")
        else:
            print("\n  *** NO ELECTIVE ALLOCATIONS CREATED! ***")
            print("  Check the Phase 2 and Phase 3 output above for issues.")
        
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"ERROR TYPE: {type(e).__name__}")
        print(f"ERROR MSG: {str(e)}")
        print(f"{'='*60}")
        print("\nFull traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    test_generation()
