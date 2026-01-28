/**
 * Timetable View Page
 * View timetables by class or teacher
 */
import { useEffect, useState } from 'react';
import { Calendar, User, GraduationCap, AlertCircle } from 'lucide-react';
import { timetableApi, semestersApi, teachersApi } from '../services/api';
import TimetableGrid from '../components/TimetableGrid';
import './TimetablePage.css';

export default function TimetablePage() {
    const [viewType, setViewType] = useState('semester'); // 'semester' or 'teacher'
    const [semesters, setSemesters] = useState([]);
    const [teachers, setTeachers] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [timetable, setTimetable] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [viewDate, setViewDate] = useState(new Date().toISOString().split('T')[0]);

    useEffect(() => {
        fetchOptions();
    }, []);

    useEffect(() => {
        if (selectedId) {
            fetchTimetable();
        }
    }, [selectedId, viewType, viewDate]);

    const fetchOptions = async () => {
        try {
            const [semRes, teachRes] = await Promise.all([
                semestersApi.getAll(),
                teachersApi.getAll(),
            ]);
            setSemesters(semRes.data);
            setTeachers(teachRes.data);

            // Auto-select first option
            if (semRes.data.length > 0) {
                setSelectedId(semRes.data[0].id);
            }
        } catch (err) {
            setError('Failed to load options');
            console.error(err);
        }
    };

    const fetchTimetable = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = viewType === 'semester'
                ? await timetableApi.getBySemester(selectedId, viewDate)
                : await timetableApi.getByTeacher(selectedId, viewDate);
            setTimetable(res.data);
        } catch (err) {
            if (err.response?.status === 404) {
                setTimetable(null);
            } else {
                setError('Failed to load timetable');
            }
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleViewTypeChange = (type) => {
        setViewType(type);
        setSelectedId(null);
        setTimetable(null);

        // Auto-select first option for new type
        if (type === 'semester' && semesters.length > 0) {
            setSelectedId(semesters[0].id);
        } else if (type === 'teacher' && teachers.length > 0) {
            setSelectedId(teachers[0].id);
        }
    };

    return (
        <div className="timetable-page">
            <div className="page-header">
                <div>
                    <h1>Timetable View</h1>
                    <p>View schedules by class or teacher</p>
                </div>
            </div>

            {/* Controls */}
            <div className="timetable-controls card">
                <div className="control-group">
                    <label className="form-label">View By</label>
                    <div className="type-selector">
                        <button
                            className={`type-btn ${viewType === 'semester' ? 'active' : ''}`}
                            onClick={() => handleViewTypeChange('semester')}
                        >
                            <GraduationCap size={16} />
                            Class
                        </button>
                        <button
                            className={`type-btn ${viewType === 'teacher' ? 'active' : ''}`}
                            onClick={() => handleViewTypeChange('teacher')}
                        >
                            <User size={16} />
                            Teacher
                        </button>
                    </div>
                </div>

                <div className="control-group">
                    <label className="form-label">
                        {viewType === 'semester' ? 'Select Class' : 'Select Teacher'}
                    </label>
                    <select
                        className="form-select"
                        value={selectedId || ''}
                        onChange={(e) => setSelectedId(parseInt(e.target.value))}
                    >
                        <option value="">-- Select --</option>
                        {viewType === 'semester'
                            ? semesters.map((s) => (
                                <option key={s.id} value={s.id}>
                                    {s.name} ({s.code})
                                </option>
                            ))
                            : teachers.map((t) => (
                                <option key={t.id} value={t.id}>
                                    {t.name}
                                </option>
                            ))}
                    </select>
                </div>

                <div className="control-group">
                    <label className="form-label">View Date (for substitutions)</label>
                    <input
                        type="date"
                        className="form-input"
                        value={viewDate}
                        onChange={(e) => setViewDate(e.target.value)}
                    />
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            {/* Loading */}
            {loading && (
                <div className="loading">
                    <div className="spinner"></div>
                </div>
            )}

            {/* Timetable Grid */}
            {!loading && timetable && (
                <TimetableGrid timetable={timetable} viewType={viewType} />
            )}

            {/* Empty State */}
            {!loading && !timetable && selectedId && (
                <div className="card empty-state">
                    <Calendar size={48} />
                    <h3>No Timetable Found</h3>
                    <p>Generate a timetable first to see it here.</p>
                </div>
            )}

            {!selectedId && (
                <div className="card empty-state">
                    <Calendar size={48} />
                    <h3>Select a {viewType === 'semester' ? 'Class' : 'Teacher'}</h3>
                    <p>Choose from the dropdown above to view the timetable.</p>
                </div>
            )}
        </div>
    );
}
