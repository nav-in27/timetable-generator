
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Allocation, ComponentType, ElectiveBasket
from app.services.generator import TimetableGenerator

def test_elective_day_constraint():
    print("\n" + "="*70)
    print("ELECTIVE DAY CONSTRAINT VERIFICATION")
    print("="*70)
    
    db = next(get_db())
    
    # 1. Trigger Generation
    print("\n[1] Triggering Generation...")
    generator = TimetableGenerator(db)
    success, message, allocations, gen_time = generator.generate()
    
    if not success:
        print(f"    [X] Generation failed: {message}")
        return
    
    print(f"    [OK] Generated {len(allocations)} allocations in {gen_time:.2f}s")
    
    # 2. Group allocations by elective basket and day
    print("\n[2] Checking elective day constraints...")
    
    # Re-fetch allocations from DB to be sure
    db_allocs = db.query(Allocation).filter(Allocation.is_elective == True).all()
    
    basket_day_components = {} # (basket_id, day) -> set of component types
    
    for a in db_allocs:
        key = (a.elective_basket_id, a.day)
        if key not in basket_day_components:
            basket_day_components[key] = set()
        basket_day_components[key].add(a.component_type)
        
    violations = 0
    checked_groups = set()
    
    for (basket_id, day), components in basket_day_components.items():
        checked_groups.add(basket_id)
        if ComponentType.THEORY in components and ComponentType.LAB in components:
            day_name = ["Mon", "Tue", "Wed", "Thu", "Fri"][day]
            print(f"    [X] VIOLATION: Basket {basket_id} has both THEORY and LAB on {day_name}")
            violations += 1
            
    if violations == 0:
        print(f"    [OK] No elective group has both Theory and Lab on the same day.")
        print(f"    Validated {len(checked_groups)} elective group(s) across all days.")
    else:
        print(f"    [FAIL] Found {violations} violations of the 'no theory and lab on same day' rule.")
        
    print("\n" + "="*70)
    print("VERIFICATION COMPLETE")
    print("="*70)

if __name__ == "__main__":
    test_elective_day_constraint()
