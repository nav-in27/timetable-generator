/**
 * College Timetable Generator - Main App Component
 * Sets up routing and layout
 */
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import TeachersPage from './pages/TeachersPage';
import SubjectsPage from './pages/SubjectsPage';
import SemestersPage from './pages/SemestersPage';
import RoomsPage from './pages/RoomsPage';
import TimetablePage from './pages/TimetablePage';
import GeneratePage from './pages/GeneratePage';
import SubstitutionPage from './pages/SubstitutionPage';

function App() {
  return (
    <Router>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/teachers" element={<TeachersPage />} />
            <Route path="/subjects" element={<SubjectsPage />} />
            <Route path="/semesters" element={<SemestersPage />} />
            <Route path="/rooms" element={<RoomsPage />} />
            <Route path="/timetable" element={<TimetablePage />} />
            <Route path="/generate" element={<GeneratePage />} />
            <Route path="/substitution" element={<SubstitutionPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
