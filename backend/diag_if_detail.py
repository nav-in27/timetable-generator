"""
Detailed diagnostic for I-F (semester_id=18) free periods.
Runs generation for Dept 10 and traces EXACTLY which slots fail for I-F and why.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Semester, Subject, Teacher, ClassSubjectTeacher, Allocation, ComponentType
from app.services.generator import TimetableGenerator, TimetableState, SLOTS_PER_DAY, DAYS_PER_WEEK

db = SessionLocal()

try:
    # Re-generate for Dept 10
    sems = db.query(Semester).filter(Semester.dept_id == 10).all()
    sem_ids = [s.id for s in sems]
    
    gen = TimetableGenerator(db)
    success, msg, allocs, t = gen.generate(
        semester_ids=sem_ids,
        clear_existing=True,
        semester_type="EVEN"
    )
    
    print(f"\nGEN RESULT: success={success}, allocs={len(allocs)}, time={t:.1f}s")
    print(f"MSG: {msg}")
    
    # Now check I-F details
    if_id = 18  # I-F semester_id
    if_allocs = [a for a in allocs if a.semester_id == if_id]
    
    print(f"\n=== I-F (sem_id={if_id}) ALLOCATIONS ({len(if_allocs)}) ===")
    
    # Build grid
    grid = {}
    for a in if_allocs:
        grid[(a.day, a.slot)] = a
    
    print("\nGRID (Day x Slot):")
    print(f"{'':>6}", end="")
    for slot in range(SLOTS_PER_DAY):
        print(f"  Slot{slot}", end="")
    print()
    
    for day in range(DAYS_PER_WEEK):
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
        print(f"{day_names[day]:>6}", end="")
        for slot in range(SLOTS_PER_DAY):
            a = grid.get((day, slot))
            if a:
                if a.subject_id:
                    print(f"  S{a.subject_id:>3}", end="")
                else:
                    print("  FREE", end="")
            else:
                print("  ----", end="")
        print()
    
    # Find empty slots
    filled_slots = {(a.day, a.slot) for a in if_allocs}
    all_slots = {(d, s) for d in range(DAYS_PER_WEEK) for s in range(SLOTS_PER_DAY)}
    empty_slots = all_slots - filled_slots
    
    print(f"\n=== EMPTY SLOTS for I-F ({len(empty_slots)} total) ===")
    for d, s in sorted(empty_slots):
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
        print(f"  {day_names[d]} Slot {s}")
    
    # Check teacher assignments for I-F
    if_assignments = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.semester_id == if_id,
        ClassSubjectTeacher.batch_id.is_(None)
    ).all()
    
    print(f"\n=== TEACHER ASSIGNMENTS for I-F ({len(if_assignments)}) ===")
    total_hours = 0
    for a in sorted(if_assignments, key=lambda x: (x.subject_id, x.component_type.value)):
        subj = db.query(Subject).filter(Subject.id == a.subject_id).first()
        t = db.query(Teacher).filter(Teacher.id == a.teacher_id).first()
        sname = subj.name if subj else str(a.subject_id)
        tname = t.name if t else str(a.teacher_id)
        ct = a.component_type.value
        if ct == 'lab':
            h = subj.lab_hours_per_week if subj else 0
        elif ct == 'tutorial':
            h = subj.tutorial_hours_per_week if subj else 0
        else:
            h = subj.theory_hours_per_week if subj else 0
        total_hours += h
        print(f"  {sname} [{ct}] -> {tname} (ID={a.teacher_id}), {h}h/week")
    
    print(f"\n  TOTAL SCHEDULED HOURS EXPECTED: {total_hours}")
    print(f"  TOTAL SLOTS AVAILABLE: {DAYS_PER_WEEK * SLOTS_PER_DAY} = {DAYS_PER_WEEK * SLOTS_PER_DAY}")
    print(f"  ACTUAL ALLOCATIONS: {len(if_allocs)}")
    print(f"  DEFICIT: {total_hours - len(if_allocs)} slots")

    # Check for failures logged
    print(f"\n=== ALLOCATION FAILURES (I-F related) ===")
    for f in gen.allocation_failures:
        if "18" in f or "I-F" in f:
            print(f"  {f}")

finally:
    db.close()
