
import sys
import os
import random
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.db.base import Base
from app.db.models import Teacher, Subject, Semester, Room, RoomType, SubjectType, Department
from app.services.generator import TimetableGenerator

# Use a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_timetable_theory.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_test_data(db):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # 1. Create Department
    dept = Department(name="Computer Science", code="CS")
    db.add(dept)
    db.commit()
    
    # 2. Create Semester
    sem_a = Semester(name="Year 2 - Sec A", code="Y2A", dept_id=dept.id, student_count=60, year=2, section="A")
    db.add(sem_a)
    db.commit()
    
    # 3. Create Subjects to fill 35 hours
    # 5 subjects * 7 hours each = 35 hours
    subjects = []
    for i in range(5):
        sub = Subject(name=f"Subject {i+1}", code=f"CS30{i}", dept_id=dept.id, 
                      subject_type=SubjectType.THEORY, weekly_hours=7)
        subjects.append(sub)
        db.add(sub)
    db.commit()
    
    # 4. Assign Subjects
    for sub in subjects:
        sem_a.subjects.append(sub)
    db.commit()
    
    # 5. Create Teachers
    # 5 teachers, one for each subject
    teachers = []
    for i in range(5):
        t = Teacher(name=f"Prof. {i+1}", email=f"p{i}@test.com", dept_id=dept.id, is_active=True, max_hours_per_week=20)
        teachers.append(t)
        db.add(t)
    db.commit()
    
    # Qualification
    for i in range(5):
        teachers[i].subjects.append(subjects[i])
    db.commit()
    
    # 6. Create Room
    r1 = Room(name="Classroom 1", capacity=100, room_type=RoomType.LECTURE, is_available=True)
    db.add(r1)
    db.commit()
    
    return sem_a.id

def test_theory_csp():
    db = SessionLocal()
    try:
        sem_id = setup_test_data(db)
        
        print("Starting Theory CSP Unit Test...")
        generator = TimetableGenerator(db)
        semesters = db.query(Semester).all()
        subjects = db.query(Subject).all()
        teachers = db.query(Teacher).all()
        rooms = db.query(Room).all()
        
        # 1. Initialize State
        from app.services.generator import TimetableState
        state = TimetableState()
        
        # 2. Build Requirements
        teacher_subject_map = generator._build_teacher_subject_map()
        teacher_by_id = {t.id: t for t in teachers}
        fixed_assignments = generator._assign_fixed_teachers(semesters, subjects, teacher_subject_map, teacher_by_id)
        
        requirements = generator._build_requirements_with_fixed_teachers(
            semesters, subjects, teacher_subject_map, fixed_assignments
        )
        
        theory_reqs = [r for r in requirements if not r.requires_lab and r.subject_type != SubjectType.ELECTIVE]
        print(f"Found {len(theory_reqs)} theory requirements for {sum(r.weekly_hours for r in theory_reqs)} hours.")
        
        # 3. Run CSP Theory Logic
        teacher_loads = {t.id: 0 for t in teachers}
        success, msg = generator._schedule_theory_csp(
            state, theory_reqs, rooms, semesters, teacher_loads, fixed_assignments
        )
        
        print(f"Result: {success} - {msg}")
        
        if not success:
            print("FAILED: Theory scheduling returned False.")
            return

        # 4. Analyze Results
        allocations = state.allocations
        print(f"Total Allocations: {len(allocations)}")
        
        if len(allocations) != 35:
             print(f"FAILED: Expected 35 slots, got {len(allocations)}.")
             missing = 35 - len(allocations)
             print(f"        Missing {missing} slots.")
        else:
             print("SUCCESS: Exact 35 slots filled.")
             
        # Verify no gaps
        filled_slots = set((a.day, a.slot) for a in allocations)
        if len(filled_slots) != 35:
             print(f"FAILED: Overlap detected? Unique slots = {len(filled_slots)}")
        else:
             print("SUCCESS: No gaps, no overlaps.")
             
    finally:
        db.close()

if __name__ == "__main__":
    test_theory_csp()
