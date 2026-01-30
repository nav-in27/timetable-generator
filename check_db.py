import sqlite3
import os

db_path = 'backend/timetable.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
try:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='class_subject_teachers'")
    result = cur.fetchone()
    if result:
        print("Table 'class_subject_teachers' EXISTS")
        cur.execute("SELECT COUNT(*) FROM class_subject_teachers")
        print(f"Row count: {cur.fetchone()[0]}")
    else:
        print("Table 'class_subject_teachers' DOES NOT EXIST")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
