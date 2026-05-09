# 🎓 College Timetable Generator

A production-grade, full-stack web application for **automated multi-department college timetable generation** with **intelligent teacher substitution**, **elective basket synchronization**, and **structured composite scheduling**. Built with **FastAPI** (Python) and **React 19** (Vite).

---

## ✨ Features

### Core Timetable Engine
- **🔄 Multi-Department Generation** — Generates timetables across departments sequentially with global constraint awareness
- **🧠 3-Phase Algorithm** — Phase 0 (Elective Pre-scheduling) → Phase 1 (Department-wise Generation) → Phase 2 (Global Validation)
- **📋 Resource Management** — Full CRUD for Teachers, Subjects, Classes/Semesters, Rooms, and Departments
- **⏰ 5-Day × 7-Slot Grid** — Monday–Friday with configurable break/lunch slots per semester template
- **🔒 Fixed/Locked Slots** — Pin specific allocations that the generator cannot overwrite
- **📱 Responsive Dashboard** — Works on desktop, tablet, and mobile

### Scheduling Capabilities
- **🧩 Structured Composite Baskets (SCB)** — Schedule theory + lab combos as atomic units (e.g., 3T + 2L weekly)
- **🎯 Elective Basket Scheduling** — Synchronize parallel elective sessions across multiple classes sharing the same year
- **🔬 Parallel Lab Batches** — Split a class into batches for lab sessions with different teachers running simultaneously
- **🏫 Room Availability Tracking** — Real-time room occupancy grid with type-based filtering (lecture / lab / seminar)
- **📊 Free Periods** — 1–2 free periods per class per week (engine-managed)

### Faculty & Substitution
- **🔁 Intelligent Substitution** — Score-based candidate ranking when a teacher is absent
- **👨‍🏫 Faculty Workload Dashboard** — Per-teacher weekly load visualization
- **📈 Faculty Assignment View** — See which teachers are assigned to which subjects per class
- **🔄 Cross-Department Teacher Sharing** — Teachers can be assigned to subjects in multiple departments

### Data Import & Export
- **📥 Bulk Excel Import** — Import subjects, teachers, classes, rooms, and departments via `.xlsx` uploads
- **📄 PDF Export** — Generate printable timetable PDFs per class or teacher
- **📊 Reports** — Allocation reports, conflict summaries, and workload analytics

### Constraint System

**Hard Constraints (Never Violated):**
- A teacher cannot teach two classes at the same time
- A room cannot be double-booked
- Teacher must be mapped to the subject for that class
- Room capacity must accommodate class size
- Lab sessions are scheduled in continuous 2-slot blocks (never crossing lunch)
- Elective sessions for the same basket run in identical time slots across classes

**Soft Constraints (Optimized):**
- Balanced teacher workload across days
- Avoid 3+ consecutive classes for a teacher
- Prefer morning/midday slots over last-hour
- Minimize same-subject repetition on the same day

### Substitution Scoring Algorithm
```
Score = (0.4 × SubjectMatch) + (0.3 × (1 − NormalizedLoad))
      + (0.2 × Effectiveness) + (0.1 × Experience)
```

---

## 🚀 Quick Start (One Command)

```bash
# Clone the repository
git clone https://github.com/nav-in27/timetable-generator.git
cd timetable-generator

# Run the project (starts both backend and frontend)
python run_project.py
```

This will:
1. ✅ Check and install backend dependencies (`pip install -r requirements.txt`)
2. ✅ Check and install frontend dependencies (`npm install`)
3. ✅ Auto-seed the database with sample data
4. ✅ Start the backend server → `http://localhost:8000`
5. ✅ Start the frontend server → `http://localhost:5173`
6. ✅ Open the app in your default browser

**Requirements:**
- Python 3.10+
- Node.js 18+

---

## 🏗️ Architecture

```
timetable_generator/
├── backend/                        # FastAPI Backend
│   ├── app/
│   │   ├── api/                    # 22 API route modules
│   │   │   ├── allocation.py       # Manual allocation CRUD
│   │   │   ├── dashboard.py        # Dashboard statistics
│   │   │   ├── departments.py      # Department management
│   │   │   ├── elective_baskets.py # Elective basket config
│   │   │   ├── feasibility.py      # Pre-generation feasibility check
│   │   │   ├── fixed_slots.py      # Locked slot management
│   │   │   ├── parallel_lab_baskets.py
│   │   │   ├── reports.py          # Allocation & workload reports
│   │   │   ├── room_availability.py# Real-time room grid
│   │   │   ├── rooms.py            # Room CRUD
│   │   │   ├── rule_toggles.py     # Scheduling rule toggles
│   │   │   ├── semesters.py        # Class/semester CRUD
│   │   │   ├── structured_composite_baskets.py  # SCB config
│   │   │   ├── subjects.py         # Subject CRUD + teacher mapping
│   │   │   ├── substitution.py     # Substitution workflow
│   │   │   ├── teachers.py         # Teacher CRUD + assignments
│   │   │   ├── timetable.py        # Generation trigger & grid API
│   │   │   ├── subject_import.py   # Excel import: subjects
│   │   │   ├── teacher_import.py   # Excel import: teacher mappings
│   │   │   ├── department_import.py# Excel import: departments
│   │   │   ├── class_import.py     # Excel import: classes
│   │   │   └── room_import.py      # Excel import: rooms
│   │   ├── core/                   # Configuration (Pydantic Settings)
│   │   ├── db/
│   │   │   ├── models.py           # SQLAlchemy models (44K+ lines)
│   │   │   ├── session.py          # DB session with QueuePool
│   │   │   └── base.py             # Declarative base
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   └── services/
│   │       ├── generator.py        # ⭐ Core scheduling engine (4100+ lines)
│   │       ├── substitution.py     # Substitution scoring service
│   │       ├── feasibility_analyzer.py
│   │       ├── pdf_service.py      # PDF timetable generation
│   │       ├── reporting.py        # Analytics & report generation
│   │       └── *_import_service.py # Excel import processors (×5)
│   ├── main.py                     # FastAPI app entry point
│   ├── seed_data.py                # Database seeder with demo data
│   ├── update_db_schema.py         # Safe schema migration utility
│   └── requirements.txt
│
├── frontend/                       # React 19 + Vite 7 Frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── Sidebar.jsx         # Navigation sidebar
│   │   │   ├── TimetableGrid.jsx   # Interactive timetable grid
│   │   │   ├── LockSlotModal.jsx   # Fixed slot configuration
│   │   │   ├── PDFPreviewModal.jsx # PDF preview & download
│   │   │   ├── ImportanceBar.jsx   # Visual priority indicator
│   │   │   └── ErrorBoundary.jsx   # Error boundary wrapper
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx            # Home dashboard
│   │   │   ├── DepartmentsPage.jsx      # Department management
│   │   │   ├── TeachersPage.jsx         # Teacher CRUD + mapping
│   │   │   ├── SubjectsPage.jsx         # Subject CRUD + config
│   │   │   ├── SemestersPage.jsx        # Class/semester CRUD
│   │   │   ├── RoomsPage.jsx            # Room management
│   │   │   ├── GeneratePage.jsx         # Timetable generation UI
│   │   │   ├── TimetablePage.jsx        # Timetable viewer
│   │   │   ├── ManageTimetablePage.jsx  # Edit/manage allocations
│   │   │   ├── SubstitutionPage.jsx     # Substitution workflow
│   │   │   ├── ElectivesPage.jsx        # Elective basket setup
│   │   │   ├── StructuredBasketsPage.jsx# SCB configuration
│   │   │   ├── ParallelLabsPage.jsx     # Parallel lab setup
│   │   │   ├── RoomAvailabilityPage.jsx # Room occupancy grid
│   │   │   ├── FacultyWorkloadPage.jsx  # Teacher load dashboard
│   │   │   ├── FacultyAssignmentPage.jsx# Assignment view
│   │   │   ├── ReportsPage.jsx          # Reports & analytics
│   │   │   ├── FeasibilityPage.jsx      # Pre-gen feasibility
│   │   │   ├── MasterLabTimetablePage.jsx # Lab master view
│   │   │   └── TeacherLoadDashboard.jsx # Load visualization
│   │   ├── services/               # Axios API service layer
│   │   └── context/                # React context providers
│   ├── package.json
│   └── vite.config.js
│
├── database/
│   └── schema.sql                  # PostgreSQL / SQLite schema
├── run_project.py                  # One-command project runner
├── seed_demo_data.py               # Demo data seeder
├── render.yaml                     # Render deployment blueprint
└── LICENSE                         # MIT License
```

---

## 🔧 Manual Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- (Optional) PostgreSQL 14+ — SQLite works out of the box

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Start the server (auto-seeds database on first run)
uvicorn main:app --reload
```

**Backend available at:** `http://localhost:8000`
**Interactive API docs:** `http://localhost:8000/docs`

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

**Frontend available at:** `http://localhost:5173`

---

## 📖 Usage Guide

### 1. Initial Data Setup
1. Create **Departments** (e.g., CSE, AI&ML, ECE)
2. Add **Rooms** — specify type (lecture / lab / seminar) and capacity
3. Add **Subjects** — set weekly hours, type (theory / lab), and department
4. Add **Teachers** — map them to subjects they can teach per class
5. Add **Classes/Semesters** — assign student count and department

### 2. Configure Scheduling Rules
1. **Elective Baskets** — Group elective subjects that should run in parallel across classes
2. **Structured Composite Baskets** — Combine theory + lab components as atomic scheduling units
3. **Parallel Lab Batches** — Split large classes into lab batches with different teachers
4. **Fixed Slots** — Lock specific teacher-subject-class-room combinations to a day/slot

### 3. Generate Timetable
1. Go to **Generate** page
2. Select target classes or departments (or generate for all)
3. Choose semester type (ODD / EVEN)
4. Click **Generate Timetable**
5. View results on the **Timetable** page (class view or teacher view)

### 4. Manage Substitutions
1. Go to **Substitution** page
2. Select a teacher and mark them absent for a date
3. The system auto-ranks substitute candidates using the scoring algorithm
4. Assign the best-fit substitute

### 5. Bulk Import (Excel)
Upload `.xlsx` files for subjects, teachers, classes, rooms, or departments through the respective management pages. The system validates data, detects conflicts, and provides detailed import reports.

---

## 🌐 API Endpoints

All endpoints are prefixed with `/api`. Interactive docs available at `/docs`.

| Module | Prefix | Description |
|--------|--------|-------------|
| Dashboard | `/api/dashboard` | Stats, counts, recent activity |
| Departments | `/api/departments` | Department CRUD |
| Rooms | `/api/rooms` | Room CRUD + availability |
| Subjects | `/api/subjects` | Subject CRUD + teacher mapping |
| Teachers | `/api/teachers` | Teacher CRUD + assignments |
| Semesters | `/api/semesters` | Class/semester CRUD |
| Timetable | `/api/timetable` | Generate, view, manage grid |
| Substitution | `/api/substitution` | Absence marking + substitute assignment |
| Elective Baskets | `/api/elective-baskets` | Elective group configuration |
| SCB | `/api/structured-composite-baskets` | Composite basket setup |
| Parallel Labs | `/api/parallel-lab-baskets` | Lab batch configuration |
| Fixed Slots | `/api/fixed-slots` | Locked slot management |
| Room Availability | `/api/room-availability` | Real-time room grid |
| Allocation | `/api/allocations` | Manual allocation CRUD |
| Reports | `/api/reports` | PDF + analytics reports |
| Feasibility | `/api/feasibility` | Pre-generation validation |
| Rule Toggles | `/api/rule-toggles` | Scheduling rule flags |
| Import (×5) | `/api/import/*` | Excel bulk import endpoints |

---

## 🛠️ Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Backend** | FastAPI | ≥ 0.109 |
| **ORM** | SQLAlchemy | ≥ 2.0 |
| **Database** | SQLite (dev) / PostgreSQL (prod) | — |
| **Validation** | Pydantic | ≥ 2.5 |
| **PDF** | ReportLab | ≥ 4.1 |
| **Excel** | openpyxl | ≥ 3.1 |
| **Frontend** | React | 19.2 |
| **Bundler** | Vite | 7.2 |
| **Routing** | React Router | 7.13 |
| **HTTP Client** | Axios | 1.13 |
| **Icons** | Lucide React | 0.563 |

---

## ☁️ Deployment

### Render (Recommended)
The project includes a `render.yaml` blueprint that automatically provisions:
1. **Backend API** — Python/FastAPI web service
2. **PostgreSQL Database** — Persistent storage
3. **Frontend Static Site** — React/Vite with SPA rewrites

**Steps:**
1. Connect your GitHub repo to [Render](https://render.com)
2. Create a new **Blueprint Instance**
3. Render auto-detects `render.yaml` and provisions all services
4. The database is automatically linked via `DATABASE_URL`

### Vercel
1. **Frontend** — Deploy the `frontend/` directory. Set `VITE_API_URL` to your backend URL.
2. **Backend** — Deploy the `backend/` directory. Vercel uses the provided `vercel.json` and `api/index.py`.

### Docker
A `Dockerfile` is included in the `backend/` directory for containerized deployment.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Backend port (set by hosting platforms) | `8000` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./timetable.db` |
| `VITE_API_URL` | Frontend → Backend API base URL | Auto-detected |
| `GENERATOR_TRACE` | Enable verbose generation logs (`1` / `true`) | `0` |

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

## 🤝 Contributing

Contributions are welcome! Feel free to:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

**⭐ Star this repo if you find it helpful!**

Built with ❤️ using FastAPI + React | [GitHub](https://github.com/nav-in27/timetable-generator)
