"""Check database tables."""
import sqlite3
import os

db_path = 'database/timetable.db'
print(f"Database path: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"\nTables in database: {tables}")
    
    if 'subjects' in tables:
        cursor.execute("PRAGMA table_info(subjects)")
        cols = cursor.fetchall()
        print(f"\nSubjects columns:")
        for col in cols:
            print(f"  {col[1]} ({col[2]})")
    
    if 'semesters' in tables:
        cursor.execute("PRAGMA table_info(semesters)")
        cols = cursor.fetchall()
        print(f"\nSemesters columns:")
        for col in cols:
            print(f"  {col[1]} ({col[2]})")
    
    conn.close()
else:
    print("Database not found!")
