/**
 * Generate Timetable Page
 * Trigger timetable generation with options
 */
import { useEffect, useState } from 'react';
import {
    RefreshCw,
    Play,
    CheckCircle,
    XCircle,
    Clock,
    AlertCircle,
    Trash2,
    Zap,
} from 'lucide-react';
import { timetableApi, semestersApi } from '../services/api';
import { Link } from 'react-router-dom';
import './GeneratePage.css';

export default function GeneratePage() {
    const [semesters, setSemesters] = useState([]);
    const [selectedSemesters, setSelectedSemesters] = useState([]);
    const [clearExisting, setClearExisting] = useState(true);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchSemesters();
    }, []);

    const fetchSemesters = async () => {
        try {
            const res = await semestersApi.getAll();
            setSemesters(res.data);
        } catch (err) {
            setError('Failed to load classes');
            console.error(err);
        }
    };

    const toggleSemester = (id) => {
        setSelectedSemesters((prev) =>
            prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
        );
    };

    const selectAll = () => {
        setSelectedSemesters(semesters.map((s) => s.id));
    };

    const clearSelection = () => {
        setSelectedSemesters([]);
    };

    const handleGenerate = async () => {
        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const res = await timetableApi.generate({
                semester_ids: selectedSemesters.length > 0 ? selectedSemesters : null,
                clear_existing: clearExisting,
            });
            setResult(res.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Generation failed');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleClearAll = async () => {
        if (!confirm('Are you sure you want to clear all timetable allocations?')) return;

        try {
            await timetableApi.clear();
            setResult(null);
            setError(null);
            alert('All allocations cleared successfully');
        } catch (err) {
            setError('Failed to clear allocations');
            console.error(err);
        }
    };

    return (
        <div className="generate-page">
            <div className="page-header">
                <div>
                    <h1>Generate Timetable</h1>
                    <p>Automatically create optimized timetables</p>
                </div>
            </div>

            <div className="generate-grid">
                {/* Options Card */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Generation Options</h3>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Select Classes (or leave empty for all)</label>
                        <div className="semester-selector">
                            {semesters.map((sem) => (
                                <button
                                    key={sem.id}
                                    className={`semester-chip ${selectedSemesters.includes(sem.id) ? 'selected' : ''}`}
                                    onClick={() => toggleSemester(sem.id)}
                                >
                                    {sem.code}
                                </button>
                            ))}
                        </div>
                        <div className="selector-actions">
                            <button type="button" className="btn btn-sm btn-secondary" onClick={selectAll}>
                                Select All
                            </button>
                            <button type="button" className="btn btn-sm btn-secondary" onClick={clearSelection}>
                                Clear
                            </button>
                        </div>
                    </div>

                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <input
                                type="checkbox"
                                checked={clearExisting}
                                onChange={(e) => setClearExisting(e.target.checked)}
                            />
                            Clear existing allocations before generating
                        </label>
                    </div>

                    <div className="generate-actions">
                        <button
                            className="btn btn-primary btn-lg"
                            onClick={handleGenerate}
                            disabled={loading}
                        >
                            {loading ? (
                                <>
                                    <RefreshCw size={20} className="spinning" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <Play size={20} />
                                    Generate Timetable
                                </>
                            )}
                        </button>
                        <button
                            className="btn btn-danger"
                            onClick={handleClearAll}
                            disabled={loading}
                        >
                            <Trash2 size={18} />
                            Clear All
                        </button>
                    </div>
                </div>

                {/* Algorithm Info Card */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Algorithm Details</h3>
                    </div>
                    <div className="algorithm-info">
                        <div className="algo-step">
                            <div className="algo-step-icon">
                                <Zap size={18} />
                            </div>
                            <div>
                                <h4>Phase 1: Greedy Assignment</h4>
                                <p>
                                    Uses constraint-based scheduling to find a feasible solution that
                                    satisfies all hard constraints (no conflicts, qualified teachers, etc.)
                                </p>
                            </div>
                        </div>
                        <div className="algo-step">
                            <div className="algo-step-icon">
                                <RefreshCw size={18} />
                            </div>
                            <div>
                                <h4>Phase 2: Genetic Optimization</h4>
                                <p>
                                    Improves the solution using evolutionary algorithms to optimize
                                    soft constraints (balanced workload, minimal gaps, etc.)
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Result */}
            {result && (
                <div className={`result-card card ${result.success ? 'success' : 'error'}`}>
                    <div className="result-icon">
                        {result.success ? <CheckCircle size={32} /> : <XCircle size={32} />}
                    </div>
                    <div className="result-content">
                        <h3>{result.success ? 'Generation Successful!' : 'Generation Failed'}</h3>
                        <p>{result.message}</p>
                        <div className="result-stats">
                            <div className="result-stat">
                                <span className="stat-value">{result.total_allocations}</span>
                                <span className="stat-label">Allocations</span>
                            </div>
                            <div className="result-stat">
                                <Clock size={16} />
                                <span className="stat-value">{result.generation_time_seconds}s</span>
                                <span className="stat-label">Time</span>
                            </div>
                        </div>
                        {result.success && (
                            <Link to="/timetable" className="btn btn-primary" style={{ marginTop: '1rem' }}>
                                View Timetable
                            </Link>
                        )}
                    </div>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}
        </div>
    );
}
