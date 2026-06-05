import sys
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Department, Semester

DATABASE_URL = "sqlite:///./timetable.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

for code in ["CSE", "AIML"]:
    dept = db.query(Department).filter(Department.code == code).first()
    if not dept:
        dept = Department(name=code, code=code)
        db.add(dept)
        db.commit()
    
cse_dept = db.query(Department).filter(Department.code == "CSE").first()
aiml_dept = db.query(Department).filter(Department.code == "AIML").first()

for code, sem, dept in [("3A", 3, cse_dept), ("3B", 3, cse_dept), ("4A", 4, aiml_dept), ("4B", 4, aiml_dept)]:
    klass = db.query(Semester).filter(Semester.code == code).first()
    if not klass:
        klass = Semester(name=code, code=code, semester=sem, dept_id=dept.id)
        db.add(klass)
        db.commit()

print("Test data created.")
