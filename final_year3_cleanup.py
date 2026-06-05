import sqlite3
import os

DB_PATH = os.path.join("backend", "timetable.db")

def cleanup_year3_final():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("--- Final Cleanup for Year 3 Subjects ---")

    # Find subjects with year 3 indicators
    # 1. Codes with ..13..
    # 2. Name with 'III' or 'Year 3'
    # 3. Known orphans from previous checks
    
    cur.execute("""
        SELECT id, code, name FROM subjects 
        WHERE (code LIKE '___13%') 
        OR (name LIKE '%III%')
        OR (id IN (102, 103, 104))
    """)
    to_delete = cur.fetchall()

    if not to_delete:
        print("No Year 3 subjects found to delete.")
    else:
        print(f"Found {len(to_delete)} subjects:")
        for r in to_delete:
            print(f"  - {r}")
            # Delete related data
            cur.execute("DELETE FROM allocations WHERE subject_id = ?", (r[0],))
            cur.execute("DELETE FROM class_subject_teachers WHERE subject_id = ?", (r[0],))
            cur.execute("DELETE FROM subject_semesters WHERE subject_id = ?", (r[0],))
            cur.execute("DELETE FROM subjects WHERE id = ?", (r[0],))
        print("Deletion successful.")

    # Also check for Year 3 semesters if any left
    cur.execute("SELECT id, name FROM semesters WHERE name LIKE '%III%' OR name LIKE '%Year 3%'")
    sems = cur.fetchall()
    if sems:
        print(f"Found {len(sems)} semesters:")
        for s in sems:
            print(f"  - {s}")
            cur.execute("DELETE FROM allocations WHERE semester_id = ?", (s[0],))
            cur.execute("DELETE FROM semesters WHERE id = ?", (s[0],))
        print("Semesters deleted.")

    conn.commit()
    conn.close()
    print("--- Cleanup Done ---")

if __name__ == "__main__":
    cleanup_year3_final()
