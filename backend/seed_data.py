"""
Sample Data Seeder.

Creates realistic sample data for demo purposes:
- 8 Teachers with various specializations
- 10 Subjects (theory + labs)
- 4 Semesters/Classes
- 6 Rooms (lecture halls + labs)

Run with: python seed_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.db.models import (
    Teacher, Subject, Semester, Room,
    teacher_subjects, RoomType, SubjectType
)


def seed_database():
    """Seed the database with sample data."""
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Check if data already exists
        if db.query(Teacher).count() > 0:
            print("⚠️  Database already has data. Skipping seed.")
            return
        
        print("🌱 Seeding database with sample data...")
        
        # ============= ROOMS =============
        rooms_data = [
            {"name": "LH-101", "capacity": 60, "room_type": RoomType.LECTURE},
            {"name": "LH-102", "capacity": 60, "room_type": RoomType.LECTURE},
            {"name": "LH-103", "capacity": 80, "room_type": RoomType.LECTURE},
            {"name": "Seminar Hall", "capacity": 100, "room_type": RoomType.SEMINAR},
            {"name": "CS Lab 1", "capacity": 40, "room_type": RoomType.LAB},
            {"name": "CS Lab 2", "capacity": 40, "room_type": RoomType.LAB},
        ]
        
        for room_data in rooms_data:
            room = Room(**room_data)
            db.add(room)
        
        db.commit()
        print(f"  ✅ Created {len(rooms_data)} rooms")
        
        # ============= SUBJECTS =============
        subjects_data = [
            {"name": "Data Structures", "code": "CS201", "weekly_hours": 4, "subject_type": SubjectType.THEORY},
            {"name": "Data Structures Lab", "code": "CS201L", "weekly_hours": 2, "subject_type": SubjectType.LAB, "consecutive_slots": 2},
            {"name": "Database Management", "code": "CS301", "weekly_hours": 3, "subject_type": SubjectType.THEORY},
            {"name": "DBMS Lab", "code": "CS301L", "weekly_hours": 2, "subject_type": SubjectType.LAB, "consecutive_slots": 2},
            {"name": "Operating Systems", "code": "CS302", "weekly_hours": 4, "subject_type": SubjectType.THEORY},
            {"name": "Computer Networks", "code": "CS401", "weekly_hours": 3, "subject_type": SubjectType.THEORY},
            {"name": "Machine Learning", "code": "CS402", "weekly_hours": 3, "subject_type": SubjectType.THEORY},
            {"name": "ML Lab", "code": "CS402L", "weekly_hours": 2, "subject_type": SubjectType.LAB, "consecutive_slots": 2},
            {"name": "Software Engineering", "code": "CS303", "weekly_hours": 3, "subject_type": SubjectType.THEORY},
            {"name": "Discrete Mathematics", "code": "MA201", "weekly_hours": 3, "subject_type": SubjectType.THEORY},
        ]
        
        subjects = []
        for subj_data in subjects_data:
            subject = Subject(**subj_data)
            db.add(subject)
            subjects.append(subject)
        
        db.commit()
        
        # Refresh to get IDs
        for s in subjects:
            db.refresh(s)
        
        print(f"  ✅ Created {len(subjects_data)} subjects")
        
        # ============= TEACHERS =============
        teachers_data = [
            {
                "name": "Dr. Sharma",
                "email": "sharma@college.edu",
                "max_hours_per_week": 18,
                "experience_years": 15,
                "experience_score": 0.95,
                "subjects": ["CS201", "CS201L", "CS302"]  # DS, DS Lab, OS
            },
            {
                "name": "Prof. Reddy",
                "email": "reddy@college.edu",
                "max_hours_per_week": 16,
                "experience_years": 12,
                "experience_score": 0.88,
                "subjects": ["CS301", "CS301L"]  # DBMS, DBMS Lab
            },
            {
                "name": "Dr. Patel",
                "email": "patel@college.edu",
                "max_hours_per_week": 20,
                "experience_years": 8,
                "experience_score": 0.82,
                "subjects": ["CS401", "CS302"]  # Networks, OS
            },
            {
                "name": "Prof. Kumar",
                "email": "kumar@college.edu",
                "max_hours_per_week": 18,
                "experience_years": 10,
                "experience_score": 0.85,
                "subjects": ["CS402", "CS402L"]  # ML, ML Lab
            },
            {
                "name": "Dr. Singh",
                "email": "singh@college.edu",
                "max_hours_per_week": 16,
                "experience_years": 20,
                "experience_score": 0.92,
                "subjects": ["MA201", "CS303"]  # Math, SE
            },
            {
                "name": "Prof. Verma",
                "email": "verma@college.edu",
                "max_hours_per_week": 14,
                "experience_years": 5,
                "experience_score": 0.75,
                "subjects": ["CS201", "CS201L", "CS301"]  # DS, DS Lab, DBMS
            },
            {
                "name": "Dr. Gupta",
                "email": "gupta@college.edu",
                "max_hours_per_week": 18,
                "experience_years": 7,
                "experience_score": 0.80,
                "subjects": ["CS401", "CS303", "CS402"]  # Networks, SE, ML
            },
            {
                "name": "Prof. Rao",
                "email": "rao@college.edu",
                "max_hours_per_week": 16,
                "experience_years": 6,
                "experience_score": 0.78,
                "subjects": ["CS302", "MA201"]  # OS, Math
            },
        ]
        
        # Create subject code to id mapping
        subject_code_map = {s.code: s.id for s in subjects}
        
        for teacher_data in teachers_data:
            subject_codes = teacher_data.pop("subjects")
            teacher = Teacher(**teacher_data)
            db.add(teacher)
            db.flush()  # Get ID
            
            # Add teacher-subject relationships
            for code in subject_codes:
                if code in subject_code_map:
                    stmt = teacher_subjects.insert().values(
                        teacher_id=teacher.id,
                        subject_id=subject_code_map[code],
                        effectiveness_score=0.8 + (teacher.experience_score - 0.5) * 0.2
                    )
                    db.execute(stmt)
        
        db.commit()
        print(f"  ✅ Created {len(teachers_data)} teachers with subject assignments")
        
        # ============= SEMESTERS (CLASSES) =============
        semesters_data = [
            {"name": "3rd Semester - Section A", "code": "CS3A", "year": 2, "section": "A", "student_count": 60},
            {"name": "3rd Semester - Section B", "code": "CS3B", "year": 2, "section": "B", "student_count": 55},
            {"name": "5th Semester - Section A", "code": "CS5A", "year": 3, "section": "A", "student_count": 50},
            {"name": "7th Semester - Section A", "code": "CS7A", "year": 4, "section": "A", "student_count": 45},
        ]
        
        for sem_data in semesters_data:
            semester = Semester(**sem_data)
            db.add(semester)
        
        db.commit()
        print(f"  ✅ Created {len(semesters_data)} semesters/classes")
        
        print("\n🎉 Database seeded successfully!")
        print("\nSummary:")
        print(f"  - Rooms: {len(rooms_data)}")
        print(f"  - Subjects: {len(subjects_data)}")
        print(f"  - Teachers: {len(teachers_data)}")
        print(f"  - Semesters: {len(semesters_data)}")
        
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
