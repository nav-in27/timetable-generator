"""
Fix missing teacher assignments for ALL subjects (Core + Elective) using raw SQL.
This ensures that the generator has valid teacher assignments to work with.
"""
import sqlite3
import random
import os

def fix_missing_teachers():
    # Ensure we are in the right directory or point to the correct DB path
    db_path = 'backend/timetable.db'
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print("Checking for subjects without teachers...")
    
    # Get all subjects
    cur.execute("SELECT id, name, code, is_elective FROM subjects")
    all_subjects = cur.fetchall()
    
    missing_teacher_subjs = []
    
    for subj_id, name, code, is_elective in all_subjects:
        # Check if has teacher
        cur.execute("SELECT count(*) FROM teacher_subjects WHERE subject_id = ?", (subj_id,))
        count = cur.fetchone()[0]
        
        if count == 0:
            missing_teacher_subjs.append((subj_id, name, code, is_elective))
            
    if not missing_teacher_subjs:
        print("  All subjects have teachers assigned!")
        conn.close()
        return

    print(f"Found {len(missing_teacher_subjs)} subjects missing teachers.")

    # Get all active teachers
    # Check if is_active column exists
    try:
        cur.execute("SELECT id, name FROM teachers WHERE is_active = 1")
    except sqlite3.OperationalError:
        # Fallback if is_active column doesn't exist or other schema issue
        cur.execute("SELECT id, name FROM teachers")
        
    teachers = cur.fetchall()
    
    if not teachers:
        print("CRITICAL: No teachers in database!")
        conn.close()
        return

    print(f"Found {len(teachers)} teachers available for assignment.")
    
    assigned_count = 0
    t_idx = 0
    
    # Shuffle teachers to distribute load
    random.shuffle(teachers)
    
    for i, (subj_id, name, code, is_elective) in enumerate(missing_teacher_subjs):
        # Pick a teacher (round robin)
        teacher = teachers[t_idx % len(teachers)]
        t_idx += 1
        t_id, t_name = teacher
        
        type_str = "Elective" if is_elective else "Core"
        if i < 5 or i >= len(missing_teacher_subjs) - 5:
            print(f"  Assigning {t_name} to {type_str} Subject: {code}")
        elif i == 5:
            print(f"  ... and {len(missing_teacher_subjs) - 10} more ...")
        
        # Insert
        try:
            cur.execute("INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (?, ?)", (t_id, subj_id))
            assigned_count += 1
        except Exception as e:
            print(f"  Error assigning: {e}")
            
    conn.commit()
    print(f"Successfully assigned teachers to {assigned_count} subjects.")
    conn.close()

if __name__ == "__main__":
    fix_missing_teachers()
