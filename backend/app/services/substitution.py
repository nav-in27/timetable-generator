"""
Automated Teacher Substitution Service.

Implements intelligent substitution logic:
1. Detect teacher absence
2. Identify qualified candidates who are free
3. Rank candidates using weighted scoring
4. Assign best candidate
5. Update timetable dynamically (local repair)

Scoring Function:
    score = 
        (subject_match_weight * subject_match) +
        (workload_weight * (1 - normalized_load)) +
        (effectiveness_weight * effectiveness_score) +
        (experience_weight * experience_score)

This approach minimizes disruption by:
- NOT regenerating the entire timetable
- Using local repair algorithm
- Preferring teachers with lower current workload
- Preferring teachers with higher effectiveness for the subject
"""
from datetime import date
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import (
    Teacher, Subject, Allocation, TeacherAbsence, Substitution,
    teacher_subjects, SubstitutionStatus
)
from app.schemas.schemas import SubstitutionCandidate
from app.core.config import get_settings

settings = get_settings()


class SubstitutionService:
    """
    Service for handling teacher substitutions.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def mark_teacher_absent(
        self,
        teacher_id: int,
        absence_date: date,
        reason: Optional[str] = None,
        is_full_day: bool = True,
        absent_slots: Optional[str] = None
    ) -> TeacherAbsence:
        """
        Mark a teacher as absent and create absence record.
        """
        # Check if already marked absent
        existing = self.db.query(TeacherAbsence).filter(
            TeacherAbsence.teacher_id == teacher_id,
            TeacherAbsence.absence_date == absence_date
        ).first()
        
        if existing:
            return existing
        
        absence = TeacherAbsence(
            teacher_id=teacher_id,
            absence_date=absence_date,
            reason=reason,
            is_full_day=is_full_day,
            absent_slots=absent_slots
        )
        self.db.add(absence)
        self.db.commit()
        self.db.refresh(absence)
        
        return absence
    
    def get_affected_allocations(
        self,
        teacher_id: int,
        absence_date: date
    ) -> List[Allocation]:
        """
        Get all allocations affected by a teacher's absence.
        Returns allocations for the day of the week matching the absence date.
        """
        # Get day of week from absence_date (0=Monday, 6=Sunday)
        day_of_week = absence_date.weekday()
        
        if day_of_week > 4:  # Weekend
            return []
        
        allocations = self.db.query(Allocation).filter(
            Allocation.teacher_id == teacher_id,
            Allocation.day == day_of_week
        ).all()
        
        return allocations
    
    def find_candidates(
        self,
        allocation: Allocation,
        substitution_date: date
    ) -> List[SubstitutionCandidate]:
        """
        Find and rank substitute candidates for an allocation.
        
        Returns candidates sorted by score (highest first).
        """
        subject_id = allocation.subject_id
        day = allocation.day
        slot = allocation.slot
        original_teacher_id = allocation.teacher_id
        
        # Get subject info
        subject = self.db.query(Subject).filter(Subject.id == subject_id).first()
        if not subject:
            return []
        
        # Get teachers who can teach this subject
        qualified_teacher_ids = self.db.execute(
            teacher_subjects.select().where(teacher_subjects.c.subject_id == subject_id)
        ).fetchall()
        
        qualified_ids = [row.teacher_id for row in qualified_teacher_ids]
        
        # Get all active teachers
        all_teachers = self.db.query(Teacher).filter(
            Teacher.is_active == True,
            Teacher.id != original_teacher_id  # Exclude the absent teacher
        ).all()
        
        # Get teachers who are busy in this slot
        busy_teachers = self.db.query(Allocation.teacher_id).filter(
            Allocation.day == day,
            Allocation.slot == slot
        ).distinct().all()
        busy_teacher_ids = {t[0] for t in busy_teachers}
        
        # Check for other absences on this date
        other_absences = self.db.query(TeacherAbsence.teacher_id).filter(
            TeacherAbsence.absence_date == substitution_date
        ).all()
        absent_teacher_ids = {t[0] for t in other_absences}
        
        # Get effectiveness scores for this subject
        effectiveness_map = {}
        for row in qualified_teacher_ids:
            effectiveness_map[row.teacher_id] = row.effectiveness_score or 0.8
        
        # Calculate max load for normalization
        max_load = max(
            (self._get_teacher_current_load(t.id) for t in all_teachers),
            default=1
        )
        if max_load == 0:
            max_load = 1
        
        candidates = []
        
        for teacher in all_teachers:
            # Skip busy teachers
            if teacher.id in busy_teacher_ids:
                continue
            
            # Skip absent teachers
            if teacher.id in absent_teacher_ids:
                continue
            
            # Check day availability
            available_days = [int(d) for d in teacher.available_days.split(",")]
            if day not in available_days:
                continue
            
            # Check if teacher can teach the subject
            subject_match = teacher.id in qualified_ids
            
            # Get current load
            current_load = self._get_teacher_current_load(teacher.id)
            
            # Check max load constraint
            if current_load >= teacher.max_hours_per_week:
                continue
            
            # Calculate score
            effectiveness = effectiveness_map.get(teacher.id, 0.5)
            normalized_load = current_load / max_load
            
            score = (
                settings.SUBJECT_MATCH_WEIGHT * (1.0 if subject_match else 0.0) +
                settings.WORKLOAD_WEIGHT * (1.0 - normalized_load) +
                settings.EFFECTIVENESS_WEIGHT * effectiveness +
                settings.EXPERIENCE_WEIGHT * teacher.experience_score
            )
            
            candidate = SubstitutionCandidate(
                teacher_id=teacher.id,
                teacher_name=teacher.name,
                score=round(score, 3),
                subject_match=subject_match,
                current_load=current_load,
                effectiveness=effectiveness,
                experience_score=teacher.experience_score
            )
            candidates.append(candidate)
        
        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        
        return candidates
    
    def assign_substitute(
        self,
        allocation_id: int,
        substitution_date: date,
        substitute_teacher_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Tuple[Optional[Substitution], str]:
        """
        Assign a substitute teacher to an allocation.
        
        If substitute_teacher_id is not provided, automatically selects the best candidate.
        
        Returns (Substitution, message) tuple.
        """
        # Get allocation
        allocation = self.db.query(Allocation).filter(
            Allocation.id == allocation_id
        ).first()
        
        if not allocation:
            return None, "Allocation not found"
        
        # Check if already substituted
        existing = self.db.query(Substitution).filter(
            Substitution.allocation_id == allocation_id,
            Substitution.substitution_date == substitution_date,
            Substitution.status.in_([SubstitutionStatus.PENDING, SubstitutionStatus.ASSIGNED])
        ).first()
        
        if existing:
            return None, "Substitution already exists for this allocation and date"
        
        # Find candidates
        candidates = self.find_candidates(allocation, substitution_date)
        
        if not candidates:
            return None, "No substitute candidates available"
        
        # Select substitute
        if substitute_teacher_id:
            # Use specified teacher if they're a valid candidate
            selected = next(
                (c for c in candidates if c.teacher_id == substitute_teacher_id),
                None
            )
            if not selected:
                return None, "Specified teacher is not a valid candidate"
        else:
            # Use top candidate
            selected = candidates[0]
        
        # Create substitution record
        substitution = Substitution(
            allocation_id=allocation_id,
            original_teacher_id=allocation.teacher_id,
            substitute_teacher_id=selected.teacher_id,
            substitution_date=substitution_date,
            status=SubstitutionStatus.ASSIGNED,
            substitute_score=selected.score,
            reason=reason
        )
        
        self.db.add(substitution)
        self.db.commit()
        self.db.refresh(substitution)
        
        # Get names for notification
        original_teacher = self.db.query(Teacher).filter(
            Teacher.id == allocation.teacher_id
        ).first()
        substitute_teacher = self.db.query(Teacher).filter(
            Teacher.id == selected.teacher_id
        ).first()
        subject = self.db.query(Subject).filter(
            Subject.id == allocation.subject_id
        ).first()
        
        message = (
            f"Substitution assigned: {substitute_teacher.name} will cover "
            f"{subject.name} (originally {original_teacher.name}) "
            f"on {substitution_date}"
        )
        
        return substitution, message
    
    def auto_substitute_for_absence(
        self,
        teacher_id: int,
        absence_date: date,
        reason: Optional[str] = None
    ) -> List[Tuple[Substitution, str]]:
        """
        Automatically create substitutions for all affected allocations.
        
        This is the main entry point for the automated substitution workflow.
        """
        # Mark teacher absent
        self.mark_teacher_absent(teacher_id, absence_date, reason)
        
        # Get affected allocations
        allocations = self.get_affected_allocations(teacher_id, absence_date)
        
        results = []
        
        for allocation in allocations:
            # Skip lab continuation slots (handle as part of main lab slot)
            if allocation.is_lab_continuation:
                continue
            
            substitution, message = self.assign_substitute(
                allocation.id,
                absence_date,
                reason=reason
            )
            results.append((substitution, message))
        
        return results
    
    def cancel_substitution(self, substitution_id: int) -> bool:
        """Cancel a substitution."""
        substitution = self.db.query(Substitution).filter(
            Substitution.id == substitution_id
        ).first()
        
        if not substitution:
            return False
        
        substitution.status = SubstitutionStatus.CANCELLED
        self.db.commit()
        
        return True
    
    def get_active_substitutions(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None
    ) -> List[Substitution]:
        """Get active substitutions, optionally filtered by date range."""
        query = self.db.query(Substitution).filter(
            Substitution.status.in_([SubstitutionStatus.PENDING, SubstitutionStatus.ASSIGNED])
        )
        
        if from_date:
            query = query.filter(Substitution.substitution_date >= from_date)
        if to_date:
            query = query.filter(Substitution.substitution_date <= to_date)
        
        return query.order_by(Substitution.substitution_date).all()
    
    def _get_teacher_current_load(self, teacher_id: int) -> int:
        """Get current weekly load for a teacher."""
        count = self.db.query(func.count(Allocation.id)).filter(
            Allocation.teacher_id == teacher_id
        ).scalar()
        
        return count or 0
