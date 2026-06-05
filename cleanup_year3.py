import sqlite3
conn = sqlite3.connect('backend/timetable.db')
cur = conn.cursor()

# Find subjects that likely belong to Year 3 (CGI13.. or name has 3/III)
# Also includes the orphaned ones I fixed earlier
codes_to_delete = [
    'CGI1356', 'AGB1331', 'AMB1331', 'AMB1332', 
    'CGI1354', 'CGI1355', 'CGI1352', 'CGI1351', 'AMB1331'
]

print(f"Deleting subjects: {codes_to_delete}")

for code in codes_to_delete:
    # First delete related allocations and assignments to avoid FK issues
    cur.execute("SELECT id FROM subjects WHERE code = ?", (code,))
    subject_row = cur.fetchone()
    if subject_row:
        subject_id = subject_row[0]
        cur.execute("DELETE FROM allocations WHERE subject_id = ?", (subject_id,))
        cur.execute("DELETE FROM class_subject_teachers WHERE subject_id = ?", (subject_id,))
        cur.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        print(f"Deleted {code}")

# Also delete any semesters with '3' or 'III' in name
cur.execute("SELECT id, name FROM semesters WHERE name LIKE '%3%' OR name LIKE '%III%' OR code LIKE '%3%'")
sem_rows = cur.fetchall()
for sem_id, sem_name in sem_rows:
    cur.execute("DELETE FROM allocations WHERE semester_id = ?", (sem_id,))
    cur.execute("DELETE FROM class_subject_teachers WHERE semester_id = ?", (sem_id,))
    cur.execute("DELETE FROM semesters WHERE id = ?", (sem_id,))
    print(f"Deleted semester {sem_name}")

conn.commit()
conn.close()
print("Cleanup complete.")
