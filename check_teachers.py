"""Check elective teacher assignments."""
import sqlite3
conn = sqlite3.connect('backend/timetable.db')
cur = conn.cursor()

print("ELECTIVE-TEACHER ASSIGNMENTS:")
print("="*50)

cur.execute("SELECT id, code, name FROM subjects WHERE is_elective = 1")
electives = cur.fetchall()

issues = []
for subj_id, code, name in electives:
    cur.execute("SELECT teacher_id FROM teacher_subjects WHERE subject_id = ?", (subj_id,))
    teachers = cur.fetchall()
    if teachers:
        for t in teachers:
            cur.execute("SELECT name FROM teachers WHERE id = ?", (t[0],))
            tname = cur.fetchone()
            print(f"  {code} -> {tname[0] if tname else 'Unknown'}")
    else:
        print(f"  {code} -> *** NO TEACHER ASSIGNED ***")
        issues.append(code)

print()
if issues:
    print("*** CRITICAL: These electives have NO teachers and CANNOT be scheduled! ***")
    print(f"   Missing teachers for: {issues}")
else:
    print("All electives have teachers assigned.")
