"""
Clean Database Script
Deletes all teachers, subjects, and related data from the database.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.db.session import SessionLocal
from app.db.models import (
    Teacher, Subject, Room, Semester, 
    Allocation, ClassSubjectTeacher, 
    ElectiveBasket, Substitution,
    teacher_subjects, elective_basket_semesters
)

def cleanup_database():
    """Delete all teachers, subjects, and related data."""
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("DATABASE CLEANUP")
        print("=" * 60)
        print()
        
        # Count records before deletion
        teacher_count = db.query(Teacher).count()
        subject_count = db.query(Subject).count()
        allocation_count = db.query(Allocation).count()
        assignment_count = db.query(ClassSubjectTeacher).count()
        basket_count = db.query(ElectiveBasket).count()
        sub_count = db.query(Substitution).count()
        
        print(f"Records to delete:")
        print(f"  - Teachers: {teacher_count}")
        print(f"  - Subjects: {subject_count}")
        print(f"  - Allocations: {allocation_count}")
        print(f"  - Class Assignments: {assignment_count}")
        print(f"  - Elective Baskets: {basket_count}")
        print(f"  - Substitutions: {sub_count}")
        print()
        
        # Confirm deletion
        response = input("Are you sure you want to delete ALL teachers and subjects? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Cleanup cancelled.")
            return
        
        print()
        print("Deleting records...")
        
        # Delete in order of dependencies
        db.query(Substitution).delete(synchronize_session=False)
        print("  [OK] Deleted substitutions")
        
        db.query(Allocation).delete(synchronize_session=False)
        print("  [OK] Deleted allocations")
        
        db.query(ClassSubjectTeacher).delete(synchronize_session=False)
        print("  [OK] Deleted class assignments")
        
        db.query(ElectiveBasket).delete(synchronize_session=False)
        print("  [OK] Deleted elective baskets")
        
        db.query(Teacher).delete(synchronize_session=False)
        print("  [OK] Deleted teachers")
        
        db.query(Subject).delete(synchronize_session=False)
        print("  [OK] Deleted subjects")
        
        # Also clear the many-to-many relationships
        db.execute(teacher_subjects.delete())
        print("  [OK] Cleared teacher-subject relationships")
        
        db.execute(elective_basket_semesters.delete())
        print("  [OK] Cleared elective basket-semester relationships")
        
        db.commit()
        
        print()
        print("=" * 60)
        print("CLEANUP COMPLETE!")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_database()
