import os

path = 'c:/Users/navee/.gemini/antigravity/scratch/timetable_generator/backend/app/api/teachers.py'

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = lines[:75]

code = """
@router.post("/", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def create_teacher(teacher_data: TeacherCreate, db: Session = Depends(get_db)):
    \"\"\"Create a new teacher.\"\"\"
    if teacher_data.email:
        existing = db.query(Teacher).filter(Teacher.email == teacher_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Teacher with this email already exists")
            
    if db.query(Teacher).filter(Teacher.teacher_code == teacher_data.teacher_code).first():
        raise HTTPException(status_code=400, detail="Teacher code already exists")
    
    subject_ids = teacher_data.subject_ids
    allowed_department_ids = teacher_data.allowed_department_ids
    teacher_dict = teacher_data.model_dump(exclude={"subject_ids", "allowed_department_ids"})
    
    if "email" in teacher_dict and teacher_dict["email"] == "":
        teacher_dict["email"] = None
    
    teacher = Teacher(**teacher_dict)
    
    if subject_ids:
        subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
        teacher.subjects = subjects
    
    if allowed_department_ids:
        depts = db.query(Department).filter(Department.id.in_(allowed_department_ids)).all()
        teacher.allowed_departments = depts
    
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher

@router.put("/{teacher_id}", response_model=TeacherResponse)
def update_teacher(teacher_id: int, teacher_data: TeacherUpdate, db: Session = Depends(get_db)):
    \"\"\"Update a teacher.\"\"\"
    teacher = db.query(Teacher).options(
        selectinload(Teacher.subjects),
        selectinload(Teacher.allowed_departments)
    ).filter(Teacher.id == teacher_id).first()
    
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    update_data = teacher_data.model_dump(exclude_unset=True)
    
    if "email" in update_data and update_data["email"] == "":
        update_data["email"] = None
        
    if "email" in update_data and update_data["email"] is not None:
         existing = db.query(Teacher).filter(Teacher.email == update_data["email"]).first()
         if existing and existing.id != teacher_id:
             raise HTTPException(status_code=400, detail="Teacher with this email already exists")

    if "teacher_code" in update_data and update_data["teacher_code"]:
        existing_code = db.query(Teacher).filter(Teacher.teacher_code == update_data["teacher_code"]).first()
        if existing_code and existing_code.id != teacher_id:
             raise HTTPException(status_code=400, detail="Teacher code already exists")
    
    if "subject_ids" in update_data:
        subject_ids = update_data.pop("subject_ids")
        if subject_ids is not None:
            subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
            teacher.subjects = subjects
    
    if "allowed_department_ids" in update_data:
        dept_ids = update_data.pop("allowed_department_ids")
        if dept_ids is not None:
            depts = db.query(Department).filter(Department.id.in_(dept_ids)).all()
            teacher.allowed_departments = depts
    
    for key, value in update_data.items():
        setattr(teacher, key, value)
    
    db.commit()
    db.refresh(teacher)
    return teacher

@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    \"\"\"Delete a teacher (soft delete - marks as inactive).\"\"\"
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    try:
        teacher.is_active = False
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    
    return None
"""

new_lines.append(code.lstrip())
new_lines.extend(lines[97:])

with open(path, 'w', encoding='utf-8') as f:
    f.write(''.join(new_lines))
