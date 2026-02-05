"""Simple elective test."""
import urllib.request
import json

BASE = "http://localhost:8000/api"

# Generate
print("Generating...")
req = urllib.request.Request(f"{BASE}/timetable/generate", data=b'{"clear_existing":true}', method='POST')
req.add_header('Content-Type', 'application/json')
r = urllib.request.urlopen(req, timeout=120)
result = json.loads(r.read())
print(f"Result: {result}")

# Check allocations
print("\nChecking allocations...")
r = urllib.request.urlopen(f"{BASE}/timetable/allocations", timeout=30)
allocs = json.loads(r.read())
print(f"Total: {len(allocs)}")

electives = [a for a in allocs if a.get('is_elective')]
print(f"Electives: {len(electives)}")

if electives:
    by_slot = {}
    for a in electives:
        key = (a['day'], a['slot'])
        if key not in by_slot:
            by_slot[key] = []
        by_slot[key].append(a)
    
    print("\nElective groups by slot:")
    for k in sorted(by_slot.keys()):
        print(f"  Day {k[0]}, Slot {k[1]}: {len(by_slot[k])} classes")
        for a in by_slot[k]:
            print(f"    Sem={a['semester_id']} Sub={a['subject_id']} Teacher={a['teacher_id']}")
