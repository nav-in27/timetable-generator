"""
Startup repair and database health check.

Runs automatically on application boot to:
1. Add missing performance indexes
2. Clean up orphan rows (broken foreign keys)
3. Remove duplicate mappings
4. Validate and repair referential integrity
5. Rebuild stale counters

All operations are idempotent and safe to run on every startup.
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("app.startup_repair")


# ============================================================================
# INDEX DEFINITIONS - high-frequency lookup patterns
# ============================================================================

_INDEXES = [
    # Teachers
    ("ix_teachers_teacher_code", "teachers", "teacher_code"),
    ("ix_teachers_dept_active", "teachers", "dept_id, is_active"),

    # Subjects
    ("ix_subjects_code", "subjects", "code"),
    ("ix_subjects_dept_id", "subjects", "dept_id"),
    ("ix_subjects_elective_basket", "subjects", "elective_basket_id"),

    # Semesters (classes)
    ("ix_semesters_dept_id", "semesters", "dept_id"),
    ("ix_semesters_code", "semesters", "code"),
    ("ix_semesters_year_section", "semesters", "year, section"),

    # Rooms
    ("ix_rooms_room_type", "rooms", "room_type"),
    ("ix_rooms_dept_available", "rooms", "dept_id, is_available"),

    # Allocations - critical for timetable views
    ("ix_alloc_semester_day_slot", "allocations", "semester_id, day, slot"),
    ("ix_alloc_teacher_day_slot", "allocations", "teacher_id, day, slot"),
    ("ix_alloc_room_day_slot", "allocations", "room_id, day, slot"),
    ("ix_alloc_subject", "allocations", "subject_id"),

    # ClassSubjectTeacher - teacher assignment lookups
    ("ix_cst_semester_subject", "class_subject_teachers", "semester_id, subject_id"),
    ("ix_cst_teacher_semester", "class_subject_teachers", "teacher_id, semester_id"),
    ("ix_cst_subject_component", "class_subject_teachers", "subject_id, component_type"),

    # Fixed slots
    ("ix_fixed_semester_day_slot", "fixed_slots", "semester_id, day, slot"),

    # Substitutions
    ("ix_subs_date_status", "substitutions", "substitution_date, status"),
    ("ix_subs_allocation", "substitutions", "allocation_id"),

    # Teacher absences
    ("ix_absences_teacher_date", "teacher_absences", "teacher_id, absence_date"),

    # Subject-Semester mapping
    ("ix_subj_sem_subject", "subject_semesters", "subject_id"),
    ("ix_subj_sem_semester", "subject_semesters", "semester_id"),

    # Teacher-Subject mapping
    ("ix_teacher_subj_teacher", "teacher_subjects", "teacher_id"),
    ("ix_teacher_subj_subject", "teacher_subjects", "subject_id"),

    # Elective baskets
    ("ix_eb_semester_number", "elective_baskets", "semester_number"),

    # SCB subjects
    ("ix_scb_subj_basket", "scb_subjects", "basket_id"),
    ("ix_scb_subj_subject", "scb_subjects", "subject_id"),

    # Parallel lab basket subjects
    ("ix_plbs_basket", "parallel_lab_basket_subjects", "basket_id"),
]


def _ensure_indexes(db: Session):
    """Create missing indexes. Idempotent - skips if index already exists."""
    created = 0
    for idx_name, table, columns in _INDEXES:
        try:
            db.execute(text(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns})"
            ))
            created += 1
        except Exception as e:
            # Table might not exist yet or column missing - skip
            err_str = str(e).lower()
            if "no such table" in err_str or "no such column" in err_str:
                continue
            logger.debug(f"Index {idx_name} skip: {e}")
    db.commit()
    if created > 0:
        logger.info(f"Ensured {created} database indexes")


def _clean_orphan_allocations(db: Session):
    """Remove allocations that reference non-existent semesters, subjects, or teachers."""
    cleaned = 0

    # Orphan semester references
    try:
        result = db.execute(text("""
            DELETE FROM allocations
            WHERE semester_id NOT IN (SELECT id FROM semesters)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    # Orphan teacher references (NULL is allowed, so only clean invalid non-NULL)
    try:
        result = db.execute(text("""
            DELETE FROM allocations
            WHERE teacher_id IS NOT NULL
              AND teacher_id NOT IN (SELECT id FROM teachers)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    # Orphan subject references
    try:
        result = db.execute(text("""
            DELETE FROM allocations
            WHERE subject_id IS NOT NULL
              AND subject_id NOT IN (SELECT id FROM subjects)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    # Orphan room references (set to NULL instead of deleting)
    try:
        result = db.execute(text("""
            UPDATE allocations SET room_id = NULL
            WHERE room_id IS NOT NULL
              AND room_id NOT IN (SELECT id FROM rooms)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    if cleaned > 0:
        db.commit()
        logger.info(f"Cleaned {cleaned} orphan allocation rows")


def _clean_orphan_class_assignments(db: Session):
    """Remove class_subject_teachers pointing to deleted entities."""
    cleaned = 0

    for fk_col, ref_table in [
        ("teacher_id", "teachers"),
        ("subject_id", "subjects"),
        ("semester_id", "semesters"),
    ]:
        try:
            result = db.execute(text(f"""
                DELETE FROM class_subject_teachers
                WHERE {fk_col} NOT IN (SELECT id FROM {ref_table})
            """))
            cleaned += result.rowcount
        except Exception:
            db.rollback()

    # Fix orphan room references (set to NULL)
    try:
        result = db.execute(text("""
            UPDATE class_subject_teachers SET room_id = NULL
            WHERE room_id IS NOT NULL
              AND room_id NOT IN (SELECT id FROM rooms)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    # Fix orphan batch references (set to NULL)
    try:
        result = db.execute(text("""
            UPDATE class_subject_teachers SET batch_id = NULL
            WHERE batch_id IS NOT NULL
              AND batch_id NOT IN (SELECT id FROM batches)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    if cleaned > 0:
        db.commit()
        logger.info(f"Cleaned {cleaned} orphan class-assignment rows")


def _clean_orphan_fixed_slots(db: Session):
    """Remove fixed slots pointing to deleted entities."""
    cleaned = 0
    for fk_col, ref_table in [
        ("semester_id", "semesters"),
        ("subject_id", "subjects"),
        ("teacher_id", "teachers"),
    ]:
        try:
            result = db.execute(text(f"""
                DELETE FROM fixed_slots
                WHERE {fk_col} NOT IN (SELECT id FROM {ref_table})
            """))
            cleaned += result.rowcount
        except Exception:
            db.rollback()

    if cleaned > 0:
        db.commit()
        logger.info(f"Cleaned {cleaned} orphan fixed-slot rows")


def _remove_duplicate_teacher_subjects(db: Session):
    """Remove exact duplicate rows from teacher_subjects junction table."""
    try:
        result = db.execute(text("""
            DELETE FROM teacher_subjects
            WHERE rowid NOT IN (
                SELECT MIN(rowid) FROM teacher_subjects
                GROUP BY teacher_id, subject_id
            )
        """))
        if result.rowcount > 0:
            db.commit()
            logger.info(f"Removed {result.rowcount} duplicate teacher-subject mappings")
    except Exception:
        db.rollback()


def _remove_duplicate_subject_semesters(db: Session):
    """Remove exact duplicate rows from subject_semesters junction table."""
    try:
        result = db.execute(text("""
            DELETE FROM subject_semesters
            WHERE rowid NOT IN (
                SELECT MIN(rowid) FROM subject_semesters
                GROUP BY subject_id, semester_id
            )
        """))
        if result.rowcount > 0:
            db.commit()
            logger.info(f"Removed {result.rowcount} duplicate subject-semester mappings")
    except Exception:
        db.rollback()


def _clean_dead_basket_rows(db: Session):
    """Clean basket subjects pointing to deleted subjects."""
    cleaned = 0

    # Elective basket subject references
    try:
        result = db.execute(text("""
            UPDATE subjects SET elective_basket_id = NULL
            WHERE elective_basket_id IS NOT NULL
              AND elective_basket_id NOT IN (SELECT id FROM elective_baskets)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    # SCB subject links
    try:
        result = db.execute(text("""
            DELETE FROM scb_subjects
            WHERE subject_id NOT IN (SELECT id FROM subjects)
               OR basket_id NOT IN (SELECT id FROM structured_composite_baskets)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    # Parallel lab basket subject links
    try:
        result = db.execute(text("""
            DELETE FROM parallel_lab_basket_subjects
            WHERE subject_id NOT IN (SELECT id FROM subjects)
               OR basket_id NOT IN (SELECT id FROM parallel_lab_baskets)
        """))
        cleaned += result.rowcount
    except Exception:
        db.rollback()

    if cleaned > 0:
        db.commit()
        logger.info(f"Cleaned {cleaned} dead basket rows")


def _analyze_tables(db: Session):
    """Run SQLite ANALYZE to update query planner statistics."""
    try:
        db.execute(text("ANALYZE"))
        db.commit()
        logger.info("SQLite ANALYZE completed - query planner updated")
    except Exception as e:
        logger.debug(f"ANALYZE skip: {e}")


def _repair_inactive_teachers(db: Session):
    """
    Reactivate teachers who are incorrectly marked inactive.
    
    A teacher with class_subject_teacher mappings or active allocations
    should NEVER be is_active=0. This typically happens when:
    - The delete button soft-deletes a teacher
    - But the teacher still has active data in the system
    
    This repair ensures teachers are always visible when they have data.
    """
    try:
        # Reactivate teachers with class assignments
        result1 = db.execute(text("""
            UPDATE teachers SET is_active = 1
            WHERE is_active = 0
              AND id IN (SELECT DISTINCT teacher_id FROM class_subject_teachers)
        """))
        count1 = result1.rowcount

        # Reactivate teachers with allocations
        result2 = db.execute(text("""
            UPDATE teachers SET is_active = 1
            WHERE is_active = 0
              AND id IN (SELECT DISTINCT teacher_id FROM allocations WHERE teacher_id IS NOT NULL)
        """))
        count2 = result2.rowcount

        total = count1 + count2
        if total > 0:
            db.commit()
            logger.info(f"Reactivated {total} teachers with active data (assignments={count1}, allocations={count2})")
    except Exception as e:
        logger.warning(f"Teacher reactivation skipped: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def _warn_year_semester_mismatches(db: Session):
    """
    Detect and warn about subject-class mappings where the subject's
    year/semester doesn't match the class's year/semester_number.
    
    This does NOT auto-delete — admin action via the repair endpoint is required.
    Runs on every startup to ensure visibility of data integrity issues.
    """
    try:
        # Check subject_semesters table
        ss_mismatches = db.execute(text("""
            SELECT s.code AS subj_code, s.year AS subj_year, s.semester AS subj_sem,
                   sem.code AS class_code, sem.year AS class_year, sem.semester_number AS class_sem
            FROM subject_semesters ss
            JOIN subjects s ON s.id = ss.subject_id
            JOIN semesters sem ON sem.id = ss.semester_id
            WHERE s.year != sem.year OR s.semester != sem.semester_number
        """)).fetchall()

        # Check class_subject_teachers table
        cst_mismatches = db.execute(text("""
            SELECT s.code AS subj_code, s.year AS subj_year, s.semester AS subj_sem,
                   sem.code AS class_code, sem.year AS class_year, sem.semester_number AS class_sem,
                   cst.id AS cst_id
            FROM class_subject_teachers cst
            JOIN subjects s ON s.id = cst.subject_id
            JOIN semesters sem ON sem.id = cst.semester_id
            WHERE s.year != sem.year OR s.semester != sem.semester_number
        """)).fetchall()

        total = len(ss_mismatches) + len(cst_mismatches)
        if total > 0:
            logger.warning(
                f"INTEGRITY WARNING: {total} cross-year/semester mapping(s) found! "
                f"({len(ss_mismatches)} in subject_semesters, {len(cst_mismatches)} in class_subject_teachers)"
            )
            for row in ss_mismatches[:5]:
                logger.warning(
                    f"  subject_semesters: {row.subj_code} (Y{row.subj_year}/S{row.subj_sem}) "
                    f"-> {row.class_code} (Y{row.class_year}/S{row.class_sem})"
                )
            for row in cst_mismatches[:5]:
                logger.warning(
                    f"  class_subject_teachers #{row.cst_id}: {row.subj_code} (Y{row.subj_year}/S{row.subj_sem}) "
                    f"-> {row.class_code} (Y{row.class_year}/S{row.class_sem})"
                )
            if total > 10:
                logger.warning(f"  ... and {total - 10} more violations.")
            logger.warning(
                "  Use POST /api/subjects/integrity/repair to fix these mappings, "
                "or GET /api/subjects/integrity/diagnostics to review first."
            )
        else:
            logger.info("Year/semester integrity check passed - no mismatches found")
    except Exception as e:
        # Don't crash on startup — just log the error
        logger.debug(f"Year/semester mismatch check skipped: {e}")


def run_startup_repair(db: Session):
    """
    Run all startup repair tasks.

    Safe to call on every boot - all operations are idempotent.
    """
    logger.info("Running startup health check and repair...")

    try:
        _ensure_indexes(db)
        _repair_inactive_teachers(db)
        _clean_orphan_allocations(db)
        _clean_orphan_class_assignments(db)
        _clean_orphan_fixed_slots(db)
        _remove_duplicate_teacher_subjects(db)
        _remove_duplicate_subject_semesters(db)
        _clean_dead_basket_rows(db)
        _warn_year_semester_mismatches(db)
        _analyze_tables(db)
        logger.info("Startup repair completed successfully")
    except Exception as e:
        logger.error(f"Startup repair encountered an error: {e}")
        try:
            db.rollback()
        except Exception:
            pass

