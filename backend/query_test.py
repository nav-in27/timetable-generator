import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Subject

DATABASE_URL = "sqlite:///timetable.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

print("Subject Count:", db.query(Subject).count())

for s in db.query(Subject).limit(5).all():
    print(f"{s.id}: {s.code} - {s.name} - IsElective: {s.is_elective}")
