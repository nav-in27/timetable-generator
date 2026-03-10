"""
Focused diagnostic: Why can't I-F labs (GEA1121/Saranya, GEA1111/Dhandapani) find valid blocks?
Check teacher availability at each valid 2-period lab window.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Semester, Subject, Teacher, ClassSubjectTeacher, Allocation
from app.services.generator import TimetableGenerator, TimetableState, SLOTS_PER_DAY, DAYS_PER_WEEK, VALID_LAB_BLOCKS

db = SessionLocal()

try:
    # Re-run gen to populate state
    sems = db.query(Semester).filter(Semester.dept_id == 10).all()
    sem_ids = [s.id for s in sems]
    gen = TimetableGenerator(db)
    success, msg, allocs, t = gen.generate(
        semester_ids=sem_ids, clear_existing=True, semester_type="EVEN"
    )
    
    print(f"Gen done: {len(allocs)} allocs")
    
    # Now investigate: For teacher 133 (Saranya) and 176 (Dhandapani),
    # check what they're doing at each valid lab block
    if_id = 18
    if_allocs = [a for a in allocs if a.semester_id == if_id]
    
    # Collect ALL allocations by teacher
    t133_allocs = [a for a in allocs if a.teacher_id == 133]
    t176_allocs = [a for a in allocs if a.teacher_id == 176]
    
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    
    print(f"\n=== Teacher 133 (Saranya) Schedule ===")
    for day in range(DAYS_PER_WEEK):
        for slot in range(SLOTS_PER_DAY):
            matches = [a for a in t133_allocs if a.day == day and a.slot == slot]
            for a in matches:
                sem = next((s for s in sems if s.id == a.semester_id), None)
                sec = sem.section if sem else '?'
                sub = db.query(Subject).filter(Subject.id == a.subject_id).first() if a.subject_id else None
                sname = sub.name if sub else 'FREE'
                ct = a.component_type.value if hasattr(a.component_type, 'value') else str(a.component_type)
                print(f"  {day_names[day]} Slot{slot}: Sec {sec} (sem={a.semester_id}) {sname} [{ct}]")
    
    print(f"\n=== Teacher 176 (Dhandapani) Schedule ===")
    for day in range(DAYS_PER_WEEK):
        for slot in range(SLOTS_PER_DAY):
            matches = [a for a in t176_allocs if a.day == day and a.slot == slot]
            for a in matches:
                sem = next((s for s in sems if s.id == a.semester_id), None)
                sec = sem.section if sem else '?'
                sub = db.query(Subject).filter(Subject.id == a.subject_id).first() if a.subject_id else None
                sname = sub.name if sub else 'FREE'
                ct = a.component_type.value if hasattr(a.component_type, 'value') else str(a.component_type)
                print(f"  {day_names[day]} Slot{slot}: Sec {sec} (sem={a.semester_id}) {sname} [{ct}]")
    
    # For I-F (sem_id=18), check which slots are free
    if_filled = {(a.day, a.slot) for a in if_allocs}
    print(f"\n=== I-F Open Slots ===")
    for day in range(DAYS_PER_WEEK):
        for slot in range(SLOTS_PER_DAY):
            if (day, slot) not in if_filled:
                print(f"  {day_names[day]} Slot{slot}")
    
    # Check valid lab blocks for I-F: which ones have the semester free AND teacher free?
    valid_blocks = [(0, 1), (1, 2), (3, 4), (4, 5), (5, 6)]
    
    for tid, tname, lab_name in [(133, 'Saranya', 'Eng Math Lab'), (176, 'Dhandapani', 'Eng Physics Lab')]:
        t_allocs = [a for a in allocs if a.teacher_id == tid]
        t_busy = {(a.day, a.slot) for a in t_allocs}
        
        print(f"\n=== Lab Block Availability for {tname} ({lab_name}) ===")
        for day in range(DAYS_PER_WEEK):
            for s1, s2 in valid_blocks:
                sem_free = (day, s1) not in if_filled and (day, s2) not in if_filled
                teacher_free = (day, s1) not in t_busy and (day, s2) not in t_busy
                if sem_free and teacher_free:
                    print(f"  [AVAILABLE] {day_names[day]} Slots {s1}-{s2}")
                elif sem_free and not teacher_free:
                    # What is the teacher doing?
                    busy_at = []
                    for s in [s1, s2]:
                        m = [a for a in t_allocs if a.day == day and a.slot == s]
                        for a in m:
                            sm = next((x for x in sems if x.id == a.semester_id), None)
                            sec = sm.section if sm else '?'
                            sub = db.query(Subject).filter(Subject.id == a.subject_id).first() if a.subject_id else None
                            busy_at.append(f"Slot{s}: Sec {sec} {sub.name if sub else 'FREE'}")
                    print(f"  [TEACHER BUSY] {day_names[day]} Slots {s1}-{s2}: {'; '.join(busy_at)}")
                elif not sem_free:
                    pass  # Semester occupied, not interesting

    # Also check: what other classes does teacher 133 and 176 teach?
    print("\n=== Teacher 133 (Saranya) other class assignments ===")
    for a in db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.teacher_id == 133).all():
        sem = db.query(Semester).filter(Semester.id == a.semester_id).first()
        sub = db.query(Subject).filter(Subject.id == a.subject_id).first()
        ct = a.component_type.value if hasattr(a.component_type, 'value') else str(a.component_type)
        sname = sub.name if sub else str(a.subject_id)
        sec = sem.section if sem else '?'
        print(f"  Sec {sec} (sem={a.semester_id}): {sname} [{ct}]")

    print("\n=== Teacher 176 (Dhandapani) other class assignments ===")
    for a in db.query(ClassSubjectTeacher).filter(ClassSubjectTeacher.teacher_id == 176).all():
        sem = db.query(Semester).filter(Semester.id == a.semester_id).first()
        sub = db.query(Subject).filter(Subject.id == a.subject_id).first()
        ct = a.component_type.value if hasattr(a.component_type, 'value') else str(a.component_type)
        sname = sub.name if sub else str(a.subject_id)
        sec = sem.section if sem else '?'
        print(f"  Sec {sec} (sem={a.semester_id}): {sname} [{ct}]")

finally:
    db.close()
