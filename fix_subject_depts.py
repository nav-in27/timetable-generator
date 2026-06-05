import sqlite3
import os

# Path to the database
DB_PATH = os.path.join("backend", "timetable.db")

def fix_orphaned_subjects():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("--- Fixing Orphaned Subjects (Missing dept_id) ---")

    # 1. Update subjects that have assigned semesters
    # We'll assign the dept_id of one of its assigned semesters
    cur.execute("""
        UPDATE subjects
        SET dept_id = (
            SELECT sem.dept_id 
            FROM subject_semesters ss
            JOIN semesters sem ON ss.semester_id = sem.id
            WHERE ss.subject_id = subjects.id
            LIMIT 1
        )
        WHERE dept_id IS NULL 
        AND EXISTS (
            SELECT 1 FROM subject_semesters WHERE subject_id = subjects.id
        )
    """)
    print(f"Updated {cur.rowcount} subjects based on semester assignments.")

    # 2. Hard-code specific AI/ML subjects if still orphaned
    # Search for common prefixes or keywords
    patterns = [
        ('%Deep Learning%', 3),
        ('%Web App%', 3),
        ('%Data Science%', 3),
        ('%AIML%', 2),
        ('%AI&DS%', 3)
    ]

    for pattern, dept_id in patterns:
        cur.execute("UPDATE subjects SET dept_id = ? WHERE dept_id IS NULL AND (name LIKE ? OR code LIKE ?)", 
                    (dept_id, pattern, pattern))
        if cur.rowcount > 0:
            print(f"Applied pattern '{pattern}' -> Dept {dept_id}: {cur.rowcount} subjects.")

    # 3. Check for any remaining orphans
    cur.execute("SELECT id, code, name FROM subjects WHERE dept_id IS NULL")
    remaining = cur.fetchall()
    if remaining:
        print("\nRemaining Orphaned Subjects:")
        for r in remaining:
            print(f"  - {r}")
            # Default to Dept 3 (AI&DS) as a fallback since the user is likely working there
            cur.execute("UPDATE subjects SET dept_id = 3 WHERE id = ?", (r[0],))
        print(f"Defaulted {len(remaining)} remaining subjects to Dept 3.")

    conn.commit()
    conn.close()
    print("\n--- Done ---")

if __name__ == "__main__":
    fix_orphaned_subjects()
