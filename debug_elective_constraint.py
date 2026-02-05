
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Allocation, ComponentType, ElectiveBasket, Subject, Semester
from app.services.generator import TimetableGenerator

def check_data():
    db = next(get_db())
    
    # Check subjects
    subjects = db.query(Subject).all()
    elective_subjects = [s for s in subjects if s.is_elective or s.elective_basket_id is not None]
    
    print(f"Total subjects: {len(subjects)}")
    print(f"Elective subjects: {len(elective_subjects)}")
    
    for s in elective_subjects:
        print(f"  - {s.code} ({s.name}), elective_basket_id={s.elective_basket_id}, type={s.subject_type}")
        
    # Check if any elective subject has both Theory and Lab components
    # (In the current model, components are derived from subject_type or specific hour fields)
    
    # Check allocations
    allocations = db.query(Allocation).all()
    print(f"Total allocations: {len(allocations)}")
    elective_allocs = [a for a in allocations if a.is_elective]
    print(f"Elective allocations: {len(elective_allocs)}")
    
    if not elective_allocs:
        print("No elective allocations found. Generating...")
        generator = TimetableGenerator(db)
        generator.generate()
        allocations = db.query(Allocation).all()
        elective_allocs = [a for a in allocations if a.is_elective]
        print(f"New elective allocations: {len(elective_allocs)}")

    # Check for theory and lab on same day
    basket_day_types = {} # (basket_id, day) -> set
    for a in elective_allocs:
        key = (a.elective_basket_id, a.day)
        if key not in basket_day_types:
            basket_day_types[key] = set()
        basket_day_types[key].add(a.component_type.value if hasattr(a.component_type, 'value') else a.component_type)
        
    violations = 0
    for (bid, day), ctypes in basket_day_types.items():
        if 'theory' in ctypes and 'lab' in ctypes:
            print(f"!!! VIOLATION: Basket {bid} has both THEORY and LAB on day {day}")
            violations += 1
            
    if violations == 0 and elective_allocs:
        print("SUCCESS: No violations found!")
    elif not elective_allocs:
        print("SKIP: No elective allocations to check.")

if __name__ == "__main__":
    check_data()
