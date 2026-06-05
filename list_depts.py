import sqlite3
conn = sqlite3.connect('backend/timetable.db')
cur = conn.cursor()
cur.execute("SELECT id, name, code FROM departments")
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
