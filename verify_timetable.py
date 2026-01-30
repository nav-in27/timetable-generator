"""
Verify Timetable Generation Logic:
1. Triggers Generation via API
2. Verifies Success (Total Allocations)
3. Verifies Elective Synchronization across Sections
4. Verifies Subject Variety (No vertical stacking)
"""
import urllib.request
import json
import sqlite3
import collections

BASE_URL = "http://localhost:8000"
DB_PATH = "backend/timetable.db"

def get_db_metadata():
    """Fetch semester groupings and subject info from DB."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Map semester_id -> {name, semester_number}
    cur.execute("SELECT id, name, semester_number FROM semesters")
    sem_map = {}
    sem_groups = collections.defaultdict(list)
    for sid, name, num in cur.fetchall():
        sem_map[sid] = {"name": name, "num": num}
        sem_groups[num].append(sid)
        
    # Map subject_id -> {code, is_elective}
    cur.execute("SELECT id, code, is_elective, subject_type, elective_basket_id FROM subjects")
    subj_map = {}
    for sid, code, is_elec, stype, basket in cur.fetchall():
        # strict is_elective check or implicit via type
        is_real_elective = (is_elec == 1) or (stype == 'elective') or (basket is not None)
        subj_map[sid] = {"code": code, "is_elective": is_real_elective}
        
    conn.close()
    return sem_map, sem_groups, subj_map

def trigger_generation():
    """Call generate endpoint."""
    url = f"{BASE_URL}/api/timetable/generate"
    print(f"Triggering generation at {url}...")
    
    # clear_existing=True is default
    data = json.dumps({"clear_existing": True}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result
    except Exception as e:
        print(f"Generation Failed: {e}")
        return None

def fetch_allocations():
    """Fetch all allocations."""
    url = f"{BASE_URL}/api/timetable/allocations"
    print(f"Fetching allocations from {url}...")
    
    try:
        with urllib.request.urlopen(url) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result
    except Exception as e:
        print(f"Fetch Allocations Failed: {e}")
        return []

def verify_logic():
    print("="*60)
    print("VERIFYING TIMETABLE LOGIC")
    print("="*60)
    
    # 1. Get Metadata
    sem_map, sem_groups, subj_map = get_db_metadata()
    print(f"Metadata: Found {len(sem_map)} semesters, {len(subj_map)} subjects.")
    
    # 2. Trigger Generation
    gen_result = trigger_generation()
    if not gen_result:
        print("CRITICAL: Generation failed (API error).")
        return
        
    print(f"Generation Result: {gen_result.get('message')}")
    total_allocs = gen_result.get('total_allocations', 0)
    print(f"Total Allocations: {total_allocs}")
    
    if total_allocs == 0:
        print("CRITICAL: Generated 0 allocations. Something is blocked.")
        return

    # 3. Fetch Data
    allocations = fetch_allocations()
    print(f"Fetched {len(allocations)} allocations for verification.")
    
    # 4. Verify Elective Sync
    print("\n[CHECK 1] Elective Synchronization")
    # Group allocations by semester_number -> slot -> set of section_ids having elective
    # Key: (SemesterYear, Day, Slot) -> Set of Sections(sem_ids)
    elective_slots = collections.defaultdict(set)
    
    elective_count = 0
    
    for alloc in allocations:
        sid = alloc['subject_id']
        sem_id = alloc['semester_id']
        day = alloc['day']
        slot = alloc['slot']
        
        # Check if elective
        subj_info = subj_map.get(sid)
        if not subj_info: continue
        
        if subj_info['is_elective']:
            elective_count += 1
            sem_num = sem_map[sem_id]['num']
            # Key: (SemesterYear, Day, Slot) -> Set of Sections(sem_ids)
            elective_slots[(sem_num, day, slot)].add(sem_id)

    print(f"Found {elective_count} elective slots scheduled.")

    if elective_count == 0:
        print("WARNING: No electives scheduled! Check teacher assignments.")
    else:
        # Check specific years (Sem 4 and Sem 6 are the main ones)
        for sem_num in [4, 6]:
            sections = sem_groups.get(sem_num, [])
            if not sections: continue
            
            print(f"  Checking Year {sem_num//2} (Semester {sem_num}) - Sections: {len(sections)}")
            
            # Find slots where AT LEAST ONE section has elective
            relevant_slots = [k for k in elective_slots.keys() if k[0] == sem_num]
            if not relevant_slots:
                print(f"    No electives found for Semester {sem_num}.")
                continue
                
            synced_slots = 0
            unsynced_slots = 0
            
            for key in relevant_slots:
                sections_with_elective = elective_slots[key]
                # Check if ALL sections have it
                missing = [s for s in sections if s not in sections_with_elective]
                
                if not missing:
                    synced_slots += 1
                else:
                    unsynced_slots += 1
                    # print(f"    Unsynced Slot {key[1:]}: Missing {missing}")
            
            if unsynced_slots == 0:
                print(f"    SUCCESS: All {synced_slots} elective slots are fully synchronized across all {len(sections)} sections!")
            else:
                print(f"    WARNING: {synced_slots} synced, {unsynced_slots} unsynced slots.")

    # 5. Verify Variety (No Vertical Stacking)
    print("\n[CHECK 2] Subject Variety (Vertical Stacking Check)")
    # For each (semester, subject), count how many times it appears in same slot index
    # stack_counts: (sem, subj) -> {slot_index: count}
    stack_counts = collections.defaultdict(lambda: collections.defaultdict(int))
    
    for alloc in allocations:
        sem_id = alloc['semester_id']
        sid = alloc['subject_id']
        slot = alloc['slot']
        
        # Only check Core subjects (Electives are fixed slots usually)
        subj_info = subj_map.get(sid)
        if subj_info and not subj_info['is_elective']:
             stack_counts[(sem_id, sid)][slot] += 1
             
    # Analyze
    high_stacking = 0
    total_subjects = 0
    
    for (sem, subj), slots in stack_counts.items():
        total_subjects += 1
        # If any slot has > 2 occurrences (e.g. Mon, Tue, Wed all Period 1) -> Stacking
        max_reps = max(slots.values())
        if max_reps > 2:
            high_stacking += 1
            # print(f"  High Repetition: Sem {sem}, Subj {subj_map[subj]['code']} appears {max_reps} times in same slot.")
            
    pct_stacking = (high_stacking / total_subjects) * 100 if total_subjects else 0
    print(f"  Analyzed {total_subjects} core subject assignments.")
    print(f"  Subjects with High Repetition (>2 days at same time): {high_stacking} ({pct_stacking:.1f}%)")
    
    if pct_stacking < 20: # Arbitrary threshold, 0 is ideal but some might happen due to constraints
        print("  SUCCESS: Variety logic is working. Vertical stacking is minimized.")
    else:
        print("  WARNING: Significant vertical stacking detected.")
        
    print("="*60)
    print("VERIFICATION COMPLETE")
    print("="*60)
    
    # Save brief summary
    with open("verification_summary.txt", "w", encoding="utf-8") as f:
        f.write(f"Total Allocations: {total_allocs}\n")
        f.write(f"Elective Slots Found: {elective_count}\n")
        if elective_count > 0:
            f.write("Elective Sync: CHECKED\n")
        else:
             f.write("Elective Sync: FAILED (0 electives)\n")
        f.write(f"Subjects with High Repetition: {high_stacking} ({pct_stacking:.1f}%)\n")
        if pct_stacking < 20:
            f.write("Variety Status: SUCCESS (Minimized Vertical Stacking)\n")
        else:
            f.write("Variety Status: WARNING (Vertical Stacking Detected)\n")

if __name__ == "__main__":
    verify_logic()
