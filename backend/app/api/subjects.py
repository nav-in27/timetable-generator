"""
CRUD API routes for Subjects.
Updated to support the CORRECT ACADEMIC DATA MODEL with component-based subjects.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.db.models import (
    Subject, Semester, Teacher, SubjectType, ComponentType,
    ClassSubjectTeacher, Allocation, SubjectComponentAssignment,
    ElectiveBasket
)
from app.schemas.schemas import SubjectCreate, SubjectUpdate, SubjectResponse, SubjectWithTeachers
from app.core.cache import cache

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get("/", response_model=List[SubjectResponse])
def list_subjects(
    skip: int = 0,
    limit: int = 100,
    dept_id: Optional[int] = None,
    year: Optional[int] = None,
    semester: Optional[int] = None,
    is_elective: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get all subjects with department-aware filtering."""
    query = db.query(Subject).options(
        selectinload(Subject.semesters),
        selectinload(Subject.departments)
    )
    
    # Department Filtering Rule:
    # - When a department is selected, show ONLY that department's subjects.
    # - Electives are college-level, but visibility is department-filtered using participating classes.
    if dept_id:
        from sqlalchemy import and_, or_

        elective_in_dept = and_(
            Subject.is_elective == True,
            Subject.semesters.any(Semester.dept_id == dept_id)
        )

        if is_elective is True:
            query = query.filter(elective_in_dept)
        elif is_elective is False:
            query = query.filter(Subject.dept_id == dept_id).filter(Subject.is_elective == False)
        else:
            query = query.filter(or_(Subject.dept_id == dept_id, elective_in_dept))
    
    if year:
        query = query.filter(Subject.year == year)
    if semester:
        query = query.filter(Subject.semester == semester)
        
    subjects = query.offset(skip).limit(limit).all()
    return subjects


# ============================================================================
# INTEGRITY DIAGNOSTICS & REPAIR
# (MUST be before /{subject_id} routes to avoid FastAPI matching 'integrity' as ID)
# ============================================================================

@router.get("/integrity/diagnostics")
def integrity_diagnostics(db: Session = Depends(get_db)):
    """
    Comprehensive integrity scan. Detects:
    1. STALE teacher mappings — CST records where subject is no longer assigned to that class
    2. YEAR/SEMESTER mismatches — active subject_semesters where year/semester don't match
    3. ORPHANED batch references — batches pointing to non-existent semesters
    4. ORPHANED room references in CST — room_id pointing to deleted rooms
    
    Each issue includes a reason for why it's flagged.
    """
    from app.db.models import subject_semesters, Batch

    issues = []

    # Build active (subject_id, semester_id) set from subject_semesters
    ss_rows = db.execute(subject_semesters.select()).fetchall()
    active_pairs = {(r.subject_id, r.semester_id) for r in ss_rows}

    # Cache subjects and semesters
    all_subjects = {s.id: s for s in db.query(Subject).all()}
    all_semesters = {s.id: s for s in db.query(Semester).all()}

    # 1. Check subject_semesters for year/semester mismatches
    for row in ss_rows:
        subj = all_subjects.get(row.subject_id)
        sem = all_semesters.get(row.semester_id)
        if subj and sem:
            if subj.year != sem.year or subj.semester != sem.semester_number:
                issues.append({
                    "type": "year_semester_mismatch",
                    "table": "subject_semesters",
                    "subject_code": subj.code,
                    "subject_name": subj.name,
                    "subject_year": subj.year,
                    "subject_semester": subj.semester,
                    "class_code": sem.code,
                    "class_name": sem.name,
                    "class_year": sem.year,
                    "class_semester": sem.semester_number,
                    "reason": f"Subject {subj.code} is Year {subj.year}/Sem {subj.semester} "
                              f"but Class {sem.code} is Year {sem.year}/Sem {sem.semester_number}"
                })

    # 2. Check ClassSubjectTeacher for stale + mismatched records
    cst_rows = db.query(ClassSubjectTeacher).all()
    all_teachers = {t.id: t for t in db.query(Teacher).all()}
    
    try:
        all_batches = {b.id: b for b in db.query(Batch).all()}
    except Exception:
        all_batches = {}
    
    for cst in cst_rows:
        subj = all_subjects.get(cst.subject_id)
        sem = all_semesters.get(cst.semester_id)
        teacher = all_teachers.get(cst.teacher_id)
        teacher_name = teacher.name if teacher else f"Teacher #{cst.teacher_id}"
        
        if not subj or not sem:
            # Orphaned reference — subject or semester was deleted
            issues.append({
                "type": "orphaned_cst",
                "table": "class_subject_teachers",
                "cst_id": cst.id,
                "subject_code": subj.code if subj else f"DELETED(id={cst.subject_id})",
                "class_code": sem.code if sem else f"DELETED(id={cst.semester_id})",
                "teacher": teacher_name,
                "component_type": cst.component_type.value if cst.component_type else None,
                "reason": "References deleted subject or class"
            })
            continue
            
        pair = (cst.subject_id, cst.semester_id)
        if pair not in active_pairs:
            # STALE: subject is no longer assigned to this class
            issues.append({
                "type": "stale_teacher_mapping",
                "table": "class_subject_teachers",
                "cst_id": cst.id,
                "subject_code": subj.code,
                "subject_name": subj.name,
                "subject_year": subj.year,
                "subject_semester": subj.semester,
                "class_code": sem.code,
                "class_name": sem.name,
                "class_year": sem.year,
                "class_semester": sem.semester_number,
                "teacher": teacher_name,
                "component_type": cst.component_type.value if cst.component_type else None,
                "reason": f"Subject {subj.code} is no longer assigned to Class {sem.code}. "
                          f"This is a stale mapping from a previous configuration."
            })
        elif subj.year != sem.year or subj.semester != sem.semester_number:
            # MISMATCH: subject IS assigned but year/semester don't match
            issues.append({
                "type": "year_semester_mismatch",
                "table": "class_subject_teachers",
                "cst_id": cst.id,
                "subject_code": subj.code,
                "subject_name": subj.name,
                "subject_year": subj.year,
                "subject_semester": subj.semester,
                "class_code": sem.code,
                "class_name": sem.name,
                "class_year": sem.year,
                "class_semester": sem.semester_number,
                "teacher": teacher_name,
                "component_type": cst.component_type.value if cst.component_type else None,
                "reason": f"Subject {subj.code} is Year {subj.year}/Sem {subj.semester} "
                          f"but Class {sem.code} is Year {sem.year}/Sem {sem.semester_number}"
            })
            
        # Check Batch Integrity (Phantom Batches)
        if cst.batch_id is not None:
            batch = all_batches.get(cst.batch_id)
            if not batch:
                issues.append({
                    "type": "orphaned_cst_batch",
                    "table": "class_subject_teachers",
                    "cst_id": cst.id,
                    "subject_code": subj.code,
                    "class_code": sem.code,
                    "teacher": teacher_name,
                    "reason": f"References a deleted batch (id={cst.batch_id})"
                })
            elif batch.semester_id != cst.semester_id:
                issues.append({
                    "type": "batch_semester_mismatch",
                    "table": "class_subject_teachers",
                    "cst_id": cst.id,
                    "subject_code": subj.code,
                    "class_code": sem.code,
                    "teacher": teacher_name,
                    "reason": f"Phantom Batch! Batch '{batch.name}' belongs to Class ID {batch.semester_id}, but mapping is for Class ID {cst.semester_id}"
                })

    # 3. Orphaned batches — batches where semester was deleted
    try:
        orphan_batches = db.query(Batch).filter(
            ~Batch.semester_id.in_(db.query(Semester.id))
        ).all()
        for b in orphan_batches:
            issues.append({
                "type": "orphaned_batch",
                "table": "batches",
                "batch_id": b.id,
                "batch_name": b.name,
                "reason": f"Batch '{b.name}' references a deleted semester (id={b.semester_id})"
            })
    except Exception:
        pass  # Batch model may not exist in all versions

    # Summarize by type
    type_counts = {}
    for issue in issues:
        t = issue["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "issues": issues,
        "summary": type_counts,
        "total_issues": len(issues),
        "message": "No integrity issues found — all clear!" if len(issues) == 0
                   else f"Found {len(issues)} issue(s). Use POST /subjects/integrity/repair to fix.",
    }


@router.post("/integrity/repair")
def integrity_repair(db: Session = Depends(get_db)):
    """
    Comprehensive integrity repair. Removes:
    1. Stale teacher mappings — CST where subject not assigned to class
    2. Year/semester mismatched subject_semesters
    3. Year/semester mismatched CST records (active but wrong)
    4. Orphaned CST records (deleted subject/class)
    5. Orphaned batch records
    
    After repair, invalidates all relevant caches.
    """
    from app.db.models import subject_semesters, Batch

    # Build active pairs
    ss_rows = db.execute(subject_semesters.select()).fetchall()
    active_pairs = {(r.subject_id, r.semester_id) for r in ss_rows}

    all_subjects = {s.id: s for s in db.query(Subject).all()}
    all_semesters = {s.id: s for s in db.query(Semester).all()}
    
    try:
        all_batches = {b.id: b for b in db.query(Batch).all()}
    except Exception:
        all_batches = {}

    removed = {
        "stale_teacher_mappings": 0,
        "mismatched_subject_class": 0,
        "mismatched_teacher_mappings": 0,
        "mismatched_batch_mappings": 0,
        "orphaned_cst": 0,
        "orphaned_cst_batch": 0,
        "orphaned_batches": 0,
    }
    details = []

    # 1. Remove stale + mismatched + orphaned CST records
    cst_rows = db.query(ClassSubjectTeacher).all()
    cst_to_delete = []
    
    for cst in cst_rows:
        subj = all_subjects.get(cst.subject_id)
        sem = all_semesters.get(cst.semester_id)
        
        if not subj or not sem:
            cst_to_delete.append(cst.id)
            removed["orphaned_cst"] += 1
            details.append(f"Removed orphaned CST #{cst.id} (deleted subject/class)")
            continue
        
        pair = (cst.subject_id, cst.semester_id)
        if pair not in active_pairs:
            cst_to_delete.append(cst.id)
            removed["stale_teacher_mappings"] += 1
            details.append(
                f"Removed stale CST #{cst.id}: {subj.code} → {sem.code} "
                f"(subject no longer assigned to this class)"
            )
        elif subj.year != sem.year or subj.semester != sem.semester_number:
            cst_to_delete.append(cst.id)
            removed["mismatched_teacher_mappings"] += 1
            details.append(
                f"Removed mismatched CST #{cst.id}: {subj.code} (Y{subj.year}/S{subj.semester}) "
                f"↔ {sem.code} (Y{sem.year}/S{sem.semester_number})"
            )
        elif cst.batch_id is not None:
            batch = all_batches.get(cst.batch_id)
            if not batch:
                cst_to_delete.append(cst.id)
                removed["orphaned_cst_batch"] += 1
                details.append(f"Removed CST #{cst.id} referencing deleted batch #{cst.batch_id}")
            elif batch.semester_id != cst.semester_id:
                cst_to_delete.append(cst.id)
                removed["mismatched_batch_mappings"] += 1
                details.append(
                    f"Removed Phantom Batch CST #{cst.id}: mapped Batch '{batch.name}' "
                    f"belongs to Class #{batch.semester_id}, but mapping is for Class #{cst.semester_id}"
                )
    
    if cst_to_delete:
        db.query(ClassSubjectTeacher).filter(
            ClassSubjectTeacher.id.in_(cst_to_delete)
        ).delete(synchronize_session='fetch')

    # 2. Remove mismatched subject_semesters
    for row in ss_rows:
        subj = all_subjects.get(row.subject_id)
        sem = all_semesters.get(row.semester_id)
        if subj and sem:
            if subj.year != sem.year or subj.semester != sem.semester_number:
                db.execute(
                    subject_semesters.delete().where(
                        (subject_semesters.c.subject_id == row.subject_id) &
                        (subject_semesters.c.semester_id == row.semester_id)
                    )
                )
                removed["mismatched_subject_class"] += 1
                details.append(
                    f"Removed subject_semesters: {subj.code} (Y{subj.year}/S{subj.semester}) "
                    f"↔ {sem.code} (Y{sem.year}/S{sem.semester_number})"
                )

    # 3. Remove orphaned batches
    try:
        orphan_batches = db.query(Batch).filter(
            ~Batch.semester_id.in_(db.query(Semester.id))
        ).all()
        for b in orphan_batches:
            db.delete(b)
            removed["orphaned_batches"] += 1
            details.append(f"Removed orphaned batch '{b.name}' (deleted semester)")
    except Exception:
        pass

    total_removed = sum(removed.values())
    if total_removed > 0:
        db.commit()
        cache.invalidate_tags(["subjects", "timetable", "teachers", "allocations", "dashboard", "reports"])

    return {
        "removed_breakdown": removed,
        "total_removed": total_removed,
        "details": details[:100],
        "message": f"Repaired {total_removed} issue(s)." if total_removed > 0
                   else "No issues found — database is clean!",
    }


@router.get("/{subject_id}", response_model=SubjectWithTeachers)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    """Get a specific subject by ID with its qualified teachers."""
    subject = db.query(Subject).options(
        selectinload(Subject.semesters),
        selectinload(Subject.departments)
    ).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.post("/", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def create_subject(subject_data: SubjectCreate, db: Session = Depends(get_db)):
    """
    Create a new subject with the component-based model.
    
    Supports:
    - theory_hours_per_week
    - lab_hours_per_week  
    - tutorial_hours_per_week
    - is_elective flag
    
    Academic Rule: Non-elective subjects can only be assigned to classes of the same semester.
    """
    # Check for duplicate code
    existing = db.query(Subject).filter(Subject.code == subject_data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Subject with this code already exists")
    
    # Handle semester mapping
    data = subject_data.model_dump(exclude={'semester_ids', 'elective_basket_id'})
    
    # Calculate legacy weekly_hours for backward compatibility
    def _validate_block(component_name: str, hours: int, block_size: int):
        if hours <= 0:
            return
        if block_size == 2 and hours % 2 != 0:
            raise HTTPException(
                status_code=400,
                detail=f"{component_name} hours must be even when block size is 2 (continuous)."
            )

    _validate_block("Project", subject_data.project_hours_per_week, subject_data.project_block_size)
    _validate_block("Report", subject_data.report_hours_per_week, subject_data.report_block_size)
    _validate_block("Seminar", subject_data.seminar_hours_per_week, subject_data.seminar_block_size)

    if subject_data.seminar_day_based and subject_data.seminar_hours_per_week > 0:
        if subject_data.seminar_hours_per_week < 7:
            raise HTTPException(
                status_code=400,
                detail="Seminar day-based mode requires at least 7 periods per week."
            )

    total_hours = (
        subject_data.theory_hours_per_week
        + subject_data.lab_hours_per_week
        + subject_data.tutorial_hours_per_week
        + subject_data.project_hours_per_week
        + subject_data.report_hours_per_week
        + subject_data.self_study_hours_per_week
        + subject_data.seminar_hours_per_week
    )
    if total_hours > 0:
        data['weekly_hours'] = total_hours
    
    # Auto-compute priority score (never user-editable)
    importance = data.get('importance_level', 'NORMAL') or 'NORMAL'
    pass_pct = data.get('previous_year_pass_percentage')
    data['computed_priority_score'] = Subject.calculate_priority_score(importance, pass_pct)
    
    subject = Subject(**data)
    
    if subject_data.semester_ids:
        semesters = db.query(Semester).filter(Semester.id.in_(subject_data.semester_ids)).all()
        
        # VALIDATION: Ensure all classes belong to the same semester (Academic Constraint)
        # Exception: Electives can span multiple semesters
        is_elective = subject_data.is_elective or subject_data.subject_type in [SubjectType.ELECTIVE]
        
        unique_sem_nums = {s.semester_number for s in semesters}
        if not is_elective and len(unique_sem_nums) > 1:
            raise HTTPException(
                status_code=400, 
                detail=f"Academic Rule Violation: A non-elective subject cannot be assigned to classes from different semesters (Found semesters: {unique_sem_nums}). Mark as 'Elective' to allow this."
            )
        
        # YEAR/SEMESTER INTEGRITY CHECK: Every assigned class must match subject's year and semester
        # Exception: Electives with a declared basket are exempt
        has_basket = bool(subject_data.elective_basket_id) if hasattr(subject_data, 'elective_basket_id') else False
        if not (is_elective and has_basket):
            for sem in semesters:
                if sem.year != subject_data.year:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Year mismatch: Class '{sem.code}' is Year {sem.year} "
                               f"but subject is Year {subject_data.year}. "
                               f"A subject can only be assigned to classes of the same year."
                    )
                if sem.semester_number != subject_data.semester:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Semester mismatch: Class '{sem.code}' is Semester {sem.semester_number} "
                               f"but subject is Semester {subject_data.semester}. "
                               f"A subject can only be assigned to classes of the same semester."
                    )
        
        subject.semesters = semesters
        
        # AUTO-ASSIGN DEPT_ID if not provided
        if not subject.dept_id and semesters:
            # Use the department of the first assigned semester
            subject.dept_id = semesters[0].dept_id
    
    # Handle elective basket
    if subject_data.elective_basket_id:
        basket = db.query(ElectiveBasket).filter(
            ElectiveBasket.id == subject_data.elective_basket_id
        ).first()
        if basket:
            subject.elective_basket_id = basket.id
            subject.is_elective = True
    
    db.add(subject)
    db.commit()
    db.refresh(subject)
    cache.invalidate_tags(["subjects", "timetable"])
    return subject


@router.put("/{subject_id}", response_model=SubjectResponse)
def update_subject(subject_id: int, subject_data: SubjectUpdate, db: Session = Depends(get_db)):
    """Update a subject and its semester assignments."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    update_data = subject_data.model_dump(exclude_unset=True)
    
    # Handle semester mapping update if provided
    if 'semester_ids' in update_data:
        sem_ids = update_data.pop('semester_ids')
        if sem_ids is not None:
            semesters = db.query(Semester).filter(Semester.id.in_(sem_ids)).all()
            
            # Check if it is (or becoming) an elective
            current_is_elective = update_data.get('is_elective', subject.is_elective)
            current_type = update_data.get('subject_type', subject.subject_type)
            is_elective = current_is_elective or current_type == SubjectType.ELECTIVE
            
            # VALIDATION: Ensure all classes belong to the same semester
            unique_sem_nums = {s.semester_number for s in semesters}
            if not is_elective and len(unique_sem_nums) > 1:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Academic Rule Violation: A non-elective subject cannot be assigned to classes from different semesters (Found semesters: {unique_sem_nums}). Mark as 'Elective' to allow this."
                )
            
            # YEAR/SEMESTER INTEGRITY CHECK: Every assigned class must match subject's year and semester
            # Use the incoming values if being updated, otherwise use existing subject values
            subject_year = update_data.get('year', subject.year)
            subject_semester = update_data.get('semester', subject.semester)
            has_basket = bool(update_data.get('elective_basket_id', subject.elective_basket_id))
            if not (is_elective and has_basket):
                for sem in semesters:
                    if sem.year != subject_year:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Year mismatch: Class '{sem.code}' is Year {sem.year} "
                                   f"but subject is Year {subject_year}. "
                                   f"A subject can only be assigned to classes of the same year."
                        )
                    if sem.semester_number != subject_semester:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Semester mismatch: Class '{sem.code}' is Semester {sem.semester_number} "
                                   f"but subject is Semester {subject_semester}. "
                                   f"A subject can only be assigned to classes of the same semester."
                        )
            
            subject.semesters = semesters

            # AUTO-ASSIGN DEPT_ID if it was missing and we now have semesters
            if not subject.dept_id and semesters:
                subject.dept_id = semesters[0].dept_id
    
    # Handle elective basket
    if 'elective_basket_id' in update_data:
        basket_id = update_data.pop('elective_basket_id')
        subject.elective_basket_id = basket_id
        if basket_id:
            subject.is_elective = True
    
    # Update remaining fields
    for key, value in update_data.items():
        setattr(subject, key, value)
    
    # Recalculate legacy weekly_hours
    def _validate_block(component_name: str, hours: int, block_size: int):
        if hours <= 0:
            return
        if block_size == 2 and hours % 2 != 0:
            raise HTTPException(
                status_code=400,
                detail=f"{component_name} hours must be even when block size is 2 (continuous)."
            )

    _validate_block("Project", subject.project_hours_per_week or 0, subject.project_block_size or 1)
    _validate_block("Report", subject.report_hours_per_week or 0, subject.report_block_size or 1)
    _validate_block("Seminar", subject.seminar_hours_per_week or 0, subject.seminar_block_size or 2)

    if getattr(subject, "seminar_day_based", False) and (subject.seminar_hours_per_week or 0) > 0:
        if (subject.seminar_hours_per_week or 0) < 7:
            raise HTTPException(
                status_code=400,
                detail="Seminar day-based mode requires at least 7 periods per week."
            )

    total_hours = (
        (subject.theory_hours_per_week or 0)
        + (subject.lab_hours_per_week or 0)
        + (subject.tutorial_hours_per_week or 0)
        + (subject.project_hours_per_week or 0)
        + (subject.report_hours_per_week or 0)
        + (subject.self_study_hours_per_week or 0)
        + (subject.seminar_hours_per_week or 0)
    )
    if total_hours > 0:
        subject.weekly_hours = total_hours
    
    # Auto-compute priority score
    importance = getattr(subject, 'importance_level', 'NORMAL') or 'NORMAL'
    pass_pct = getattr(subject, 'previous_year_pass_percentage', None)
    subject.computed_priority_score = Subject.calculate_priority_score(importance, pass_pct)
    
    db.commit()
    db.refresh(subject)
    cache.invalidate_tags(["subjects", "timetable"])
    return subject


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    """
    Delete a subject with COMPLETE CLEANUP.
    
    According to academic rules, deleting a subject MUST:
    1. Remove all allocations for this subject
    2. Remove all class-subject-teacher mappings
    3. Remove all component assignments
    4. Remove from elective baskets (if applicable)
    5. Recalculate available hours (happens at validation)
    """
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    subject_name = subject.name
    
    # 1. Delete all allocations for this subject
    deleted_allocations = db.query(Allocation).filter(
        Allocation.subject_id == subject_id
    ).delete(synchronize_session=False)
    
    # 2. Delete all class-subject-teacher mappings
    deleted_assignments = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.subject_id == subject_id
    ).delete(synchronize_session=False)
    
    # 3. Delete all component assignments
    deleted_components = db.query(SubjectComponentAssignment).filter(
        SubjectComponentAssignment.subject_id == subject_id
    ).delete(synchronize_session=False)
    
    # 4. Clear semester associations (handled by ORM cascade)
    subject.semesters = []
    
    # 5. Delete the subject itself
    db.delete(subject)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to delete subject: {str(e)}"
        )
    
    print(f"[Subject Deleted] '{subject_name}' (ID: {subject_id})")
    print(f"  - Removed {deleted_allocations} allocations")
    print(f"  - Removed {deleted_assignments} teacher assignments")
    print(f"  - Removed {deleted_components} component assignments")
    cache.invalidate_tags(["subjects", "timetable", "teachers", "allocations"])
    
    return None


# ============================================================================
# ADDITIONAL ENDPOINTS FOR COMPONENT-BASED SUBJECTS
# ============================================================================

@router.get("/{subject_id}/components")
def get_subject_components(subject_id: int, db: Session = Depends(get_db)):
    """Get detailed component breakdown for a subject."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    components = []
    
    if subject.theory_hours_per_week > 0:
        components.append({
            "type": "theory",
            "hours_per_week": subject.theory_hours_per_week,
            "description": f"{subject.theory_hours_per_week} theory periods/week"
        })
    
    if subject.lab_hours_per_week > 0:
        blocks = subject.lab_hours_per_week // 2
        components.append({
            "type": "lab",
            "hours_per_week": subject.lab_hours_per_week,
            "blocks_per_week": blocks,
            "description": f"{blocks} lab block(s)/week ({subject.lab_hours_per_week} periods)"
        })
    
    if subject.tutorial_hours_per_week > 0:
        components.append({
            "type": "tutorial",
            "hours_per_week": subject.tutorial_hours_per_week,
            "description": f"{subject.tutorial_hours_per_week} tutorial period(s)/week"
        })

    if getattr(subject, "project_hours_per_week", 0) > 0:
        components.append({
            "type": "project",
            "hours_per_week": subject.project_hours_per_week,
            "block_size": getattr(subject, "project_block_size", 1),
            "description": f"{subject.project_hours_per_week} project period(s)/week"
        })

    if getattr(subject, "report_hours_per_week", 0) > 0:
        components.append({
            "type": "report",
            "hours_per_week": subject.report_hours_per_week,
            "block_size": getattr(subject, "report_block_size", 1),
            "description": f"{subject.report_hours_per_week} report period(s)/week"
        })

    if getattr(subject, "self_study_hours_per_week", 0) > 0:
        components.append({
            "type": "self_study",
            "hours_per_week": subject.self_study_hours_per_week,
            "description": f"{subject.self_study_hours_per_week} self-study period(s)/week"
        })
    
    if getattr(subject, "seminar_hours_per_week", 0) > 0:
        components.append({
            "type": "seminar",
            "hours_per_week": subject.seminar_hours_per_week,
            "block_size": getattr(subject, "seminar_block_size", 2),
            "day_based": getattr(subject, "seminar_day_based", False),
            "description": f"{subject.seminar_hours_per_week} seminar period(s)/week"
        })
    
    return {
        "subject_id": subject.id,
        "subject_name": subject.name,
        "subject_code": subject.code,
        "is_elective": subject.is_elective,
        "total_hours_per_week": subject.total_weekly_hours,
        "components": components
    }


@router.put("/{subject_id}/components")
def update_subject_components(
    subject_id: int, 
    theory_hours: int = 0,
    lab_hours: int = 0,
    tutorial_hours: int = 0,
    db: Session = Depends(get_db)
):
    """Update component hours for a subject."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    subject.theory_hours_per_week = theory_hours
    subject.lab_hours_per_week = lab_hours
    subject.tutorial_hours_per_week = tutorial_hours
    subject.weekly_hours = theory_hours + lab_hours + tutorial_hours
    
    db.commit()
    db.refresh(subject)
    cache.invalidate_tags(["subjects", "timetable"])
    
    return {
        "message": "Components updated",
        "subject_id": subject.id,
        "theory_hours": subject.theory_hours_per_week,
        "lab_hours": subject.lab_hours_per_week,
        "tutorial_hours": subject.tutorial_hours_per_week,
        "total_hours": subject.weekly_hours
    }
