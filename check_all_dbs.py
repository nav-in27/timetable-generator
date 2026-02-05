"""Check all database files."""
import sqlite3
import os

db_paths = [
    'timetable.db',
    'backend/timetable.db', 
    'database/timetable.db'
]

for db_path in db_paths:
    print(f"\n{'='*60}")
    print(f"Database: {db_path}")
    print('='*60)
    
    if not os.path.exists(db_path):
        print("  NOT FOUND")
        continue
    
    size = os.path.getsize(db_path)
    print(f"  Size: {size} bytes")
    
    if size == 0:
        print("  EMPTY FILE")
        continue
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"  Tables: {tables}")
        
        if 'subjects' in tables:
            cursor.execute("SELECT COUNT(*) FROM subjects")
            count = cursor.fetchone()[0]
            print(f"  Subjects count: {count}")
            
            # Check for electives
            cursor.execute("SELECT id, code, name, is_elective, subject_type FROM subjects WHERE is_elective=1 OR subject_type='elective'")
            electives = cursor.fetchall()
            print(f"  Electives: {len(electives)}")
            for e in electives:
                print(f"    {e}")
        
        if 'semesters' in tables:
            cursor.execute("SELECT COUNT(*) FROM semesters")
            count = cursor.fetchone()[0]
            print(f"  Semesters count: {count}")
        
        conn.close()
    except Exception as ex:
        print(f"  ERROR: {ex}")
