"""
Test script: generate timetables for I-B and I-F combined (Dept 10 Science & Humanities)
and verify no free periods.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Semester, Allocation
from app.services.generator import TimetableGenerator

db = SessionLocal()

try:
    # Get Science & Humanities department ID 10 semesters
    sems = db.query(Semester).filter(Semester.dept_id == 10).all()
    sem_ids = [s.id for s in sems]
    print(f"Testing generation for Dept 10 (Science & Humanities): {len(sems)} classes")
    print(f"Semester IDs: {sem_ids}")
    
    # Sections
    for s in sems:
        print(f"  ID={s.id} Section={s.section}")
    
    # Count pre-generation allocations
    pre_allocs = db.query(Allocation).filter(Allocation.semester_id.in_(sem_ids)).count()
    free_pre = db.query(Allocation).filter(
        Allocation.semester_id.in_(sem_ids),
        Allocation.subject_id.is_(None)
    ).count()
    print(f"\nPRE-GENERATION: {pre_allocs} allocations, {free_pre} free periods")
    
    # Run generator
    gen = TimetableGenerator(db)
    success, msg, allocs, t = gen.generate(
        semester_ids=sem_ids,
        clear_existing=True,
        semester_type="EVEN"
    )
    
    print(f"\nGENERATION RESULT: success={success}, time={t:.1f}s")
    print(f"Message: {msg}")
    print(f"Total allocations returned: {len(allocs)}")
    
    # Count post-generation allocations from DB
    db.commit()
    post_allocs = db.query(Allocation).filter(Allocation.semester_id.in_(sem_ids)).count()
    free_post = db.query(Allocation).filter(
        Allocation.semester_id.in_(sem_ids),
        Allocation.subject_id.is_(None)
    ).count()
    print(f"\nPOST-GENERATION: {post_allocs} allocations, {free_post} free periods")
    
    # Per-section breakdown
    print("\nPER-SECTION BREAKDOWN:")
    for s in sems:
        sec_allocs = db.query(Allocation).filter(Allocation.semester_id == s.id).count()
        sec_free = db.query(Allocation).filter(
            Allocation.semester_id == s.id,
            Allocation.subject_id.is_(None)
        ).count()
        status = "OK" if sec_free == 0 else f"FREE PERIODS: {sec_free}"
        print(f"  Sec {s.section} (ID={s.id}): {sec_allocs} allocs, {status}")

finally:
    db.close()
