import sqlite3
import os

db_path = 'backend/timetable.db'
if not os.path.exists(db_path):
    print(f"File {db_path} not found")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("--- SEMESTERS ---")
cur.execute("SELECT id, name, code FROM semesters")
for r in cur.fetchall():
    if 'AIML' in str(r) or 'AIDS' in str(r):
        print(f"Semester: {r}")

print("\n--- DEPARTMENTS ---")
cur.execute("SELECT id, name, code FROM departments")
for r in cur.fetchall():
    if 'AIML' in str(r) or 'AIDS' in str(r) or 'Artificial' in str(r):
        print(f"Department: {r}")

print("\n--- ALLOCATIONS COUNT ---")
cur.execute("SELECT count(*) FROM allocations")
print(f"Total Allocations: {cur.fetchone()[0]}")

conn.close()
