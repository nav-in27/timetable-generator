"""
CRUD API routes for Rooms.
Multi-department support:
  - A room can be shared by multiple departments (via room_departments junction)
  - dept_id remains as legacy field for backward compat
Section-wise room assignment support:
  - Default classroom assignment per section
  - Hard constraint: a room can only be default for ONE section
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from app.db.session import get_db
from app.db.models import Room, Department, room_departments
from app.schemas.schemas import RoomCreate, RoomUpdate, RoomResponse
from app.core.cache import cache

router = APIRouter(prefix="/rooms", tags=["Rooms"])


def _room_to_response(room: Room) -> dict:
    """Convert Room ORM object to response dict with dept_ids."""
    data = {
        "id": room.id,
        "name": room.name,
        "capacity": room.capacity,
        "room_type": room.room_type,
        "is_available": room.is_available,
        "dept_id": room.dept_id,
        "dept_ids": [d.id for d in room.departments] if room.departments else [],
        "assigned_year": room.assigned_year,
        "assigned_section": room.assigned_section,
        "is_default_classroom": room.is_default_classroom,
        "created_at": room.created_at,
        "updated_at": room.updated_at,
    }
    return data


def _sync_room_departments(db: Session, room_id: int, dept_ids: List[int]):
    """Sync the room_departments junction table for a given room."""
    # Clear existing
    db.execute(
        delete(room_departments).where(room_departments.c.room_id == room_id)
    )
    # Insert new
    for did in dept_ids:
        db.execute(
            room_departments.insert().values(room_id=room_id, dept_id=did)
        )


@router.get("/", response_model=List[RoomResponse])
def list_rooms(
    skip: int = 0,
    limit: int = 100,
    dept_id: Optional[int] = Query(None, description="Filter by department"),
    year: Optional[int] = Query(None, ge=1, le=6, description="Filter by assigned year"),
    section: Optional[str] = Query(None, max_length=10, description="Filter by assigned section"),
    is_default: Optional[bool] = Query(None, description="Filter default classrooms only"),
    db: Session = Depends(get_db)
):
    """Get all rooms with optional filters.
    
    When dept_id is specified, returns rooms that:
    - Have that dept_id in their departments list (junction table), OR
    - Have the legacy dept_id field matching, OR
    - Have no department assigned at all (shared rooms)
    """
    query = db.query(Room)
    if dept_id:
        # Include rooms that are in the junction table for this dept,
        # OR have the legacy dept_id, OR have no dept assignment at all
        room_ids_in_junction = (
            db.query(room_departments.c.room_id)
            .filter(room_departments.c.dept_id == dept_id)
            .subquery()
        )
        query = query.filter(
            (Room.id.in_(select(room_ids_in_junction.c.room_id))) |
            (Room.dept_id == dept_id) |
            (Room.dept_id.is_(None))
        )
    if year is not None:
        query = query.filter(Room.assigned_year == year)
    if section is not None:
        query = query.filter(Room.assigned_section == section)
    if is_default is not None:
        query = query.filter(Room.is_default_classroom == is_default)
    
    rooms = query.offset(skip).limit(limit).all()
    return [_room_to_response(r) for r in rooms]


@router.get("/default-classroom", response_model=Optional[RoomResponse])
def get_default_classroom(
    dept_id: int = Query(..., description="Department ID"),
    year: int = Query(..., ge=1, le=6, description="Year"),
    section: str = Query(..., max_length=10, description="Section"),
    db: Session = Depends(get_db)
):
    """Find the default classroom for a specific section."""
    room = db.query(Room).filter(
        Room.assigned_year == year,
        Room.assigned_section == section,
        Room.is_default_classroom == True,
        Room.is_available == True
    ).first()
    if room:
        return _room_to_response(room)
    return None


@router.get("/{room_id}", response_model=RoomResponse)
def get_room(room_id: int, db: Session = Depends(get_db)):
    """Get a specific room by ID."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return _room_to_response(room)


@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(room_data: RoomCreate, db: Session = Depends(get_db)):
    """Create a new room with optional multi-department assignment."""
    # Check for duplicate name
    existing = db.query(Room).filter(Room.name == room_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Room with this name already exists")
    
    # HARD CONSTRAINT: default classroom uniqueness (scoped per department)
    dept_ids = room_data.dept_ids or []
    if room_data.is_default_classroom and room_data.assigned_year and room_data.assigned_section:
        _validate_default_classroom(db, room_data.assigned_year, room_data.assigned_section, dept_ids=dept_ids, exclude_room_id=None)
    
    # Extract dept_ids before creating the Room ORM object
    dept_ids = room_data.dept_ids or []
    room_dict = room_data.model_dump(exclude={"dept_ids"})
    
    # Set legacy dept_id to first dept if available and not explicitly set
    if not room_dict.get("dept_id") and dept_ids:
        room_dict["dept_id"] = dept_ids[0]
    
    room = Room(**room_dict)
    db.add(room)
    db.flush()  # Get the room.id
    
    # Sync junction table
    if dept_ids:
        _sync_room_departments(db, room.id, dept_ids)
    
    db.commit()
    db.refresh(room)
    cache.invalidate_tags(["rooms", "timetable"])
    return _room_to_response(room)


@router.put("/{room_id}", response_model=RoomResponse)
def update_room(room_id: int, room_data: RoomUpdate, db: Session = Depends(get_db)):
    """Update a room."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    update_data = room_data.model_dump(exclude_unset=True)
    dept_ids = update_data.pop("dept_ids", None)
    
    # Compute the resulting state after update for validation
    result_year = update_data.get("assigned_year", room.assigned_year)
    result_section = update_data.get("assigned_section", room.assigned_section)
    result_is_default = update_data.get("is_default_classroom", room.is_default_classroom)
    
    # HARD CONSTRAINT: validate default classroom uniqueness (scoped per department)
    result_dept_ids = dept_ids if dept_ids is not None else [d.id for d in room.departments] if room.departments else ([room.dept_id] if room.dept_id else [])
    if result_is_default and result_year and result_section:
        _validate_default_classroom(db, result_year, result_section, dept_ids=result_dept_ids, exclude_room_id=room_id)
    
    for key, value in update_data.items():
        setattr(room, key, value)
    
    # Sync junction table if dept_ids was provided
    if dept_ids is not None:
        _sync_room_departments(db, room.id, dept_ids)
        # Also update legacy dept_id
        if dept_ids:
            room.dept_id = dept_ids[0]
        else:
            room.dept_id = None
    
    db.commit()
    db.refresh(room)
    cache.invalidate_tags(["rooms", "timetable"])
    return _room_to_response(room)


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(room_id: int, db: Session = Depends(get_db)):
    """Delete a room."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Junction entries are auto-deleted via CASCADE
    db.delete(room)
    db.commit()
    cache.invalidate_tags(["rooms", "timetable"])
    return None


# ----- Helpers -----

def _validate_default_classroom(
    db: Session,
    year: int,
    section: str,
    dept_ids: Optional[List[int]] = None,
    exclude_room_id: Optional[int] = None
):
    """
    Enforce: only ONE room can be the default classroom for a given
    (dept, year, section) combination.

    Different departments MAY have the same section letter (e.g. AIML-2A
    and AIDS-2A are separate classes and each needs its own default room).
    """
    query = db.query(Room).filter(
        Room.is_default_classroom == True,
        Room.assigned_year == year,
        Room.assigned_section == section,
    )
    if exclude_room_id is not None:
        query = query.filter(Room.id != exclude_room_id)

    # Scope to the same department(s) — only conflict if they share a dept
    if dept_ids:
        # A conflict exists only if another default room is assigned to
        # one of the same departments for that year/section.
        overlapping_room_ids = (
            db.query(room_departments.c.room_id)
            .filter(room_departments.c.dept_id.in_(dept_ids))
            .subquery()
        )
        from sqlalchemy import select
        query = query.filter(
            (Room.id.in_(select(overlapping_room_ids.c.room_id)))
            | (Room.dept_id.in_(dept_ids))
        )

    existing = query.first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Room '{existing.name}' is already the default classroom "
                f"for Year {year} Section {section}. "
                f"Remove that assignment first."
            )
        )
