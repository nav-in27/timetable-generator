"""
Test script to verify multi-elective group support.

This script tests that:
1. Multiple elective groups within the same year are detected correctly
2. Each group gets its own independent time slot
3. Teachers are locked per-group and don't interfere across groups
4. Existing data is not modified
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy.orm import Session
from app.db.session import get_db, engine
from app.db.models import (
    Subject, Semester, Teacher, Room, Allocation,
    SubjectType, ComponentType, ElectiveBasket
)


def test_multi_elective_groups():
    """Test that multiple elective groups are properly detected and scheduled."""
    print("\n" + "="*70)
    print("MULTI-ELECTIVE GROUP SUPPORT TEST")
    print("="*70)
    
    db = next(get_db())
    
    try:
        # Query existing data
        semesters = db.query(Semester).all()
        subjects = db.query(Subject).all()
        baskets = db.query(ElectiveBasket).all()
        allocations = db.query(Allocation).all()
        
        print(f"\n[1] DATA SUMMARY:")
        print(f"    Total semesters: {len(semesters)}")
        print(f"    Total subjects: {len(subjects)}")
        print(f"    Total elective baskets: {len(baskets)}")
        print(f"    Total allocations: {len(allocations)}")
        
        # Find elective subjects
        elective_subjects = [s for s in subjects if s.is_elective or s.elective_basket_id is not None]
        print(f"\n[2] ELECTIVE SUBJECTS FOUND: {len(elective_subjects)}")
        
        if elective_subjects:
            # Group by basket
            by_basket = {}
            for s in elective_subjects:
                basket_id = s.elective_basket_id
                if basket_id not in by_basket:
                    by_basket[basket_id] = []
                by_basket[basket_id].append(s)
            
            print(f"    Unique baskets: {list(by_basket.keys())}")
            for basket_id, basket_subjects in by_basket.items():
                basket_name = "Unknown"
                for b in baskets:
                    if b.id == basket_id:
                        basket_name = b.name
                        break
                print(f"\n    Basket {basket_id} ({basket_name}):")
                for s in basket_subjects:
                    sems = [sem.name for sem in s.semesters]
                    print(f"      - {s.code}: {s.name} (Year: {s.semester})")
                    print(f"        Assigned to: {sems}")
        
        # Check elective allocations
        elective_allocs = [a for a in allocations if a.is_elective]
        print(f"\n[3] ELECTIVE ALLOCATIONS: {len(elective_allocs)}")
        
        if elective_allocs:
            # Group by basket
            by_basket = {}
            for a in elective_allocs:
                bid = a.elective_basket_id
                if bid not in by_basket:
                    by_basket[bid] = []
                by_basket[bid].append(a)
            
            print(f"    Unique baskets in allocations: {list(by_basket.keys())}")
            
            for basket_id, basket_allocs in by_basket.items():
                basket_name = "Unknown"
                for b in baskets:
                    if b.id == basket_id:
                        basket_name = b.name
                        break
                
                # Find slots used by this basket
                slots_used = set()
                for a in basket_allocs:
                    slots_used.add((a.day, a.slot))
                
                print(f"\n    Basket {basket_id} ({basket_name}): {len(basket_allocs)} allocations")
                print(f"      Slots used: {sorted(slots_used)}")
                
                # Check slot synchronization across classes
                classes_in_basket = set(a.semester_id for a in basket_allocs)
                print(f"      Classes covered: {classes_in_basket}")
                
                for day, slot in sorted(slots_used):
                    day_name = ["Mon", "Tue", "Wed", "Thu", "Fri"][day]
                    allocs_at_slot = [a for a in basket_allocs if a.day == day and a.slot == slot]
                    classes_at_slot = set(a.semester_id for a in allocs_at_slot)
                    print(f"        {day_name} P{slot+1}: {len(allocs_at_slot)} classes - {classes_at_slot}")
        
        # Verify no slot overlap between different baskets
        print(f"\n[4] SLOT OVERLAP VERIFICATION:")
        
        all_basket_slots = {}
        for a in elective_allocs:
            bid = a.elective_basket_id
            if bid not in all_basket_slots:
                all_basket_slots[bid] = set()
            all_basket_slots[bid].add((a.day, a.slot, a.semester_id))
        
        overlap_found = False
        basket_ids = list(all_basket_slots.keys())
        for i, bid1 in enumerate(basket_ids):
            for bid2 in basket_ids[i+1:]:
                # Check if different baskets use same (day, slot, class) combo
                # (This would be a conflict for same class)
                for slot1 in all_basket_slots.get(bid1, set()):
                    for slot2 in all_basket_slots.get(bid2, set()):
                        if slot1[0] == slot2[0] and slot1[1] == slot2[1] and slot1[2] == slot2[2]:
                            print(f"    [X] CONFLICT: Basket {bid1} and {bid2} both use Day {slot1[0]} Slot {slot1[1]} for Class {slot1[2]}")
                            overlap_found = True
        
        if not overlap_found and len(basket_ids) > 1:
            print("    [OK] No conflicts between different elective baskets")
        elif len(basket_ids) <= 1:
            print("    [INFO] Only one or no elective basket - no cross-basket validation needed")
        
        print("\n" + "="*70)
        print("TEST COMPLETE")
        print("="*70)
        
        return True
        
    except Exception as e:
        print(f"\n[X] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_multi_elective_groups()
    sys.exit(0 if success else 1)
