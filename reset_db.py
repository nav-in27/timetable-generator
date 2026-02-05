"""
Quick Database Reset Script
Deletes the SQLite database file to start fresh.
"""

import os
import glob

print("=" * 60)
print("DATABASE RESET")
print("=" * 60)
print()

# Find and delete all SQLite database files
db_patterns = [
    "backend/timetable*.db",
    "backend/*.db",
    "timetable*.db",
    "*.db"
]

deleted_files = []
for pattern in db_patterns:
    for filepath in glob.glob(pattern):
        try:
            os.remove(filepath)
            deleted_files.append(filepath)
            print(f"  [OK] Deleted: {filepath}")
        except Exception as e:
            print(f"  [WARN] Could not delete {filepath}: {e}")

print()
if deleted_files:
    print("=" * 60)
    print("DATABASE RESET COMPLETE!")
    print("=" * 60)
    print()
    print("All teachers, subjects, and related data have been deleted.")
    print("The database will be recreated on next API request.")
else:
    print("No database files found to delete.")
