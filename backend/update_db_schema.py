import os
import sqlite3

# Always resolve the DB path relative to this file to avoid cwd surprises.
DB_PATH = os.path.join(os.path.dirname(__file__), "timetable.db")


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _get_columns(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [info[1] for info in cursor.fetchall()]


def _index_exists(cursor: sqlite3.Cursor, index_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=? LIMIT 1",
        (index_name,),
    )
    return cursor.fetchone() is not None


def update_schema():
    """
    Backward-compatible schema updater for SQLite deployments.

    Safety properties:
    - Never deletes data
    - Best-effort: skips missing tables/columns and never raises to caller
    """
    if not os.path.exists(DB_PATH):
        print(f"[WARN] Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. teachers: Add teacher_code
    try:
        if _table_exists(cursor, "teachers"):
            columns = _get_columns(cursor, "teachers")
            if "teacher_code" not in columns:
                print("Adding teacher_code to teachers table...")
                cursor.execute("ALTER TABLE teachers ADD COLUMN teacher_code TEXT")

                # Populate teacher_code for existing rows (best-effort)
                cursor.execute("SELECT id FROM teachers")
                start_teachers = cursor.fetchall()
                for (t_id,) in start_teachers:
                    code = f"T{t_id:03d}"
                    cursor.execute("UPDATE teachers SET teacher_code = ? WHERE id = ?", (code, t_id))
                print(f"Updated {len(start_teachers)} teachers with codes.")
            else:
                print("teacher_code already exists in teachers.")
        else:
            print("[WARN] teachers table not found; skipping teacher_code migration.")
    except Exception as e:
        print(f"[WARN] teachers migration skipped due to error: {e}")

    # 2. subjects: Add year
    try:
        if _table_exists(cursor, "subjects"):
            columns = _get_columns(cursor, "subjects")
            if "year" not in columns:
                print("Adding year to subjects table...")
                cursor.execute("ALTER TABLE subjects ADD COLUMN year INTEGER")

                # Populate year based on semester (best-effort, preserves existing data)
                cursor.execute("SELECT id, semester FROM subjects")
                start_subjects = cursor.fetchall()
                for (s_id, sem) in start_subjects:
                    # Year 1: Sem 1,2. Year 2: Sem 3,4...
                    if not sem:
                        y = 1
                    else:
                        y = (sem + 1) // 2
                    cursor.execute("UPDATE subjects SET year = ? WHERE id = ?", (y, s_id))
                print(f"Updated {len(start_subjects)} subjects with year.")
            else:
                print("year already exists in subjects.")
        else:
            print("[WARN] subjects table not found; skipping year migration.")
    except Exception as e:
        print(f"[WARN] subjects(year) migration skipped due to error: {e}")

    # 3. subjects: Add extended component fields (optional)
    try:
        if _table_exists(cursor, "subjects"):
            columns = _get_columns(cursor, "subjects")

            subject_new_columns = [
                ("project_hours_per_week", "INTEGER", 0),
                ("project_block_size", "INTEGER", 1),
                ("report_hours_per_week", "INTEGER", 0),
                ("report_block_size", "INTEGER", 1),
                ("self_study_hours_per_week", "INTEGER", 0),
                ("seminar_hours_per_week", "INTEGER", 0),
                ("seminar_block_size", "INTEGER", 2),
                ("seminar_day_based", "BOOLEAN", 0),
            ]

            for col_name, col_type, default_value in subject_new_columns:
                if col_name not in columns:
                    print(f"Adding {col_name} to subjects table...")
                    cursor.execute(
                        f"ALTER TABLE subjects ADD COLUMN {col_name} {col_type} DEFAULT {default_value}"
                    )
        else:
            print("[WARN] subjects table not found; skipping extended component migrations.")
    except Exception as e:
        print(f"[WARN] subjects(extended) migration skipped due to error: {e}")

    # 4. allocations: Add academic_component label (optional)
    try:
        if _table_exists(cursor, "allocations"):
            alloc_columns = _get_columns(cursor, "allocations")
            if "academic_component" not in alloc_columns:
                print("Adding academic_component to allocations table...")
                cursor.execute("ALTER TABLE allocations ADD COLUMN academic_component TEXT")
            else:
                print("academic_component already exists in allocations.")
        else:
            print("[WARN] allocations table not found; skipping academic_component migration.")
    except Exception as e:
        print(f"[WARN] allocations migration skipped due to error: {e}")

    # 5. fixed_slots: Add academic_component label (optional)
    try:
        if _table_exists(cursor, "fixed_slots"):
            fixed_columns = _get_columns(cursor, "fixed_slots")
            if "academic_component" not in fixed_columns:
                print("Adding academic_component to fixed_slots table...")
                cursor.execute("ALTER TABLE fixed_slots ADD COLUMN academic_component TEXT")
            else:
                print("academic_component already exists in fixed_slots.")
        else:
            print("[WARN] fixed_slots table not found; skipping academic_component migration.")
    except Exception as e:
        print(f"[WARN] fixed_slots migration skipped due to error: {e}")

    # 6. rooms: Ensure dept_id exists (optional)
    try:
        if _table_exists(cursor, "rooms"):
            room_columns = _get_columns(cursor, "rooms")
            if "dept_id" not in room_columns:
                print("Adding dept_id to rooms table...")
                cursor.execute("ALTER TABLE rooms ADD COLUMN dept_id INTEGER")
            else:
                print("dept_id already exists in rooms.")
        else:
            print("[WARN] rooms table not found; skipping dept_id migration.")
    except Exception as e:
        print(f"[WARN] rooms migration skipped due to error: {e}")

    # 7. semesters: Ensure dept_id exists (optional)
    try:
        if _table_exists(cursor, "semesters"):
            sem_columns = _get_columns(cursor, "semesters")
            if "dept_id" not in sem_columns:
                print("Adding dept_id to semesters table...")
                cursor.execute("ALTER TABLE semesters ADD COLUMN dept_id INTEGER")
            else:
                print("dept_id already exists in semesters.")
        else:
            print("[WARN] semesters table not found; skipping dept_id migration.")
    except Exception as e:
        print(f"[WARN] semesters migration skipped due to error: {e}")

    # 8. class_subject_teachers: Add room_id for component room preference (optional)
    try:
        if _table_exists(cursor, "class_subject_teachers"):
            cst_columns = _get_columns(cursor, "class_subject_teachers")
            if "room_id" not in cst_columns:
                print("Adding room_id to class_subject_teachers table...")
                cursor.execute("ALTER TABLE class_subject_teachers ADD COLUMN room_id INTEGER")
            else:
                print("room_id already exists in class_subject_teachers.")

            if "parallel_lab_group" not in cst_columns:
                print("Adding parallel_lab_group to class_subject_teachers table...")
                cursor.execute("ALTER TABLE class_subject_teachers ADD COLUMN parallel_lab_group TEXT")
            else:
                print("parallel_lab_group already exists in class_subject_teachers.")

            if "batch_id" not in cst_columns:
                print("Adding batch_id to class_subject_teachers table...")
                cursor.execute("ALTER TABLE class_subject_teachers ADD COLUMN batch_id INTEGER")
            else:
                print("batch_id already exists in class_subject_teachers.")

        else:
            print("[WARN] class_subject_teachers table not found; skipping room_id/parallel/batch migration.")
    except Exception as e:
        print(f"[WARN] class_subject_teachers migration skipped due to error: {e}")

    # 9. allocations: Add batch_id (optional)
    try:
        if _table_exists(cursor, "allocations"):
            alloc_columns = _get_columns(cursor, "allocations")
            if "batch_id" not in alloc_columns:
                print("Adding batch_id to allocations table...")
                cursor.execute("ALTER TABLE allocations ADD COLUMN batch_id INTEGER")
            else:
                print("batch_id already exists in allocations.")
        else:
            print("[WARN] allocations table not found; skipping batch_id migration.")
    except Exception as e:
        print(f"[WARN] allocations batch_id migration skipped due to error: {e}")

    # 10. rooms: Add section-wise assignment columns (optional)
    try:
        if _table_exists(cursor, "rooms"):
            room_columns = _get_columns(cursor, "rooms")
            section_cols = [
                ("assigned_year", "INTEGER", None),
                ("assigned_section", "TEXT", None),
                ("is_default_classroom", "BOOLEAN", 0),
            ]
            for col_name, col_type, default_value in section_cols:
                if col_name not in room_columns:
                    default_clause = f" DEFAULT {default_value}" if default_value is not None else ""
                    print(f"Adding {col_name} to rooms table...")
                    cursor.execute(
                        f"ALTER TABLE rooms ADD COLUMN {col_name} {col_type}{default_clause}"
                    )
                else:
                    print(f"{col_name} already exists in rooms.")
        else:
            print("[WARN] rooms table not found; skipping section assignment migration.")
    except Exception as e:
        print(f"[WARN] rooms section assignment migration skipped due to error: {e}")

    # 11. Create room_departments junction table (multi-department rooms)
    try:
        if not _table_exists(cursor, "room_departments"):
            print("Creating room_departments junction table...")
            cursor.execute("""
                CREATE TABLE room_departments (
                    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    dept_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                    PRIMARY KEY (room_id, dept_id)
                )
            """)
            # Migrate existing dept_id values from rooms into the junction table
            if _table_exists(cursor, "rooms"):
                cursor.execute("SELECT id, dept_id FROM rooms WHERE dept_id IS NOT NULL")
                migrated = 0
                for (room_id, dept_id) in cursor.fetchall():
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO room_departments (room_id, dept_id) VALUES (?, ?)",
                            (room_id, dept_id)
                        )
                        migrated += 1
                    except Exception:
                        pass
                if migrated:
                    print(f"Migrated {migrated} existing room-department links.")
        else:
            print("room_departments table already exists.")
    except Exception as e:
        print(f"[WARN] room_departments migration skipped due to error: {e}")

    # 12. subjects: Add academic importance fields (optional, backward-compatible)
    try:
        if _table_exists(cursor, "subjects"):
            columns = _get_columns(cursor, "subjects")

            importance_columns = [
                ("importance_level", "TEXT", "'NORMAL'"),
                ("previous_year_pass_percentage", "INTEGER", None),
                ("computed_priority_score", "INTEGER", "0"),
            ]

            for col_name, col_type, default_value in importance_columns:
                if col_name not in columns:
                    default_clause = f" DEFAULT {default_value}" if default_value is not None else ""
                    print(f"Adding {col_name} to subjects table...")
                    cursor.execute(
                        f"ALTER TABLE subjects ADD COLUMN {col_name} {col_type}{default_clause}"
                    )
                else:
                    print(f"{col_name} already exists in subjects.")
        else:
            print("[WARN] subjects table not found; skipping importance migration.")
    except Exception as e:
        print(f"[WARN] subjects importance migration skipped due to error: {e}")

    # 13. class_subject_teachers: append-mode duplicate guard index (no data deletion)
    try:
        if _table_exists(cursor, "class_subject_teachers"):
            index_name = "uq_cst_teacher_sem_subj_comp_batch_idx"

            # Do not create index if exact duplicate rows already exist.
            cursor.execute(
                """
                SELECT teacher_id, semester_id, subject_id, component_type, IFNULL(batch_id, -1), COUNT(*) AS cnt
                FROM class_subject_teachers
                GROUP BY teacher_id, semester_id, subject_id, component_type, IFNULL(batch_id, -1)
                HAVING cnt > 1
                LIMIT 1
                """
            )
            duplicate_row = cursor.fetchone()

            if duplicate_row:
                print(
                    "[WARN] Skipping append-mode unique index creation because duplicate "
                    "rows already exist. No rows were deleted."
                )
            elif not _index_exists(cursor, index_name):
                print("Creating append-mode unique index on class_subject_teachers...")
                cursor.execute(
                    f"""
                    CREATE UNIQUE INDEX {index_name}
                    ON class_subject_teachers
                    (teacher_id, semester_id, subject_id, component_type, IFNULL(batch_id, -1))
                    """
                )
            else:
                print("append-mode unique index already exists on class_subject_teachers.")
        else:
            print("[WARN] class_subject_teachers table not found; skipping append-mode index migration.")
    except Exception as e:
        print(f"[WARN] append-mode class_subject_teachers index migration skipped due to error: {e}")

    # 14. Create subject_departments junction table (multi-department subjects)
    try:
        if not _table_exists(cursor, "subject_departments"):
            print("Creating subject_departments junction table...")
            cursor.execute("""
                CREATE TABLE subject_departments (
                    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                    dept_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                    PRIMARY KEY (subject_id, dept_id)
                )
            """)
            # Migrate existing dept_id values from subjects into the junction table
            if _table_exists(cursor, "subjects"):
                cursor.execute("SELECT id, dept_id FROM subjects WHERE dept_id IS NOT NULL")
                migrated = 0
                for (subject_id, dept_id) in cursor.fetchall():
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO subject_departments (subject_id, dept_id) VALUES (?, ?)",
                            (subject_id, dept_id)
                        )
                        migrated += 1
                    except Exception:
                        pass
                if migrated:
                    print(f"Migrated {migrated} existing subject-department links.")
        else:
            print("subject_departments table already exists.")
    except Exception as e:
        print(f"[WARN] subject_departments migration skipped due to error: {e}")

    try:
        conn.commit()
    finally:
        conn.close()
    print("Schema update completed.")

if __name__ == "__main__":
    update_schema()
