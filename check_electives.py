"""Check elective subjects and their assignments."""
import sys
sys.path.insert(0, 'backend')

from app.db.session import SessionLocal
from app.db.models import Subject, Semester, ClassSubjectTeacher, SubjectType, teacher_subjects

db = SessionLocal()

print("=" * 60)
print("ELECTIVE SUBJECTS CHECK")
print("=" * 60)

# Get all subjects
subjects = db.query(Subject).all()
print(f"\nTotal subjects: {len(subjects)}")

# Find electives
electives = []
for s in subjects:
    is_elective = s.is_elective or s.subject_type == SubjectType.ELECTIVE
    if is_elective:
        electives.append(s)

print(f"Elective subjects: {len(electives)}")

for s in electives:
    print(f"\n  {s.id}: {s.code} - {s.name}")
    print(f"      is_elective={s.is_elective}, type={s.subject_type}")
    print(f"      weekly_hours={s.weekly_hours}, theory={getattr(s, 'theory_hours_per_week', 0)}")
    
    # Check assigned classes
    semesters = s.semesters
    print(f"      Classes: {[sem.name for sem in semesters] if semesters else 'NONE'}")
    
    # Check assigned teachers
    teachers = s.teachers
    print(f"      Teachers: {[t.name for t in teachers] if teachers else 'NONE'}")

# Check ClassSubjectTeacher entries
print("\n" + "=" * 60)
print("CLASS-SUBJECT-TEACHER MAPPINGS")
print("=" * 60)

csts = db.query(ClassSubjectTeacher).all()
print(f"\nTotal mappings: {len(csts)}")

# Filter for elective subjects
elective_ids = [s.id for s in electives]
elective_csts = [c for c in csts if c.subject_id in elective_ids]
print(f"Elective mappings: {len(elective_csts)}")

for c in elective_csts:
    sem = db.query(Semester).get(c.semester_id)
    subj = db.query(Subject).get(c.subject_id)
    from app.db.models import Teacher
    teacher = db.query(Teacher).get(c.teacher_id)
    print(f"  {sem.name if sem else c.semester_id} | {subj.code if subj else c.subject_id} | {c.component_type.value} | {teacher.name if teacher else c.teacher_id}")

# Check semesters
print("\n" + "=" * 60)
print("SEMESTERS BY YEAR")
print("=" * 60)

semesters = db.query(Semester).all()
by_year = {}
for sem in semesters:
    year = sem.semester_number
    if year not in by_year:
        by_year[year] = []
    by_year[year].append(sem)

for year in sorted(by_year.keys()):
    sems = by_year[year]
    print(f"\n  Year {year}: {[s.name for s in sems]}")

db.close()
