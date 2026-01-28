-- ============================================================================
-- College Department Timetable Generator - Database Schema
-- PostgreSQL / SQLite Compatible
-- ============================================================================

-- Drop tables if exist (for clean recreation)
DROP TABLE IF EXISTS substitutions CASCADE;
DROP TABLE IF EXISTS teacher_absences CASCADE;
DROP TABLE IF EXISTS allocations CASCADE;
DROP TABLE IF EXISTS teacher_subjects CASCADE;
DROP TABLE IF EXISTS semesters CASCADE;
DROP TABLE IF EXISTS subjects CASCADE;
DROP TABLE IF EXISTS teachers CASCADE;
DROP TABLE IF EXISTS rooms CASCADE;

-- ============================================================================
-- ROOMS
-- Physical rooms/classrooms
-- ============================================================================
CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    room_type VARCHAR(20) DEFAULT 'lecture' CHECK (room_type IN ('lecture', 'lab', 'seminar')),
    is_available BOOLEAN DEFAULT TRUE,
    
    -- Scalability: Future support for multiple departments/colleges
    dept_id INTEGER,
    college_id INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TEACHERS
-- Faculty members
-- ============================================================================
CREATE TABLE teachers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(200) UNIQUE,
    phone VARCHAR(20),
    
    -- Constraints & scoring
    max_hours_per_week INTEGER DEFAULT 20 CHECK (max_hours_per_week > 0),
    max_consecutive_classes INTEGER DEFAULT 3 CHECK (max_consecutive_classes > 0),
    experience_years INTEGER DEFAULT 1 CHECK (experience_years >= 0),
    experience_score FLOAT DEFAULT 0.5 CHECK (experience_score >= 0 AND experience_score <= 1),
    
    -- Availability: Comma-separated day indices (0=Monday, 4=Friday)
    available_days VARCHAR(50) DEFAULT '0,1,2,3,4',
    
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Scalability
    dept_id INTEGER,
    college_id INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SUBJECTS
-- Courses/Subjects
-- ============================================================================
CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    
    weekly_hours INTEGER DEFAULT 3 CHECK (weekly_hours > 0),
    subject_type VARCHAR(20) DEFAULT 'theory' CHECK (subject_type IN ('theory', 'lab', 'tutorial')),
    
    -- For labs: number of consecutive slots needed
    consecutive_slots INTEGER DEFAULT 1 CHECK (consecutive_slots > 0),
    
    -- Scalability
    dept_id INTEGER,
    college_id INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TEACHER_SUBJECTS
-- Many-to-Many: Which teachers can teach which subjects
-- ============================================================================
CREATE TABLE teacher_subjects (
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
    
    -- How effective is this teacher for this subject (0.0 - 1.0)
    effectiveness_score FLOAT DEFAULT 0.8 CHECK (effectiveness_score >= 0 AND effectiveness_score <= 1),
    
    PRIMARY KEY (teacher_id, subject_id)
);

-- ============================================================================
-- SEMESTERS
-- Classes/Sections (e.g., "CSE 3rd Sem Section A")
-- ============================================================================
CREATE TABLE semesters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    
    year INTEGER DEFAULT 2 CHECK (year >= 1 AND year <= 6),
    section VARCHAR(10) DEFAULT 'A',
    student_count INTEGER DEFAULT 60 CHECK (student_count > 0),
    
    -- Scalability
    dept_id INTEGER,
    college_id INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- ALLOCATIONS
-- Timetable entries: Teacher teaches Subject to Semester in Room at Day/Slot
-- ============================================================================
CREATE TABLE allocations (
    id SERIAL PRIMARY KEY,
    
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    semester_id INTEGER NOT NULL REFERENCES semesters(id),
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    
    -- Time slot info
    day INTEGER NOT NULL CHECK (day >= 0 AND day <= 4),  -- 0=Monday, 4=Friday
    slot INTEGER NOT NULL CHECK (slot >= 0 AND slot <= 7),  -- 8 periods/day
    
    -- For multi-slot sessions (labs)
    is_lab_continuation BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraint: One class per semester per day/slot
    UNIQUE (semester_id, day, slot)
);

-- Create indexes for faster lookups
CREATE INDEX idx_allocations_teacher ON allocations(teacher_id);
CREATE INDEX idx_allocations_semester ON allocations(semester_id);
CREATE INDEX idx_allocations_day_slot ON allocations(day, slot);

-- ============================================================================
-- TEACHER_ABSENCES
-- Records when teachers are absent
-- ============================================================================
CREATE TABLE teacher_absences (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    absence_date DATE NOT NULL,
    reason VARCHAR(500),
    
    -- Full day or specific slots
    is_full_day BOOLEAN DEFAULT TRUE,
    absent_slots VARCHAR(50),  -- e.g., "0,1,2" for first 3 periods
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE (teacher_id, absence_date)
);

-- ============================================================================
-- SUBSTITUTIONS
-- Substitute teacher assignments
-- ============================================================================
CREATE TABLE substitutions (
    id SERIAL PRIMARY KEY,
    
    allocation_id INTEGER NOT NULL REFERENCES allocations(id),
    original_teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    substitute_teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    
    substitution_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'assigned', 'completed', 'cancelled')),
    
    -- Scoring info (for transparency/auditing)
    substitute_score FLOAT DEFAULT 0.0,
    reason VARCHAR(500),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_substitutions_date ON substitutions(substitution_date);
CREATE INDEX idx_substitutions_status ON substitutions(status);

-- ============================================================================
-- TRIGGER FUNCTION: Update updated_at timestamp
-- ============================================================================
-- Note: This is PostgreSQL specific. For SQLite, handle in application code.

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables that need it
CREATE TRIGGER update_rooms_updated_at BEFORE UPDATE ON rooms FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_teachers_updated_at BEFORE UPDATE ON teachers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_subjects_updated_at BEFORE UPDATE ON subjects FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_semesters_updated_at BEFORE UPDATE ON semesters FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_allocations_updated_at BEFORE UPDATE ON allocations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_substitutions_updated_at BEFORE UPDATE ON substitutions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
