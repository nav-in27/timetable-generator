"""
Fix specific subject hours layout.
Target: Business Communication (GEA1211) -> Only Lab.
"""
import sqlite3
import os

def fix_subject():
    db_path = 'backend/timetable.db'
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print("Checking Subject GEA1211...")
    cur.execute("SELECT id, name, theory_hours_per_week, lab_hours_per_week, weekly_hours FROM subjects WHERE code = 'GEA1211'")
    row = cur.fetchone()
    
    if not row:
        print("Subject not found!")
        conn.close()
        return
        
    sid, name, theory, lab, weekly = row
    print(f"Current State: {name} (ID {sid})")
    print(f"  Theory: {theory}h")
    print(f"  Lab: {lab}h")
    print(f"  Weekly: {weekly}h")
    
    # Target: Theory=0, Lab=4 (or keep Lab as is if > 0)
    new_theory = 0
    new_lab = lab if lab > 0 else 4 # Default to 4 if somehow 0
    new_weekly = new_theory + new_lab
    
    if theory != new_theory:
        print(f"Updating to: Theory={new_theory}h, Lab={new_lab}h, Weekly={new_weekly}h")
        cur.execute("""
            UPDATE subjects 
            SET theory_hours_per_week = ?, 
                lab_hours_per_week = ?,
                weekly_hours = ? 
            WHERE id = ?
        """, (new_theory, new_lab, new_weekly, sid))
        conn.commit()
        print("Update Successful.")
    else:
        print("Subject already has 0 Theory hours.")
        
    conn.close()

if __name__ == "__main__":
    fix_subject()
