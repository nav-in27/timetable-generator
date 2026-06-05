import sqlite3
conn = sqlite3.connect('backend/timetable.db')
cur = conn.cursor()
print("Searching for subjects with 'Web' in name or code...")
cur.execute("SELECT id, code, name, dept_id FROM subjects WHERE name LIKE '%Web%' OR code LIKE '%Web%'")
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
