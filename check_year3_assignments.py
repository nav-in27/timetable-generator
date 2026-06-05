import sqlite3
conn = sqlite3.connect('backend/timetable.db')
cur = conn.cursor()
cur.execute("""
    SELECT s.name, sub.name, t.name 
    FROM class_subject_teachers cst 
    JOIN semesters s ON cst.semester_id = s.id 
    JOIN subjects sub ON cst.subject_id = sub.id 
    JOIN teachers t ON cst.teacher_id = t.id 
    WHERE s.code LIKE '%3%' OR s.name LIKE '%3%'
""")
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
