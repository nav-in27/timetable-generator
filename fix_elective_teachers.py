"""
Fix missing teacher assignments for electives using raw SQL to avoid ORM issues.
"""
import sqlite3
import random

def fix_teachers_raw():
    db_path = 'backend/timetable.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print("Checking for electives without teachers...")
    
    # Get electives (is_elective=1)
    cur.execute("SELECT id, name, code FROM subjects WHERE is_elective = 1")
    electives = cur.fetchall()
    
    missing_teacher_subjs = []
    
    for subj_id, name, code in electives:
        # Check if has teacher
        cur.execute("SELECT count(*) FROM teacher_subjects WHERE subject_id = ?", (subj_id,))
        count = cur.fetchone()[0]
        
        if count == 0:
            missing_teacher_subjs.append((subj_id, name, code))
            print(f"  Found missing teacher for: {code} - {name}")
            
    if not missing_teacher_subjs:
        print("  All electives have teachers!")
        conn.close()
        return

    # Get all teachers
    cur.execute("SELECT id, name FROM teachers")
    teachers = cur.fetchall()
    
    if not teachers:
        print("CRITICAL: No teachers in database!")
        conn.close()
        return

    print(f"Found {len(teachers)} teachers available.")
    
    import random
    assigned_count = 0
    
    for subj_id, name, code in missing_teacher_subjs:
        # Pick a random teacher
        teacher = random.choice(teachers)
        t_id, t_name = teacher
        
        print(f"  Assigning {t_name} to {code}")
        
        # Insert
        try:
            cur.execute("INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (?, ?)", (t_id, subj_id))
            assigned_count += 1
        except Exception as e:
            print(f"  Error assigning: {e}")
            
    conn.commit()
    print(f"Successfully assigned teachers to {assigned_count} electives.")
    conn.close()

if __name__ == "__main__":
    fix_teachers_raw()
