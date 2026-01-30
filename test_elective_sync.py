
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
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_timetable.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_test_data(db):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # 1. Create Department
    dept = Department(name="Computer Science", code="CS")
    db.add(dept)
    db.commit()
    
    # 2. Create Semesters (Year 2, Section A and B)
    # They match by YEAR
    sem_a = Semester(name="Year 2 - Sec A", code="Y2A", dept_id=dept.id, student_count=60, year=2, section="A")
    sem_b = Semester(name="Year 2 - Sec B", code="Y2B", dept_id=dept.id, student_count=60, year=2, section="B")
    db.add(sem_a)
    db.add(sem_b)
    db.commit()
    
    # 3. Create Subjects
    # Elective for Year 2
    sub_elec = Subject(name="AI Elective", code="CS201", dept_id=dept.id, 
                      subject_type=SubjectType.ELECTIVE, weekly_hours=3)
    
    # Regular subjects to fill the schedule
    sub_reg_a = Subject(name="Core Java", code="CS202", dept_id=dept.id, weekly_hours=4)
    sub_reg_b = Subject(name="Data Structures", code="CS203", dept_id=dept.id, weekly_hours=4)
    
    db.add(sub_elec)
    db.add(sub_reg_a)
    db.add(sub_reg_b)
    db.commit()
    
    # 4. Assign Subjects
    # Sec A takes Elective + Core Java
    sem_a.subjects.append(sub_elec)
    sem_a.subjects.append(sub_reg_a)
    
    # Sec B takes Data Structures (NO Elective assigned explicitly)
    sem_b.subjects.append(sub_reg_b)
    db.commit()
    
    # 5. Create Teachers
    t1 = Teacher(name="Prof. AI", email="ai@test.com", dept_id=dept.id, is_active=True)
    t2 = Teacher(name="Prof. Java", email="java@test.com", dept_id=dept.id, is_active=True)
    t3 = Teacher(name="Prof. DS", email="ds@test.com", dept_id=dept.id, is_active=True)
    
    db.add(t1)
    db.add(t2)
    db.add(t3)
    db.commit()
    
    # Qualification
    # Prof AI teaches Elective
    t1.subjects.append(sub_elec)
    t2.subjects.append(sub_reg_a)
    t3.subjects.append(sub_reg_b)
    db.commit()
    
    # 6. Create Rooms
    r1 = Room(name="Room 101", capacity=100, room_type=RoomType.LECTURE, is_available=True)
    r2 = Room(name="Room 102", capacity=100, room_type=RoomType.LECTURE, is_available=True)
    db.add(r1)
    db.add(r2)
    db.commit()
    
    return [sem_a.id, sem_b.id], sub_elec.id

def test_sync():
    db = SessionLocal()
    try:
        sem_ids, elec_sub_id = setup_test_data(db)
        sem_a_id, sem_b_id = sem_ids
        
        print("Starting Elective Sync Unit Test...")
        generator = TimetableGenerator(db)
        semesters = db.query(Semester).filter(Semester.id.in_(sem_ids)).all()
        subjects = db.query(Subject).all()
        teachers = db.query(Teacher).all()
        rooms = db.query(Room).all()
        
        # 1. Initialize State
        from app.services.generator import TimetableState
        state = TimetableState()
        
        # 2. Build Requirements
        # Need to mimic what generate() does
        teacher_subject_map = generator._build_teacher_subject_map()
        teacher_by_id = {t.id: t for t in teachers}
        
        # Run Phase 2 logic (assign teachers) mostly to get assignments
        fixed_assignments = generator._assign_fixed_teachers(semesters, subjects, teacher_subject_map, teacher_by_id)
        state.fixed_teacher_assignments = fixed_assignments.copy()
        
        requirements = generator._build_requirements_with_fixed_teachers(
            semesters, subjects, teacher_subject_map, fixed_assignments
        )
        
        teacher_loads = {t.id: 0 for t in teachers}
        
        # 3. Verify Requirements
        elec_reqs = [r for r in requirements if r.subject_type == SubjectType.ELECTIVE]
        print(f"Found {len(elec_reqs)} elective requirements.")
        if not elec_reqs:
            print("FAILED: No elective requirements generated.")
            return

        # 4. Run Sync Logic Directly
        generator._schedule_electives_for_year_sync(
            state, semesters, requirements, rooms, teacher_loads
        )
        
        # 5. Analyze Results
        allocations = state.allocations
        elec_allocs = [a for a in allocations if a.semester_id == sem_a_id and a.subject_id == elec_sub_id]
        
        if not elec_allocs:
            print("FAILED: No electives scheduled for Sem A after sync call")
            return
            
        print(f"Sem A has {len(elec_allocs)} elective slots.")
        
        for alloc in elec_allocs:
            day = alloc.day
            slot = alloc.slot
            print(f"Elective at Week {day} Slot {slot}")
            
            # Check locks
            # Is Sem B locked at this slot?
            is_sem_b_locked = state.is_slot_locked(sem_b_id, day, slot)
            is_sem_b_occupied = not state.is_semester_free(sem_b_id, day, slot)
            
            print(f"  Sem B Locked: {is_sem_b_locked}")
            print(f"  Sem B Occupied: {is_sem_b_occupied}")
            
            if is_sem_b_locked or is_sem_b_occupied:
                print(f"  SUCCESS: Sem B is properly blocked/synchronized.")
            else:
                print(f"  CRITICAL FAILURE: Sem B is NOT blocked at this time.")

    finally:
        db.close()


if __name__ == "__main__":
    test_sync()

