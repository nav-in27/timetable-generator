"""Check elective mappings in backend database."""
import sqlite3
import os

db_path = 'backend/timetable.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 60)
print("ELECTIVE SUBJECTS")
print("=" * 60)

cursor.execute("""
    SELECT id, code, name, weekly_hours, theory_hours_per_week, is_elective, subject_type 
    FROM subjects 
    WHERE is_elective=1 OR subject_type='elective' OR subject_type='ELECTIVE'
""")
electives = cursor.fetchall()
print(f"Found {len(electives)} electives:\n")

for e in electives:
    print(f"  ID={e[0]}: {e[1]} - {e[2]}")
    print(f"    weekly_hours={e[3]}, theory={e[4]}, is_elective={e[5]}, type={e[6]}")

# Check semester assignments (subject_semesters)
print("\n" + "=" * 60)
print("ELECTIVE-CLASS ASSIGNMENTS (subject_semesters)")
print("=" * 60)

elective_ids = [e[0] for e in electives]
for eid in elective_ids:
    cursor.execute("SELECT semester_id FROM subject_semesters WHERE subject_id=?", (eid,))
    sems = cursor.fetchall()
    
    cursor.execute("SELECT code FROM subjects WHERE id=?", (eid,))
    code = cursor.fetchone()[0]
    
    print(f"\n  {code}: Assigned to semesters {[s[0] for s in sems]}")
    
    for (sem_id,) in sems:
        cursor.execute("SELECT name, semester_number FROM semesters WHERE id=?", (sem_id,))
        sem_info = cursor.fetchone()
        if sem_info:
            print(f"    -> {sem_info[0]} (Year {sem_info[1]})")

# Check ClassSubjectTeacher for electives
print("\n" + "=" * 60)
print("ELECTIVE TEACHER ASSIGNMENTS (class_subject_teachers)")
print("=" * 60)

for eid in elective_ids:
    cursor.execute("""
        SELECT cst.semester_id, cst.subject_id, cst.component_type, cst.teacher_id, t.name
        FROM class_subject_teachers cst
        LEFT JOIN teachers t ON t.id = cst.teacher_id
        WHERE cst.subject_id=?
    """, (eid,))
    csts = cursor.fetchall()
    
    cursor.execute("SELECT code FROM subjects WHERE id=?", (eid,))
    code = cursor.fetchone()[0]
    
    print(f"\n  {code}:")
    if csts:
        for c in csts:
            cursor.execute("SELECT name FROM semesters WHERE id=?", (c[0],))
            sem_name = cursor.fetchone()
            print(f"    Sem={sem_name[0] if sem_name else c[0]}, Type={c[2]}, Teacher={c[4] or c[3]}")
    else:
        print("    *** NO TEACHER ASSIGNMENTS! ***")

# Check teacher_subjects for electives
print("\n" + "=" * 60)
print("ELECTIVE TEACHER CAPABILITY (teacher_subjects)")
print("=" * 60)

for eid in elective_ids:
    cursor.execute("""
        SELECT ts.teacher_id, t.name
        FROM teacher_subjects ts
        LEFT JOIN teachers t ON t.id = ts.teacher_id
        WHERE ts.subject_id=?
    """, (eid,))
    teachers = cursor.fetchall()
    
    cursor.execute("SELECT code FROM subjects WHERE id=?", (eid,))
    code = cursor.fetchone()[0]
    
    print(f"\n  {code}:")
    if teachers:
        for t in teachers:
            print(f"    Teacher: {t[1]} (ID={t[0]})")
    else:
        print("    *** NO TEACHERS CAN TEACH THIS! ***")

# Check semesters by year
print("\n" + "=" * 60)
print("SEMESTERS BY YEAR")
print("=" * 60)

cursor.execute("SELECT id, name, semester_number FROM semesters ORDER BY semester_number")
semesters = cursor.fetchall()
for s in semesters:
    print(f"  ID={s[0]}: {s[1]} (Year {s[2]})")

conn.close()
