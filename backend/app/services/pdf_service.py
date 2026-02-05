"""
PDF Generation Service for Official College Timetable Export.
READ-ONLY service - does not modify any timetable data.

Generates PDF that EXACTLY matches the K.Ramakrishnan College timetable format.
Uses Times-Roman font for formal, classic appearance.
"""
from io import BytesIO
from typing import List, Dict, Optional, Set
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from sqlalchemy.orm import Session, joinedload
from app.db.models import Allocation, Semester, Teacher, Subject
from app.core.config import get_settings

settings = get_settings()

# ============================================================================
# CONFIGURATION - Matching KR College Format
# ============================================================================
ACADEMIC_YEAR = "2025-26"
SEMESTER_TYPE = "EVEN SEMESTER"
COLLEGE_NAME = "K.RAMAKRISHNAN COLLEGE OF TECHNOLOGY(Autonomous)"
DEPARTMENT_NAME = "DEPARTMENT OF ARTIFICIAL INTELLIGENCE & MACHINE LEARNING"

# Font settings - Classic Times Roman for formal look
FONT_REGULAR = 'Times-Roman'
FONT_BOLD = 'Times-Bold'
FONT_ITALIC = 'Times-Italic'

# Colors matching the reference image
COLORS = {
    "header_blue": colors.Color(0.68, 0.85, 0.9),  # Light blue header
    "yellow": colors.Color(1.0, 1.0, 0.6),  # Yellow for theory
    "orange": colors.Color(1.0, 0.8, 0.4),  # Orange
    "red": colors.Color(0.95, 0.5, 0.5),  # Red for labs
    "grey": colors.Color(0.85, 0.85, 0.85),  # Grey for breaks
    "white": colors.white,
    "black": colors.black,
    "border": colors.black,
}

DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI"]


class TimetablePDFService:
    """Service for generating official KR College timetable PDFs."""
    
    def __init__(self, db: Session):
        self.db = db
        self.styles = getSampleStyleSheet()
    
    def _get_all_semesters(self) -> List[Semester]:
        """Get all semesters that have allocations."""
        semester_ids = self.db.query(Allocation.semester_id).distinct().all()
        semester_ids = [s[0] for s in semester_ids]
        
        if not semester_ids:
            return []
        
        return self.db.query(Semester).filter(
            Semester.id.in_(semester_ids)
        ).order_by(Semester.year, Semester.code).all()
    
    def _get_semester_allocations(self, semester_id: int) -> tuple:
        """Get all allocations for a semester organized by day and slot."""
        allocations = self.db.query(Allocation).options(
            joinedload(Allocation.teacher),
            joinedload(Allocation.subject),
            joinedload(Allocation.room)
        ).filter(
            Allocation.semester_id == semester_id
        ).all()
        
        # Organize into a grid
        grid = {}
        for day in range(5):
            grid[day] = {}
            for slot in range(settings.SLOTS_PER_DAY):
                grid[day][slot] = None
        
        for alloc in allocations:
            grid[alloc.day][alloc.slot] = alloc
        
        return grid, allocations
    
    def _get_subject_mnemonic(self, subject: Subject) -> str:
        """Generate a mnemonic from subject name."""
        name = subject.name
        words = name.split()
        if len(words) == 1:
            return name[:4].upper()
        # Take first letter of each significant word
        mnemonic = ''.join(w[0].upper() for w in words if len(w) > 2)[:4]
        return mnemonic if mnemonic else name[:3].upper()
    
    def _get_component_suffix(self, alloc) -> str:
        """Get component type suffix for display."""
        if alloc.component_type:
            ct = alloc.component_type.value
            if ct == "lab":
                return "(P)"
            elif ct == "tutorial":
                return "(T)"
        return "(L)"
    
    def _build_header_section(self, semester: Semester) -> Table:
        """Build the header section matching the reference format."""
        # Top section with college info and format number
        header_data = [
            # Row 1: Format info on right
            ["***", COLLEGE_NAME, "Format No:CPS-01"],
            # Row 2: Revision info  
            ["REVISION", DEPARTMENT_NAME, "Issue No: 01"],
            # Row 3: Date and title
            ["DATE", f"CLASS TIME TABLE - {semester.name} - ACADEMIC YEAR {ACADEMIC_YEAR} ({SEMESTER_TYPE})", f"Date: 01.07.05"],
        ]
        
        col_widths = [2.2*cm, 21*cm, 4.5*cm]
        header_table = Table(header_data, colWidths=col_widths)
        header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTSIZE', (1, 0), (1, 0), 14),  # College name larger
            ('FONTSIZE', (1, 1), (1, 1), 11),   # Dept name
            ('FONTSIZE', (1, 2), (1, 2), 12),  # Title
            ('FONTNAME', (1, 0), (1, 2), FONT_BOLD),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        return header_table
    
    def _build_info_row(self, semester: Semester) -> Table:
        """Build the info row with HOD, Class Advisor, etc."""
        info_data = [
            ["HOD", "Dr.T.Avudaiappan", "SECTION", "A", "CHAIR PERSON", "Mr. P. B. Aravind Prasad", "ROOM NO.", "LHC104"],
            ["CLASS ADVISOR", "Mrs.E.SRI SANTHOSHINI", "STRENGTH", "62", "ASST.CLASS ADVISOR", "***", "CLASS REP", "***"],
        ]
        
        col_widths = [2.8*cm, 4.5*cm, 2.2*cm, 1.5*cm, 4*cm, 5*cm, 2.2*cm, 2.2*cm]
        info_table = Table(info_data, colWidths=col_widths)
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), FONT_BOLD),
            ('FONTNAME', (2, 0), (2, -1), FONT_BOLD),
            ('FONTNAME', (4, 0), (4, -1), FONT_BOLD),
            ('FONTNAME', (6, 0), (6, -1), FONT_BOLD),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, COLORS["black"]),
            ('BACKGROUND', (0, 0), (-1, -1), COLORS["header_blue"]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        return info_table
    
    def _build_timetable_grid(self, semester: Semester, grid: Dict) -> Table:
        """Build the main timetable grid matching the reference format."""
        # Period timings - slightly larger text
        timings = [
            "8:45 a.m. -\n9:45 a.m.",
            "9:45 a.m. -\n10:45 a.m.",
            "10:45 a.m.-\n11:00 a.m.",  # Break
            "11:00 a.m.-\n12:00 p.m.",
            "12:00 p.m.-\n01:00 p.m.",  # Lunch
            "01:00 p.m.-\n02:00 p.m.",
            "02:00 p.m.-\n02:50 p.m.",
            "02:50 p.m.-\n03:05 p.m.",  # Break
            "03:05 p.m.-\n03:55p.m.",
            "03:55 p.m.-\n04:45p.m.",
        ]
        
        # Header rows
        header_row1 = ["DAYS", "1", "2", "BREAK", "3", "LUNCH", "4", "5", "BREAK", "6", "7"]
        header_row2 = ["TIMINGS"] + timings
        
        # Build data rows
        data = [header_row1, header_row2]
        
        # Map slots to columns (accounting for break/lunch columns)
        slot_to_col = {0: 1, 1: 2, 2: 4, 3: 6, 4: 7, 5: 9, 6: 10}
        
        for day_idx, day_name in enumerate(DAY_NAMES):
            row = [day_name]
            
            for col_idx in range(1, 11):
                if col_idx == 3:  # Break
                    row.append("BREAK")
                elif col_idx == 5:  # Lunch
                    row.append("LUNCH")
                elif col_idx == 8:  # Break
                    row.append("BREAK")
                else:
                    # Find slot for this column
                    slot_idx = None
                    for s, c in slot_to_col.items():
                        if c == col_idx:
                            slot_idx = s
                            break
                    
                    if slot_idx is not None:
                        alloc = grid.get(day_idx, {}).get(slot_idx)
                        if alloc:
                            mnemonic = self._get_subject_mnemonic(alloc.subject)
                            suffix = self._get_component_suffix(alloc)
                            cell_text = f"{mnemonic}{suffix}"
                        else:
                            cell_text = ""
                    else:
                        cell_text = ""
                    row.append(cell_text)
            
            data.append(row)
        
        # LARGER Column widths for better readability
        col_widths = [2.0*cm, 2.5*cm, 2.5*cm, 1.6*cm, 2.5*cm, 2.0*cm, 2.5*cm, 2.5*cm, 1.6*cm, 2.5*cm, 2.5*cm]
        row_heights = [0.9*cm, 1.1*cm] + [1.1*cm] * 5  # Taller rows
        
        table = Table(data, colWidths=col_widths, rowHeights=row_heights)
        
        # Build style commands with Times-Roman font
        style_commands = [
            # Headers - LARGER
            ('FONTNAME', (0, 0), (-1, 1), FONT_BOLD),
            ('FONTSIZE', (0, 0), (-1, 0), 11),  # Period numbers
            ('FONTSIZE', (0, 1), (-1, 1), 7),   # Timings
            ('BACKGROUND', (0, 0), (-1, 1), COLORS["header_blue"]),
            
            # Days column - LARGER
            ('FONTNAME', (0, 2), (0, -1), FONT_BOLD),
            ('FONTSIZE', (0, 2), (0, -1), 11),
            ('BACKGROUND', (0, 2), (0, -1), COLORS["header_blue"]),
            
            # Content - LARGER
            ('FONTNAME', (1, 2), (-1, -1), FONT_BOLD),
            ('FONTSIZE', (1, 2), (-1, -1), 10),
            
            # Alignment
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid - slightly thicker
            ('GRID', (0, 0), (-1, -1), 1, COLORS["black"]),
            ('BOX', (0, 0), (-1, -1), 2, COLORS["black"]),
            
            # Break columns background (columns 3, 5, 8)
            ('BACKGROUND', (3, 0), (3, -1), COLORS["grey"]),
            ('BACKGROUND', (5, 0), (5, -1), COLORS["grey"]),
            ('BACKGROUND', (8, 0), (8, -1), COLORS["grey"]),
        ]
        
        # Apply cell colors based on content type
        for day_idx in range(5):
            row_idx = day_idx + 2  # +2 for header rows
            for slot_idx, col_idx in slot_to_col.items():
                alloc = grid.get(day_idx, {}).get(slot_idx)
                if alloc:
                    if alloc.component_type and alloc.component_type.value == "lab":
                        style_commands.append(
                            ('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), COLORS["red"])
                        )
                    elif getattr(alloc, 'is_elective', False):
                        style_commands.append(
                            ('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), COLORS["orange"])
                        )
                    else:
                        style_commands.append(
                            ('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), COLORS["yellow"])
                        )
        
        table.setStyle(TableStyle(style_commands))
        return table
    
    def _build_subject_table(self, allocations: List) -> Table:
        """Build the subject details table."""
        # Header
        header = [
            "SUB CODE", "SUBJECT NAME", "MNEMONIC", 
            "L-LECTURE,T-TUTORIAL,P-PRACTICAL,S-SELF STUDY",
            "CREDIT", "STAFF NAME(M)", "DEPT", "TOTAL HOURS"
        ]
        
        # Collect unique subjects
        subjects_seen: Set[int] = set()
        rows = [header]
        total_hours = 0
        
        for alloc in allocations:
            if alloc.subject.id not in subjects_seen:
                subjects_seen.add(alloc.subject.id)
                subj = alloc.subject
                mnemonic = self._get_subject_mnemonic(subj)
                
                # Calculate total hours for this subject in timetable
                hours = sum(1 for a in allocations if a.subject.id == subj.id)
                total_hours += hours
                
                # Determine LTPS format
                comp_type = ""
                if alloc.component_type:
                    if alloc.component_type.value == "lab":
                        comp_type = "PE - II"
                    elif alloc.component_type.value == "tutorial":
                        comp_type = "T"
                    else:
                        comp_type = ""
                
                # Credit calculation - use correct attribute names
                theory_hrs = getattr(subj, 'theory_hours_per_week', 3) or 3
                lab_hrs = getattr(subj, 'lab_hours_per_week', 0) or 0
                credit = theory_hrs + (lab_hrs // 2) if lab_hrs else theory_hrs
                
                rows.append([
                    subj.code,
                    subj.name[:40],
                    mnemonic,
                    comp_type,
                    str(credit) if credit else "3",
                    alloc.teacher.name if alloc.teacher else "***",
                    "AI",
                    str(hours)
                ])
        
        # Add total row
        rows.append(["", "", "", "", "", "", "TOTAL HOURS", str(total_hours)])
        
        # Create table - LARGER columns
        col_widths = [2*cm, 6.5*cm, 2.2*cm, 4.5*cm, 1.5*cm, 5.5*cm, 1.5*cm, 2.2*cm]
        table = Table(rows, colWidths=col_widths)
        
        table.setStyle(TableStyle([
            # Header
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 0), (-1, 0), COLORS["header_blue"]),
            
            # Content - Times Roman
            ('FONTNAME', (0, 1), (-1, -1), FONT_REGULAR),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            
            # Alignment
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (4, 0), (4, -1), 'CENTER'),
            ('ALIGN', (7, 0), (7, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.75, COLORS["black"]),
            ('BOX', (0, 0), (-1, -1), 1, COLORS["black"]),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            
            # Total row
            ('FONTNAME', (0, -1), (-1, -1), FONT_BOLD),
        ]))
        
        return table
    
    def _build_signature_section(self) -> Table:
        """Build the signature footer section."""
        sig_data = [
            ["Dept.T.T. Coordinator", "", "HoD-AI", "", "CoT", "", "HAA", ""]
        ]
        
        col_widths = [4*cm, 3.5*cm, 2.5*cm, 3.5*cm, 2*cm, 3.5*cm, 2*cm, 3.5*cm]
        table = Table(sig_data, colWidths=col_widths)
        
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_BOLD),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 25),
        ]))
        
        return table
    
    def _build_semester_page(self, semester: Semester) -> List:
        """Build complete PDF page for a semester."""
        elements = []
        grid, allocations = self._get_semester_allocations(semester.id)
        
        # Header section
        elements.append(self._build_header_section(semester))
        elements.append(Spacer(1, 3*mm))
        
        # Info row
        elements.append(self._build_info_row(semester))
        elements.append(Spacer(1, 4*mm))
        
        # Timetable grid
        elements.append(self._build_timetable_grid(semester, grid))
        elements.append(Spacer(1, 6*mm))
        
        # Subject table
        elements.append(self._build_subject_table(allocations))
        elements.append(Spacer(1, 10*mm))
        
        # Signature section
        elements.append(self._build_signature_section())
        
        return elements
    
    def generate_all_timetables_pdf(self) -> bytes:
        """
        Generate PDF containing all class timetables in official KR College format.
        READ-ONLY operation - uses existing allocation data only.
        
        Returns:
            bytes: PDF file content
        """
        buffer = BytesIO()
        
        # Create document in landscape orientation with narrow margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=0.6*cm,
            leftMargin=0.6*cm,
            topMargin=0.4*cm,
            bottomMargin=0.4*cm
        )
        
        elements = []
        
        # Get all semesters with allocations
        semesters = self._get_all_semesters()
        
        if not semesters:
            # No timetables generated yet
            elements.append(Spacer(1, 5*cm))
            elements.append(Paragraph(
                "No Timetable Generated",
                ParagraphStyle(
                    name='EmptyTitle',
                    fontName=FONT_BOLD,
                    fontSize=18,
                    alignment=TA_CENTER
                )
            ))
            elements.append(Spacer(1, 1*cm))
            elements.append(Paragraph(
                "Please generate a timetable first before exporting to PDF.",
                ParagraphStyle(
                    name='EmptySubtitle',
                    fontName=FONT_REGULAR,
                    fontSize=12,
                    alignment=TA_CENTER,
                    textColor=colors.gray
                )
            ))
        else:
            # Add each semester timetable on a new page
            for i, semester in enumerate(semesters):
                elements.extend(self._build_semester_page(semester))
                if i < len(semesters) - 1:
                    elements.append(PageBreak())
        
        # Build PDF
        doc.build(elements)
        
        return buffer.getvalue()
    
    def get_timetable_count(self) -> int:
        """Get count of semesters with generated timetables."""
        return self.db.query(Allocation.semester_id).distinct().count()
