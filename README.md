# 🎓 AI Dept Timetable Generator

A modern, full-stack web application for **automated AI department timetable generation** with **intelligent teacher substitution**. Built with FastAPI (Python) and React.

![Dashboard Preview](docs/dashboard.png)

## ✨ Features

### Core Functionality
- **📋 Resource Management**: CRUD operations for Teachers, Subjects, Classes (Semesters), and Rooms
- **🔄 Automatic Timetable Generation**: Two-phase algorithm (Greedy + Genetic) that respects all constraints
- **🔁 Automated Teacher Substitution**: Score-based candidate ranking for intelligent substitute assignment
- **📊 Multiple View Modes**: View timetables by class or by teacher
- **⏰ Free Periods**: 1-2 free periods per class per week (configurable)
- **📱 Responsive Design**: Works on desktop and mobile devices

### Constraint Handling

**Hard Constraints (Never Violated):**
- A teacher cannot teach two classes simultaneously
- A room cannot be double-booked
- Teacher must be qualified for the subject
- Room capacity must accommodate class size
- Lab sessions scheduled in consecutive slots

**Soft Constraints (Optimized):**
- Balanced teacher workload across days
- Avoid 3+ consecutive classes for teachers
- Prefer morning/midday slots over last-hour
- Prefer substitutes with lower current workload

### Substitution Algorithm
The substitution scoring function:
```
Score = (0.4 × SubjectMatch) + (0.3 × (1 - NormalizedLoad)) 
      + (0.2 × Effectiveness) + (0.1 × Experience)
```

## 🚀 Quick Start (One Command)

The easiest way to run the entire project:

```bash
# Clone the repository
git clone https://github.com/nav-in27/timetable-generator.git
cd timetable-generator

# Run the project (starts both backend and frontend)
python run_project.py
```

This will:
1. ✅ Create a Python virtual environment
2. ✅ Install backend dependencies
3. ✅ Install frontend dependencies  
4. ✅ Seed the database with sample data
5. ✅ Start the backend server (http://localhost:8000)
6. ✅ Start the frontend server (http://localhost:5173)

**Requirements:**
- Python 3.10+
- Node.js 18+

---

## 🏗️ Architecture

```
timetable_generator/
├── backend/                 # FastAPI Backend
│   ├── app/
│   │   ├── api/            # API endpoints
│   │   ├── core/           # Configuration
│   │   ├── db/             # Database models & session
│   │   ├── schemas/        # Pydantic schemas
│   │   └── services/       # Business logic
│   ├── main.py             # App entry point
│   ├── seed_data.py        # Sample data seeder
│   └── requirements.txt
├── frontend/               # React Frontend (Vite)
│   ├── src/
│   │   ├── components/     # Reusable components
│   │   ├── pages/          # Page components
│   │   └── services/       # API service
│   └── package.json
└── database/
    └── schema.sql          # PostgreSQL schema
```

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- (Optional) PostgreSQL 14+

### Backend Setup

1. Navigate to backend directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # or: source venv/bin/activate  # Linux/Mac
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment (optional - SQLite works by default):
   ```bash
   # Edit .env file for PostgreSQL connection if needed
   ```

5. Seed sample data:
   ```bash
   python seed_data.py
   ```

6. Run the server:
   ```bash
   uvicorn main:app --reload
   ```
   
   Backend will be available at: http://localhost:8000
   API docs at: http://localhost:8000/docs

### Frontend Setup

1. Navigate to frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start development server:
   ```bash
   npm run dev
   ```
   
   Frontend will be available at: http://localhost:5173

## 📖 Usage Guide

### 1. Initial Setup
1. Add **Rooms** (lecture halls, labs)
2. Add **Subjects** (courses with weekly hours and type)
3. Add **Teachers** (assign subjects they can teach)
4. Add **Classes/Semesters** (with student counts)

### 2. Generate Timetable
1. Go to **Generate** page
2. Select classes (or all)
3. Click "Generate Timetable"
4. View generated schedule on **Timetable** page

### 3. Manage Substitutions
1. Go to **Substitution** page
2. Select absent teacher and date
3. View affected classes and candidate substitutes
4. Either:
   - Click "Auto-Assign" for automatic best-match selection
   - Manually select from ranked candidates

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/teachers` | GET, POST | List/create teachers |
| `/api/subjects` | GET, POST | List/create subjects |
| `/api/semesters` | GET, POST | List/create classes |
| `/api/rooms` | GET, POST | List/create rooms |
| `/api/timetable/generate` | POST | Generate timetable |
| `/api/timetable/view/semester/{id}` | GET | View class timetable |
| `/api/timetable/view/teacher/{id}` | GET | View teacher timetable |
| `/api/substitution/auto-substitute/{teacher_id}/{date}` | POST | Auto-assign substitutes |
| `/api/substitution/candidates/{alloc_id}/{date}` | GET | Get substitute candidates |
| `/api/dashboard/stats` | GET | Dashboard statistics |

See full API documentation at http://localhost:8000/docs

## 🧮 Algorithm Details

### Phase 1: Greedy/CSP Generation
1. **Reserve free periods**: 1-2 random slots per class are reserved as free periods
2. Sort requirements by difficulty (labs first, fewer qualified teachers first)
3. For each requirement, find available (day, slot) combinations
4. Select teacher with lowest current load
5. Select room meeting capacity requirements
6. Validate hard constraints before committing

### Phase 2: Genetic Optimization
1. Create population from initial solution variants
2. Calculate fitness based on soft constraints
3. Selection: Keep top 50% by fitness
4. Mutation: Swap slots while maintaining hard constraints
5. Repeat for configured generations

### Substitution Workflow
1. Detect affected allocations for absent teacher
2. For each allocation, find candidates who:
   - Are not already teaching in that slot
   - Are not marked absent
   - Are available on that day
3. Score candidates using weighted formula
4. Assign highest-scored candidate (or allow manual selection)

## 🔮 Future Enhancements

- [ ] Multi-department support (dept_id already in schema)
- [ ] Multi-college support (college_id already in schema)
- [ ] User authentication & roles
- [ ] Email notifications for substitutions
- [ ] Export timetable to PDF/Excel
- [ ] Conflict visualization
- [ ] Room booking calendar view

## � Deployment

This project is configured for easy deployment to **Render** and **Vercel**.

### Render (Recommended)
The project includes a `render.yaml` blueprint. 
1. Connect your GitHub repository to [Render](https://render.com).
2. Render will automatically detect the blueprint and set up both the Backend API and the Frontend Static Site.
3. The databases will be configured as SQLite by default (ephemeral in the free tier). For persistent data, configure a PostgreSQL instance on Render and update the `DATABASE_URL` environment variable.

### Vercel
The project is optimized for Vercel serverless functions.
1. **Frontend**: Deploy the `frontend` directory as a new Vercel project. Set `VITE_API_URL` to your backend URL.
2. **Backend**: Deploy the `backend` directory as a second Vercel project. Vercel will use the provided `vercel.json` and `api/index.py`.

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Backend port (automatically set by Render/Vercel) | 8000 |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./timetable.db` |
| `VITE_API_URL` | (Frontend only) URL of the backend API | (Detected) |

---

## �📄 License

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
