"""
Sample Data Seeder (Updated for Component-Based Model).

Creates realistic sample data for demo purposes:
- 8 Teachers with various specializations
- 10 Subjects with Theory + Lab + Tutorial components
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
    teacher_subjects, subject_semesters, RoomType, SubjectType
)


def seed_database():
    """Seed the database with sample data using the new component-based model."""
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Check if data already exists
        if db.query(Teacher).count() > 0:
            print("[WARN] Database already has data. Skipping seed.")
            return
        
        print("[SEED] Seeding database with sample data...")
        
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
        print(f"  [OK] Created {len(rooms_data)} rooms")
        
        # ============= SUBJECTS (Component-Based Model) =============
        # CORRECT MODEL: Each subject can have Theory + Lab + Tutorial components
        # All components share the same course code
        # Target: ~32-34 hours per week per semester (out of 35 slots)
        
        subjects_data = [
            # --- 3rd Semester (Total: 32 hours) ---
            {
                "name": "Data Structures", "code": "CS201", "semester": 3,
                "theory_hours_per_week": 4, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 6, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Discrete Mathematics", "code": "MA201", "semester": 3,
                "theory_hours_per_week": 4, "lab_hours_per_week": 0, "tutorial_hours_per_week": 1,
                "weekly_hours": 5, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Digital Logic Design", "code": "CS202", "semester": 3,
                "theory_hours_per_week": 3, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 5, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "OOP with C++", "code": "CS203", "semester": 3,
                "theory_hours_per_week": 3, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 5, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Environmental Science", "code": "ES201", "semester": 3,
                "theory_hours_per_week": 3, "lab_hours_per_week": 0, "tutorial_hours_per_week": 0,
                "weekly_hours": 3, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Ethics & Values", "code": "HS201", "semester": 3,
                "theory_hours_per_week": 3, "lab_hours_per_week": 0, "tutorial_hours_per_week": 0,
                "weekly_hours": 3, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Communications Lab", "code": "HS202", "semester": 3,
                "theory_hours_per_week": 0, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 2, "subject_type": SubjectType.REGULAR
            },
            # Total 3rd Sem: 4+4+3+3+3+3+0 = 20 theory, 2+0+2+2+0+0+2 = 8 lab, 0+1+0+0+0+0+0 = 1 tut
            # = 29 hours, 6 free periods

            # --- 5th Semester (Total: 33 hours) ---
            {
                "name": "Database Management Systems", "code": "CS301", "semester": 5,
                "theory_hours_per_week": 4, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 6, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Operating Systems", "code": "CS302", "semester": 5,
                "theory_hours_per_week": 4, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 6, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Software Engineering", "code": "CS303", "semester": 5,
                "theory_hours_per_week": 4, "lab_hours_per_week": 0, "tutorial_hours_per_week": 0,
                "weekly_hours": 4, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Theory of Computation", "code": "CS304", "semester": 5,
                "theory_hours_per_week": 4, "lab_hours_per_week": 0, "tutorial_hours_per_week": 1,
                "weekly_hours": 5, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Computer Organization", "code": "CS305", "semester": 5,
                "theory_hours_per_week": 4, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 6, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Technical Seminar", "code": "SE301", "semester": 5,
                "theory_hours_per_week": 2, "lab_hours_per_week": 0, "tutorial_hours_per_week": 0,
                "weekly_hours": 2, "subject_type": SubjectType.REGULAR
            },
            # Total 5th Sem: 4+4+4+4+4+2 = 22 theory, 2+2+0+0+2+0 = 6 lab, 0+0+0+1+0+0 = 1 tut
            # = 29 hours, 6 free periods

            # --- 7th Semester (Total: 31 hours) ---
            {
                "name": "Computer Networks", "code": "CS401", "semester": 7,
                "theory_hours_per_week": 4, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 6, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Machine Learning", "code": "CS402", "semester": 7,
                "theory_hours_per_week": 4, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 6, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Compiler Design", "code": "CS403", "semester": 7,
                "theory_hours_per_week": 4, "lab_hours_per_week": 0, "tutorial_hours_per_week": 0,
                "weekly_hours": 4, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Cloud Computing", "code": "CS404", "semester": 7,
                "theory_hours_per_week": 3, "lab_hours_per_week": 2, "tutorial_hours_per_week": 0,
                "weekly_hours": 5, "subject_type": SubjectType.REGULAR
            },
            {
                "name": "Project Phase-I", "code": "PR401", "semester": 7,
                "theory_hours_per_week": 0, "lab_hours_per_week": 6, "tutorial_hours_per_week": 0,
                "weekly_hours": 6, "subject_type": SubjectType.REGULAR
            },
            # Total 7th Sem: 4+4+4+3+0 = 15 theory, 2+2+0+2+6 = 12 lab, 0+0+0+0+0 = 0 tut
            # = 27 hours, 8 free periods
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
        
        print(f"  [OK] Created {len(subjects_data)} subjects (with component hours)")
        
        # ============= TEACHERS =============
        # Teachers can now teach both theory and lab components of the same subject
        teachers_data = [
            {
                "name": "Dr. Sharma",
                "email": "sharma@college.edu",
                "max_hours_per_week": 22,
                "experience_years": 15,
                "experience_score": 0.95,
                "subjects": ["CS201", "CS302"]  # DS (theory+lab), OS (theory+lab)
            },
            {
                "name": "Prof. Reddy",
                "email": "reddy@college.edu",
                "max_hours_per_week": 22,
                "experience_years": 12,
                "experience_score": 0.88,
                "subjects": ["CS301", "CS202"]  # DBMS (theory+lab), DLD (theory+lab)
            },
            {
                "name": "Dr. Patel",
                "email": "patel@college.edu",
                "max_hours_per_week": 22,
                "experience_years": 8,
                "experience_score": 0.82,
                "subjects": ["CS401", "CS404"]  # Networks (theory+lab), Cloud (theory+lab)
            },
            {
                "name": "Prof. Kumar",
                "email": "kumar@college.edu",
                "max_hours_per_week": 22,
                "experience_years": 10,
                "experience_score": 0.85,
                "subjects": ["CS402", "PR401"]  # ML (theory+lab), Project
            },
            {
                "name": "Dr. Singh",
                "email": "singh@college.edu",
                "max_hours_per_week": 20,
                "experience_years": 20,
                "experience_score": 0.92,
                "subjects": ["MA201", "CS303", "CS304"]  # Math, SE, TOC
            },
            {
                "name": "Prof. Verma",
                "email": "verma@college.edu",
                "max_hours_per_week": 20,
                "experience_years": 5,
                "experience_score": 0.75,
                "subjects": ["CS201", "CS301", "CS305"]  # DS, DBMS, Computer Org
            },
            {
                "name": "Dr. Gupta",
                "email": "gupta@college.edu",
                "max_hours_per_week": 22,
                "experience_years": 7,
                "experience_score": 0.80,
                "subjects": ["CS401", "CS203", "CS403"]  # Networks, OOP, Compiler
            },
            {
                "name": "Prof. Rao",
                "email": "rao@college.edu",
                "max_hours_per_week": 20,
                "experience_years": 6,
                "experience_score": 0.78,
                "subjects": ["ES201", "HS201", "HS202", "SE301"]  # Env, Ethics, Comm Lab, Seminar
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
        print(f"  [OK] Created {len(teachers_data)} teachers with subject assignments")
        
        # ============= SEMESTERS (CLASSES) =============
        semesters_data = [
            {"name": "3rd Semester - Section A", "code": "CS3A", "year": 2, "semester_number": 3, "section": "A", "student_count": 60},
            {"name": "3rd Semester - Section B", "code": "CS3B", "year": 2, "semester_number": 3, "section": "B", "student_count": 55},
            {"name": "5th Semester - Section A", "code": "CS5A", "year": 3, "semester_number": 5, "section": "A", "student_count": 50},
            {"name": "7th Semester - Section A", "code": "CS7A", "year": 4, "semester_number": 7, "section": "A", "student_count": 45},
        ]
        
        for sem_data in semesters_data:
            semester = Semester(**sem_data)
            db.add(semester)
        
        db.commit()
        print(f"  [OK] Created {len(semesters_data)} semesters/classes")
        
        # ============= LINK SUBJECTS TO SEMESTERS (M2M) =============
        # This enforces the new explicit mapping rule.
        # We link subjects to ALL sections of their respective semester number.
        
        # Get all updated objects with IDs
        all_subjects = db.query(Subject).all()
        all_semesters = db.query(Semester).all()
        
        sem_map = {} # semester_number -> [semester_ids]
        for sem in all_semesters:
            if sem.semester_number not in sem_map:
                sem_map[sem.semester_number] = []
            sem_map[sem.semester_number].append(sem.id)
            
        link_count = 0
        for subj in all_subjects:
            if subj.semester in sem_map:
                target_sem_ids = sem_map[subj.semester]
                for sem_id in target_sem_ids:
                    stmt = subject_semesters.insert().values(
                        subject_id=subj.id,
                        semester_id=sem_id
                    )
                    db.execute(stmt)
                    link_count += 1
        
        db.commit()
        print(f"  [OK] Linked {link_count} subject-class explicit mappings")
        
        # Print hourly breakdown
        print("\n[VALIDATION] Hourly Breakdown per Semester:")
        for sem_num, sem_ids in sem_map.items():
            sem_subjects = [s for s in all_subjects if s.semester == sem_num]
            total_theory = sum(getattr(s, 'theory_hours_per_week', 0) for s in sem_subjects)
            total_lab = sum(getattr(s, 'lab_hours_per_week', 0) for s in sem_subjects)
            total_tut = sum(getattr(s, 'tutorial_hours_per_week', 0) for s in sem_subjects)
            total = total_theory + total_lab + total_tut
            free = 35 - total
            print(f"  Semester {sem_num}: {total_theory}h theory + {total_lab}h lab + {total_tut}h tutorial = {total}h ({free} free slots)")
        
        print("\n[SUCCESS] Database seeded successfully!")
        print("\nSummary:")
        print(f"  - Rooms: {len(rooms_data)}")
        print(f"  - Subjects: {len(subjects_data)}")
        print(f"  - Teachers: {len(teachers_data)}")
        print(f"  - Semesters: {len(semesters_data)}")
        print(f"  - Mappings: {link_count}")
        
    except Exception as e:
        print(f"[ERROR] Error seeding database: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
