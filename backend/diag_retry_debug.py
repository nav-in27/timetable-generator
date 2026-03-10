"""Debug: trace why _retry_failed_labs_post_theory cannot find candidates for I-F"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Semester, Room
from app.services.generator import TimetableGenerator, TimetableState, SLOTS_PER_DAY, DAYS_PER_WEEK

db = SessionLocal()

try:
    sems = db.query(Semester).filter(Semester.dept_id == 10).all()
    sem_ids = [s.id for s in sems]
    
    gen = TimetableGenerator(db)
    success, msg, allocs, t = gen.generate(
        semester_ids=sem_ids, clear_existing=True, semester_type="EVEN"
    )
    
    print(f"Gen: {success}, allocs={len(allocs)}")
    
    # Check allocation failures for lab issues
    print("\nFailed lab messages:")
    for f in gen.allocation_failures:
        if "LAB" in f:
            print(f"  {f}")
    
    # Check if any [LAB-RETRY] happened
    print("\nLab-retry messages: (should appear above if retry ran)")
    
    # Check I-F details
    if_allocs = [a for a in allocs if a.semester_id == 18]
    print(f"\nI-F allocs: {len(if_allocs)}")
    
    # Check what rooms are available as lab rooms
    all_rooms = db.query(Room).all()
    lab_rooms = [r for r in all_rooms if r.room_type and 'lab' in r.room_type.lower()]
    print(f"\nTotal lab rooms: {len(lab_rooms)}")
    for r in lab_rooms[:10]:
        print(f"  Room {r.id}: {r.name} type={r.room_type} cap={r.capacity}")

finally:
    db.close()
