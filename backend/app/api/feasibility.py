"""
Module 9: Timetable Feasibility Analyzer API
Detect scheduling conflicts before generation.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.db.session import get_db
from app.services.feasibility_analyzer import TimetableFeasibilityAnalyzer

router = APIRouter(prefix="/feasibility", tags=["Feasibility Analyzer"])


@router.get("/analyze")
def analyze_feasibility(
    department_id: Optional[int] = None,
    semester_ids: Optional[str] = Query(None, description="Comma-separated semester IDs"),
    db: Session = Depends(get_db)
):
    """
    Run all feasibility checks and return a report.
    If conflicts are detected, warns admin before timetable generation.
    """
    parsed_ids = None
    if semester_ids:
        parsed_ids = [int(x.strip()) for x in semester_ids.split(",") if x.strip().isdigit()]

    analyzer = TimetableFeasibilityAnalyzer(db)
    return analyzer.analyze(department_id=department_id, semester_ids=parsed_ids)
