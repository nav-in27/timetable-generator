"""Test timetable generation with detailed error handling."""
import sys
import os
sys.path.insert(0, 'backend')
os.environ['PYTHONIOENCODING'] = 'utf-8'

import traceback

def test_generation():
    print("=" * 60)
    print("TIMETABLE GENERATION TEST")
    print("=" * 60)
    
    try:
        from app.db.session import get_db
        from app.db.models import Teacher, Subject, Semester, Room
        
        db = next(get_db())
        
        # Check data exists
        teachers = db.query(Teacher).count()
        subjects = db.query(Subject).count()
        semesters = db.query(Semester).count()
        rooms = db.query(Room).count()
        
        print(f"\nData in database:")
        print(f"  Teachers: {teachers}")
        print(f"  Subjects: {subjects}")
        print(f"  Semesters: {semesters}")
        print(f"  Rooms: {rooms}")
        
        if teachers == 0 or subjects == 0 or semesters == 0 or rooms == 0:
            print("\nERROR: Missing required data. Run seed_data.py first!")
            return
        
        print("\nImporting generator...")
        from app.services.generator import TimetableGenerator
        
        print("Creating generator instance...")
        gen = TimetableGenerator(db)
        
        print("Starting generation...")
        success, msg, allocs, time_taken = gen.generate()
        
        print(f"\n{'='*60}")
        print(f"Result:")
        print(f"  Success: {success}")
        print(f"  Message: {msg}")
        print(f"  Allocations: {len(allocs)}")
        print(f"  Time: {time_taken:.2f}s")
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
