# 🎓 AI Dept Timetable Generator

A modern, full-stack web application for **automated college timetable generation** with **intelligent teacher substitution**. Built with **FastAPI** (Python) and **React** (Vite), featuring a robust constraint-based scheduling engine.

---

## ✨ Features

### Core Functionality
- **📋 Resource Management** — Full CRUD for Departments, Teachers, Subjects, Classes (Semesters/Sections), Rooms, and Batches.
- **🔄 Automatic Timetable Generation** — Multi-phase engine (Greedy + Genetic Optimization) respecting complex hard and soft constraints.
- **📚 Advanced Elective Baskets** — Group elective subjects to be auto-scheduled to common slots across multiple participating classes.
- **🧪 Parallel Lab Baskets** — Schedule multiple lab sessions simultaneously (e.g., DBMS Lab + OS Lab) across different rooms and batches.
- **🧩 Structured Composite Baskets (SCB)** — Bundle Theory + Lab + Tutorial components for coordinated scheduling.
- **📌 Fixed Slots** — Pre-lock specific subjects/teachers to timeslots; the generator respects these as immovable anchors.
- **⚙️ Rule Toggles** — Configure per-department rules (lab continuity, teacher gap, max consecutive classes).
- **🔁 Automated Teacher Substitution** — Score-based ranking (Subject Match, Load, Effectiveness, Experience) for intelligent substitute assignment.
- **📊 Reports & Analytics** — Faculty workload reports, teacher load dashboards, room availability tracking, and PDF exports.

### Stability & Integrity
- **🛡️ Read-Only Generation Engine** — The generator never modifies source data (teachers, subjects, etc.); it only reads mappings and creates new `Allocation` records.
- **🧪 Atomic Lab Blocks** — Guarantees labs occupy exactly two continuous slots post-lunch, treated as indivisible units during optimization.
- **🧬 Deterministic Teacher Mapping** — Ensures exactly one teacher is assigned per (class, subject) pair for consistency across the week.
- **🔄 Synchronized Electives** — Guarantees that elective subjects shared across departments are scheduled at identical times.

---

## 📖 Technical Documentation

For deep dives into specific systems and architectural decisions, see:

- **[Algorithm Fixes](ALGORITHM_FIXES.md)** — Detailed breakdown of logical fixes for teacher mapping, elective sync, and lab continuity.
- **[Elective Architecture Guide](ELECTIVE_ARCHITECTURE_COMPLETE.md)** — Comprehensive guide to the elective basket scheduling system and its 7-phase flow.
- **[Strict Generation Rules](STRICT_GENERATION_RULES.md)** — Overview of the data safety rules and the read-only nature of the engine.
- **[Multi-Elective Groups](MULTI_ELECTIVE_GROUPS.md)** — Documentation on handling complex elective groupings.

---

## 📋 Usage Guide

### 1. Resource Setup
Populate **Departments**, **Rooms**, **Subjects**, and **Teachers**. Use the **Bulk Import** feature for rapid setup via Excel/CSV.

### 2. Advanced Mapping
- **Elective Baskets**: Group subjects to ensure synchronized scheduling across classes.
- **Fixed Slots**: Anchor specific sessions to permanent timeslots.
- **Rule Toggles**: Fine-tune generation logic (e.g., allow/disallow teacher gaps).

### 3. Generation & Management
Run the **Feasibility Checker** to detect conflicts, then hit **Generate**. View results in **Class** or **Teacher** view modes. Assign **Substitutions** for absent faculty using the AI ranking engine.

---

## ⚖️ Constraint Highlights

| Type | Constraint | Enforcement |
|---|---|---|
| **Hard** | Teacher Double-Booking | **Strictly Forbidden** (Validated per slot) |
| **Hard** | Room Conflicts | **Strictly Forbidden** (Validated per slot) |
| **Hard** | Lab Continuity | **Guaranteed** (Atomic 2-period blocks) |
| **Soft** | Consecutive Classes | Optimized to avoid 3+ back-to-back sessions |
| **Soft** | Workload Balance | Distributed evenly across the week |

---

## 🏗️ Architecture

```
timetable-generator/
├── backend/                      # FastAPI Backend
│   ├── app/
│   │   ├── api/                  # 20+ API route modules
│   │   │   ├── timetable.py      # Core generation logic
│   │   │   ├── elective_baskets.py
│   │   │   ├── parallel_lab_baskets.py
│   │   │   ├── fixed_slots.py
│   │   │   ├── substitution.py
│   │   │   └── ... (CRUD modules)
│   │   ├── core/                 # Config & timing definitions
│   │   ├── db/                   # Models & Session management
│   │   ├── schemas/              # Pydantic validation models
│   │   └── services/             # Business logic (Generator, PDF, Import)
│   ├── main.py                   # App entry point
│   └── requirements.txt
├── frontend/                     # React Frontend (Vite)
│   ├── src/
│   │   ├── components/           # Reusable UI (Grid, Modals, etc.)
│   │   ├── pages/                # 20+ interactive pages
│   │   └── services/             # API communication layer
│   └── package.json
├── database/                     # SQL Schema reference
├── run_project.py                # One-command project launcher
└── ... (Technical Documentation MD files)
```

---

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | FastAPI, SQLAlchemy 2.0, Pydantic v2, SQLite/PostgreSQL, ReportLab |
| **Frontend** | React 19, Vite 7, React Router 7, Axios, Lucide React |
| **DevOps** | Render Blueprint, Vercel Support, Python venv |

---

## 🚀 Getting Started

### One-Command Start (Recommended)
```bash
python run_project.py
```
This script handles dependency installation, database seeding, and starts both servers automatically.

### Manual Setup

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## 📅 College Time Structure

- **Periods**: 7 per day, Monday – Friday.
- **Labs**: 2 consecutive periods (Post-lunch: 4-5 or 6-7).
- **Substitution**: Automatic scoring based on specialization and workload.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**⭐ Star this repo if you find it helpful!**

Built with ❤️ by the AI Dept Team
