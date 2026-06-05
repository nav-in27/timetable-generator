/**
 * College Timetable Generator - Main App Component
 * Sets up routing and layout
 */
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import Sidebar from './components/Sidebar';
import { DepartmentProvider } from './context/DepartmentContext';
import Dashboard from './pages/Dashboard';
import DepartmentsPage from './pages/DepartmentsPage';
import TeachersPage from './pages/TeachersPage';
import SubjectsPage from './pages/SubjectsPage';
import SemestersPage from './pages/SemestersPage';
import RoomsPage from './pages/RoomsPage';
import TimetablePage from './pages/TimetablePage';
import ManageTimetablePage from './pages/ManageTimetablePage';
import ElectivesPage from './pages/ElectivesPage';
import StructuredBasketsPage from './pages/StructuredBasketsPage';
import ParallelLabsPage from './pages/ParallelLabsPage';
import GeneratePage from './pages/GeneratePage';
import SubstitutionPage from './pages/SubstitutionPage';
import ReportsPage from './pages/ReportsPage';
import MasterLabTimetablePage from './pages/MasterLabTimetablePage';
import TeacherLoadDashboard from './pages/TeacherLoadDashboard';
import RoomAvailabilityPage from './pages/RoomAvailabilityPage';

import FacultyAssignmentPage from './pages/FacultyAssignmentPage';
import FacultyWorkloadPage from './pages/FacultyWorkloadPage';
import FeasibilityPage from './pages/FeasibilityPage';
import IntegrityPage from './pages/IntegrityPage';

function App() {
  return (
    <ErrorBoundary>
      <DepartmentProvider>
        <Router>
          <div className="app-layout">
            <Sidebar />
            <main className="main-content">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/departments" element={<DepartmentsPage />} />
                <Route path="/teachers" element={<TeachersPage />} />
                <Route path="/subjects" element={<SubjectsPage />} />
                <Route path="/electives" element={<ElectivesPage />} />
                <Route path="/structured-baskets" element={<StructuredBasketsPage />} />
                <Route path="/parallel-labs" element={<ParallelLabsPage />} />
                <Route path="/semesters" element={<SemestersPage />} />
                <Route path="/rooms" element={<RoomsPage />} />
                <Route path="/timetable" element={<TimetablePage />} />
                <Route path="/manage-timetable" element={<ManageTimetablePage />} />
                <Route path="/generate" element={<GeneratePage />} />
                <Route path="/substitution" element={<SubstitutionPage />} />
                <Route path="/teacher-load" element={<TeacherLoadDashboard />} />
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/master-lab" element={<MasterLabTimetablePage />} />
                <Route path="/room-availability" element={<RoomAvailabilityPage />} />

                <Route path="/faculty-assignments" element={<FacultyAssignmentPage />} />
                <Route path="/faculty-workload" element={<FacultyWorkloadPage />} />
                <Route path="/feasibility" element={<FeasibilityPage />} />
                <Route path="/integrity" element={<IntegrityPage />} />
              </Routes>
            </main>
          </div>
        </Router>
      </DepartmentProvider>
    </ErrorBoundary>
  );
}

export default App;
