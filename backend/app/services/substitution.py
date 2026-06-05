"""
Strict Same-Class Teacher Substitution Service.

POLICY: When a teacher is absent, ONLY show teachers who:
1. Already teach THAT SAME CLASS (semester) in any other period
2. Are FREE in the specific day/slot
3. Are not the absent teacher
4. Belong to the same department as the class

NO subject qualification matching.
NO cross-class or cross-department search.
NO automatic fallback to wider pools.

Admin may manually override if needed.
"""
from datetime import date
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import (
    Teacher, Subject, Allocation, TeacherAbsence, Substitution,
    SubstitutionStatus
)
from app.schemas.schemas import SubstitutionCandidate


class SubstitutionService:
    """
    Strict same-class substitution service.
    Only considers teachers already assigned to the same class.
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
        Find substitute candidates using STRICT SAME-CLASS policy.
        
        Only returns teachers who:
        1. Already teach THIS SAME CLASS (semester_id) in any other period
        2. Are FREE in the specific day/slot
        3. Are not the absent teacher
        4. Are not absent themselves on this date
        
        NO subject qualification matching.
        NO cross-class or cross-department search.
        NO global fallback.
        """
        day = allocation.day
        slot = allocation.slot
        original_teacher_id = allocation.teacher_id
        semester_id = allocation.semester_id
        
        # ── STEP 1: Get all teachers assigned to THIS SAME CLASS ──
        # From the allocations table — teachers who teach ANY subject
        # to this class in ANY period.
        same_class_teacher_ids = self.db.query(
            Allocation.teacher_id
        ).filter(
            Allocation.semester_id == semester_id,
            Allocation.teacher_id != original_teacher_id  # Exclude absent teacher
        ).distinct().all()
        
        same_class_teacher_ids = {t[0] for t in same_class_teacher_ids}
        
        if not same_class_teacher_ids:
            return []
        
        # ── STEP 2: Get teachers who are BUSY in this specific slot ──
        busy_teachers = self.db.query(Allocation.teacher_id).filter(
            Allocation.day == day,
            Allocation.slot == slot
        ).distinct().all()
        busy_teacher_ids = {t[0] for t in busy_teachers}
        
        # ── STEP 3: Get teachers who are ABSENT on this date ──
        other_absences = self.db.query(TeacherAbsence.teacher_id).filter(
            TeacherAbsence.absence_date == substitution_date
        ).all()
        absent_teacher_ids = {t[0] for t in other_absences}
        
        # ── STEP 3b: Exclude co-batch teachers (MULTI-FACULTY LAB AWARENESS) ──
        # When the original allocation has a batch_id, other teachers assigned to
        # DIFFERENT batches of the same subject in the same slot are already teaching
        # and cannot substitute. This prevents offering a teacher who is already
        # running B2 as a substitute for B1's absent teacher.
        co_batch_teacher_ids: set = set()
        if getattr(allocation, 'batch_id', None):
            co_batch_allocs = self.db.query(Allocation.teacher_id).filter(
                Allocation.semester_id == semester_id,
                Allocation.subject_id == allocation.subject_id,
                Allocation.day == day,
                Allocation.slot == slot,
                Allocation.batch_id.isnot(None),
                Allocation.batch_id != allocation.batch_id,  # Other batches
            ).distinct().all()
            co_batch_teacher_ids = {t[0] for t in co_batch_allocs}
        
        # ── STEP 4: Build candidate list ──
        candidates = []
        
        for teacher_id in same_class_teacher_ids:
            # Skip busy teachers (not free in this slot)
            if teacher_id in busy_teacher_ids:
                continue
            
            # Skip absent teachers
            if teacher_id in absent_teacher_ids:
                continue
            
            # Skip co-batch teachers (already teaching another batch in this slot)
            if teacher_id in co_batch_teacher_ids:
                continue
            
            # Get teacher info (must be active)
            teacher = self.db.query(Teacher).filter(
                Teacher.id == teacher_id,
                Teacher.is_active == True
            ).first()
            
            if not teacher:
                continue
            
            # Get subjects this teacher already handles for THIS class
            class_subjects = self.db.query(Subject.name, Subject.code).join(
                Allocation, Allocation.subject_id == Subject.id
            ).filter(
                Allocation.teacher_id == teacher_id,
                Allocation.semester_id == semester_id
            ).distinct().all()
            
            class_subject_list = [
                f"{s.code} ({s.name})" for s in class_subjects
            ]
            
            # Get current weekly load (total allocations across all classes)
            current_load = self._get_teacher_current_load(teacher_id)
            
            # Build candidate — no scoring, strict policy
            candidate = SubstitutionCandidate(
                teacher_id=teacher.id,
                teacher_name=teacher.name,
                teacher_code=getattr(teacher, 'teacher_code', None) or '',
                score=0.0,
                subject_match=False,  # Not used in strict mode
                current_load=current_load,
                effectiveness=0.0,
                experience_score=0.0,
                class_subjects=class_subject_list
            )
            candidates.append(candidate)
        
        # Sort by lowest load first (prefer less-loaded teachers)
        candidates.sort(key=lambda c: c.current_load)
        
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
        
        NEVER auto-assigns. If substitute_teacher_id is not provided,
        selects the candidate with lowest load (but still requires confirmation).
        
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
        
        # Find candidates (strict same-class only)
        candidates = self.find_candidates(allocation, substitution_date)
        
        if not candidates:
            return None, "No internal class teachers available."
        
        # Select substitute
        if substitute_teacher_id:
            # Use specified teacher if they're a valid candidate
            selected = next(
                (c for c in candidates if c.teacher_id == substitute_teacher_id),
                None
            )
            if not selected:
                return None, "Specified teacher is not a valid candidate (must already teach this class)"
        else:
            # Use top candidate (lowest load)
            selected = candidates[0]
        
        # Create substitution record
        substitution = Substitution(
            allocation_id=allocation_id,
            original_teacher_id=allocation.teacher_id,
            substitute_teacher_id=selected.teacher_id,
            substitution_date=substitution_date,
            status=SubstitutionStatus.ASSIGNED,
            substitute_score=0.0,
            reason=reason
        )
        
        self.db.add(substitution)
        self.db.commit()
        self.db.refresh(substitution)
        
        # Get names for log message
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
            f"{subject.name if subject else 'Unknown'} (originally {original_teacher.name}) "
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
        Uses strict same-class policy for each affected slot.
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
        """Get current weekly load (total allocated periods) for a teacher."""
        count = self.db.query(func.count(Allocation.id)).filter(
            Allocation.teacher_id == teacher_id
        ).scalar()
        
        return count or 0
