"""
Diagnostic: Find shared teachers between science & humanities sections (B and F vs others).
Outputs to stdout in a simpler form to avoid encoding issues.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

from app.db.session import SessionLocal
from app.db.models import Semester, Subject, Teacher, ClassSubjectTeacher, Department

db = SessionLocal()

try:
    all_sems = db.query(Semester).all()
    print("SEMESTERS:")
    for s in all_sems:
        dept = db.query(Department).filter(Department.id == s.dept_id).first()
        dname = dept.name if dept else "N/A"
        print(f"  ID={s.id} Sec={s.section} Year={s.year} SemNum={s.semester_number} Dept={s.dept_id}({dname})")

    bf_sems = [s for s in all_sems if s.section in ('B', 'F')]
    b_sems = [s for s in all_sems if s.section == 'B']
    f_sems = [s for s in all_sems if s.section == 'F']
    
    b_sem_ids = {s.id for s in b_sems}
    f_sem_ids = {s.id for s in f_sems}
    bf_sem_ids = b_sem_ids | f_sem_ids

    b_assignments = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.semester_id.in_(b_sem_ids)
    ).all()
    f_assignments = db.query(ClassSubjectTeacher).filter(
        ClassSubjectTeacher.semester_id.in_(f_sem_ids)
    ).all()

    b_teachers = {a.teacher_id for a in b_assignments}
    f_teachers = {a.teacher_id for a in f_assignments}
    shared = b_teachers & f_teachers

    print("\nSHARED TEACHERS BETWEEN B AND F SECTIONS:")
    if shared:
        for tid in sorted(shared):
            t = db.query(Teacher).filter(Teacher.id == tid).first()
            tname = t.name if t else str(tid)
            print(f"  ** CONFLICT: Teacher {tid} ({tname}) assigned to BOTH B and F **")
            for a in b_assignments:
                if a.teacher_id == tid:
                    subj = db.query(Subject).filter(Subject.id == a.subject_id).first()
                    sname = subj.name if subj else str(a.subject_id)
                    print(f"     I-B: {sname} [{a.component_type}]")
            for a in f_assignments:
                if a.teacher_id == tid:
                    subj = db.query(Subject).filter(Subject.id == a.subject_id).first()
                    sname = subj.name if subj else str(a.subject_id)
                    print(f"     I-F: {sname} [{a.component_type}]")
    else:
        print("  None - No shared teachers between B and F")

    # Teacher hour loads 
    print("\nTEACHER HOUR LOADS (B and F teachers):")
    for tid in sorted(b_teachers | f_teachers):
        t = db.query(Teacher).filter(Teacher.id == tid).first()
        tname = t.name if t else str(tid)
        max_h = t.max_hours_per_week if t else 20
        all_assign = db.query(ClassSubjectTeacher).filter(
            ClassSubjectTeacher.teacher_id == tid,
            ClassSubjectTeacher.batch_id.is_(None)
        ).all()
        total = 0
        details = []
        for a in all_assign:
            sem = db.query(Semester).filter(Semester.id == a.semester_id).first()
            subj = db.query(Subject).filter(Subject.id == a.subject_id).first()
            if not subj:
                continue
            ct = a.component_type.value if hasattr(a.component_type, 'value') else str(a.component_type)
            if ct == 'lab':
                h = subj.lab_hours_per_week
            elif ct == 'tutorial':
                h = subj.tutorial_hours_per_week
            else:
                h = subj.theory_hours_per_week
            total += h
            sec = sem.section if sem else '?'
            sname = subj.name if subj else str(a.subject_id)
            details.append(f"Sec {sec}: {sname} [{ct}]={h}h")
        print(f"  {tname} (ID={tid}): total_h={total}, max_h={max_h}")
        for d in details:
            print(f"    {d}")

finally:
    db.close()
