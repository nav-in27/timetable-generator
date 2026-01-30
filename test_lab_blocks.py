
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.db.base import Base
from app.db.models import Teacher, Subject, Semester, Room, RoomType, SubjectType, Department
from app.services.generator import TimetableGenerator

# Use a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_timetable_labs.db"
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
    
    # 3. Create Lab Subject (2 hours)
    sub_lab = Subject(name="Programming Lab", code="CS202L", dept_id=dept.id, 
                      subject_type=SubjectType.LAB, weekly_hours=2, consecutive_slots=2)
    db.add(sub_lab)
    db.commit()
    
    # 4. Assign Subject
    sem_a.subjects.append(sub_lab)
    db.commit()
    
    # 5. Create Teacher
    t1 = Teacher(name="Prof. Lab", email="lab@test.com", dept_id=dept.id, is_active=True)
    db.add(t1)
    db.commit()
    
    # Qualification
    t1.subjects.append(sub_lab)
    db.commit()
    
    # 6. Create Lab Room
    r1 = Room(name="Lab 1", capacity=100, room_type=RoomType.LAB, is_available=True)
    db.add(r1)
    db.commit()
    
    return sem_a.id, sub_lab.id

def test_lab_blocks():
    db = SessionLocal()
    try:
        sem_id, lab_sub_id = setup_test_data(db)
        
        print("Starting Lab Block Unit Test...")
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
        
        lab_reqs = [r for r in requirements if r.requires_lab]
        print(f"Found {len(lab_reqs)} lab requirements.")
        
        if not lab_reqs:
            print("FAILED: No lab requirements found.")
            return

        # 3. Run Lab Logic Directly
        teacher_loads = {t.id: 0 for t in teachers}
        generator._schedule_lab_blocks(
            state, lab_reqs, rooms, teacher_loads, fixed_assignments
        )
        
        # 4. Analyze Results
        allocations = state.allocations
        lab_allocs = [a for a in allocations if a.subject_id == lab_sub_id]
        
        if not lab_allocs:
            print("FAILED: No labs scheduled.")
            return
            
        print(f"Scheduled {len(lab_allocs)} lab slots.")
        
        if len(lab_allocs) != 2:
            print(f"FAILED: Expected 2 slots, got {len(lab_allocs)}")
            return
            
        # Check consecutively
        # Sort by slot
        lab_allocs.sort(key=lambda x: x.slot)
        
        a1, a2 = lab_allocs[0], lab_allocs[1]
        
        print(f"Slot 1: Day {a1.day} Slot {a1.slot}")
        print(f"Slot 2: Day {a2.day} Slot {a2.slot}")
        
        if a1.day != a2.day:
            print("FAILED: Lab slots on different days.")
        elif a2.slot == a1.slot + 1:
            print("SUCCESS: Lab slots are consecutive.")
            
            # Check Atomicity Tracking
            block_info = state.get_lab_block_for_slot(sem_id, a1.day, a1.slot)
            if block_info:
                 print(f"SUCCESS: Block tracking confirmed: {block_info}")
            else:
                 print("FAILED: Lab block not registered in state.")
        else:
            print(f"FAILED: Lab slots NOT consecutive ({a1.slot}, {a2.slot}).")

    finally:
        db.close()

if __name__ == "__main__":
    test_lab_blocks()
