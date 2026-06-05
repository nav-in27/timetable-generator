/**
 * Generate Timetable Page
 * Trigger timetable generation with options
 * Supports async generation with polling status
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import {
    RefreshCw,
    Play,
    CheckCircle,
    XCircle,
    Clock,
    AlertCircle,
    Trash2,
    Loader,
} from 'lucide-react';
import { timetableApi, semestersApi, feasibilityApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import { Link } from 'react-router-dom';
import './GeneratePage.css';

export default function GeneratePage() {
    const { departments, selectedDeptId, setSelectedDeptId, deptId } = useDepartmentContext();
    const [semesters, setSemesters] = useState([]);
    const [selectedSemesters, setSelectedSemesters] = useState([]);
    const [clearExisting, setClearExisting] = useState(true);
    const [semesterType, setSemesterType] = useState('EVEN');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [elapsed, setElapsed] = useState(0);
    const [genStatus, setGenStatus] = useState(null); // 'queued' | 'running' | 'completed' | 'failed'
    const [feasibilityReport, setFeasibilityReport] = useState(null);
    const [analyzing, setAnalyzing] = useState(false);
    const pollRef = useRef(null);

    useEffect(() => {
        fetchSemesters();
    }, [deptId]);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, []);

    const fetchSemesters = async () => {
        try {
            const params = {};
            if (deptId) params.deptId = deptId;
            const res = await semestersApi.getAll(params);
            setSemesters(res.data);
            setSelectedSemesters([]);
        } catch (err) {
            setError('Failed to load classes');
        }
    };

    const toggleSemester = (id) => {
        setSelectedSemesters((prev) =>
            prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
        );
    };

    const selectAll = () => setSelectedSemesters(semesters.map((s) => s.id));
    const clearSelection = () => setSelectedSemesters([]);

    const pollForStatus = useCallback((taskId) => {
        pollRef.current = setInterval(async () => {
            try {
                const res = await timetableApi.getGenerationStatus(taskId);
                const data = res.data;
                setGenStatus(data.status);
                if (data.elapsed_seconds) setElapsed(data.elapsed_seconds);

                if (data.status === 'completed' || data.status === 'failed') {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                    setLoading(false);
                    if (data.result) setResult(data.result);
                    if (data.status === 'failed') {
                        setError(data.result?.message || 'Generation failed');
                    }
                }
            } catch (err) {
                // If poll fails, keep trying
            }
        }, 1500);
    }, []);

    const handleGenerate = async () => {
        setLoading(true);
        setError(null);
        setResult(null);
        setElapsed(0);
        setGenStatus('queued');

        try {
            // Use async generation to avoid blocking
            const res = await timetableApi.generateAsync({
                semester_ids: selectedSemesters.length > 0 ? selectedSemesters : null,
                dept_id: deptId ?? null,
                clear_existing: clearExisting,
                semester_type: semesterType,
            });

            const taskId = res.data.task_id;
            pollForStatus(taskId);
        } catch (err) {
            // Fallback to sync if async endpoint not available
            try {
                const res = await timetableApi.generate({
                    semester_ids: selectedSemesters.length > 0 ? selectedSemesters : null,
                    dept_id: deptId ?? null,
                    clear_existing: clearExisting,
                    semester_type: semesterType,
                });
                setResult(res.data);
                setGenStatus(res.data.success ? 'completed' : 'failed');
            } catch (syncErr) {
                setError(syncErr.response?.data?.detail || 'Generation failed');
                setGenStatus('failed');
            }
            setLoading(false);
        }
    };

    const handleAnalyzeFeasibility = async () => {
        setAnalyzing(true);
        setError(null);
        setFeasibilityReport(null);
        
        try {
            const params = {};
            if (deptId) params.department_id = deptId;
            if (selectedSemesters.length > 0) params.semester_ids = selectedSemesters.join(',');
            
            const res = await feasibilityApi.analyze(params);
            setFeasibilityReport(res.data);
        } catch (err) {
            setError('Failed to analyze feasibility');
        } finally {
            setAnalyzing(false);
        }
    };

    const handleClearAll = async () => {
        const scopeLabel = deptId ? `this department's` : 'ALL';
        if (!confirm(`Are you sure you want to clear ${scopeLabel} timetable allocations?`)) return;

        try {
            await timetableApi.clear(null, deptId);
            setResult(null);
            setError(null);
            alert('Allocations cleared successfully');
        } catch (err) {
            setError('Failed to clear allocations');
        }
    };

    const statusLabel = genStatus === 'queued' ? 'Queuing...'
        : genStatus === 'running' ? `Generating... (${elapsed}s)`
            : loading ? 'Starting...' : null;

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
                        <label className="form-label">Department (Optional)</label>
                        <select
                            className="form-input"
                            value={selectedDeptId || ''}
                            onChange={(e) => setSelectedDeptId(e.target.value)}
                        >
                            <option value="">All Departments</option>
                            {departments.map(d => (
                                <option key={d.id} value={d.id}>{d.name} ({d.code})</option>
                            ))}
                        </select>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Semester Type</label>
                        <select
                            className="form-input"
                            value={semesterType}
                            onChange={(e) => setSemesterType(e.target.value)}
                        >
                            <option value="ODD">Odd Semester</option>
                            <option value="EVEN">Even Semester</option>
                        </select>
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
                                    <Loader size={20} className="spinning" />
                                    {statusLabel || 'Starting...'}
                                </>
                            ) : (
                                <>
                                    <Play size={20} />
                                    Generate Timetable
                                </>
                            )}
                        </button>
                        <button
                            className="btn btn-secondary btn-lg"
                            onClick={handleAnalyzeFeasibility}
                            disabled={loading || analyzing}
                        >
                            {analyzing ? (
                                <>
                                    <Loader size={20} className="spinning" />
                                    Analyzing...
                                </>
                            ) : (
                                <>
                                    <AlertCircle size={20} />
                                    Analyze Feasibility
                                </>
                            )}
                        </button>
                        <button
                            className="btn btn-danger"
                            onClick={handleClearAll}
                            disabled={loading}
                        >
                            <Trash2 size={18} />
                            {deptId ? 'Clear Dept' : 'Clear All'}
                        </button>
                    </div>

                    {/* Progress indicator during generation */}
                    {loading && (
                        <div className="generation-progress" style={{
                            marginTop: '1rem',
                            padding: '1rem',
                            background: 'var(--bg-secondary, #f8f9fa)',
                            borderRadius: '8px',
                            textAlign: 'center'
                        }}>
                            <Loader size={24} className="spinning" style={{ marginBottom: '0.5rem' }} />
                            <p style={{ margin: 0, color: 'var(--text-secondary, #666)', fontSize: '0.9rem' }}>
                                {genStatus === 'running'
                                    ? `Engine is generating... ${elapsed}s elapsed`
                                    : 'Preparing generation engine...'}
                            </p>
                            <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted, #999)', fontSize: '0.8rem' }}>
                                This page will update automatically when complete
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {/* Result */}
            {result && (
                <div className={`result-card card ${result.success ? 'success' : 'error'}`}>
                    <div className="result-icon">
                        {result.success ? <CheckCircle size={32} /> : <XCircle size={32} />}
                    </div>
                    <div className="result-content" style={{ width: '100%' }}>
                        <h3>{result.success ? 'Generation Successful!' : 'Generation Failed'}</h3>
                        <p style={{ whiteSpace: 'pre-wrap', textAlign: 'left', background: 'rgba(0,0,0,0.03)', padding: '1rem', borderRadius: '4px', margin: '1rem 0' }}>{result.message}</p>
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
            {error && !loading && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}
        </div>
    );
}
