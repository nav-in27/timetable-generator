"""Test timetable generation and check elective allocations."""
import urllib.request
import json

BASE_URL = "http://localhost:8000/api"

def api_get(endpoint):
    """Make a GET request."""
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())

def api_post(endpoint, data=None):
    """Make a POST request."""
    url = f"{BASE_URL}{endpoint}"
    if data:
        body = json.dumps(data).encode()
    else:
        body = b'{}'
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode())

# First, trigger regeneration
print("=" * 60)
print("TRIGGERING TIMETABLE GENERATION")
print("=" * 60)

try:
    result = api_post("/timetable/generate", {"clear_existing": True})
    print(f"Success: {result.get('success')}")
    print(f"Message: {result.get('message')}")
    print(f"Allocations: {result.get('total_allocations', 0)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Now check elective allocations
print("\n" + "=" * 60)
print("CHECKING ELECTIVE ALLOCATIONS")
print("=" * 60)

try:
    # Get allocations
    allocations = api_get("/timetable/allocations")
    
    # Filter elective allocations
    elective_allocs = [a for a in allocations if a.get('is_elective')]
    
    print(f"\nTotal allocations: {len(allocations)}")
    print(f"Elective allocations: {len(elective_allocs)}")
    
    if elective_allocs:
        # Group by day/slot
        by_slot = {}
        for a in elective_allocs:
            key = (a['day'], a['slot'])
            if key not in by_slot:
                by_slot[key] = []
            by_slot[key].append(a)
        
        print("\nElective slot groups (should show multiple classes at same time):")
        for (day, slot), allocs in sorted(by_slot.items()):
            print(f"\n  Day {day}, Slot {slot}:")
            for a in allocs:
                print(f"    Class {a.get('semester_id')}: Subject {a.get('subject_id')} -> Teacher {a.get('teacher_id')}")
        
        # Verify: Check if all classes have electives at same slots
        print("\n  ✅ Success if multiple classes have electives at same day/slot!")
    else:
        print("\n*** NO ELECTIVE ALLOCATIONS FOUND! ***")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Check semester timetables
print("\n" + "=" * 60)
print("SEMESTER TIMETABLES SUMMARY")
print("=" * 60)

try:
    semesters = api_get("/semesters")
    
    for sem in semesters:
        sem_id = sem['id']
        sem_name = sem['name']
        
        # Get timetable view for this semester
        timetable = api_get(f"/timetable/view/semester/{sem_id}")
        
        # Count electives from all days/slots
        elective_count = 0
        for day in timetable.get('days', []):
            for slot in day.get('slots', []):
                if slot.get('is_elective'):
                    elective_count += 1
        
        # Count total non-empty slots
        total_slots = 0
        for day in timetable.get('days', []):
            for slot in day.get('slots', []):
                if slot.get('allocation_id'):
                    total_slots += 1
        
        print(f"\n  {sem_name}: {total_slots} filled slots, {elective_count} elective")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
