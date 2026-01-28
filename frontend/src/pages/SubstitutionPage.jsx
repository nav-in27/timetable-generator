/**
 * Substitution Management Page
 * Handle teacher absences and automated substitution
 */
import { useEffect, useState } from 'react';
import {
    UserX,
    UserCheck,
    Calendar,
    Clock,
    Star,
    AlertCircle,
    CheckCircle,
    Zap,
    X,
    ArrowRight,
    Briefcase,
} from 'lucide-react';
import { substitutionApi, teachersApi } from '../services/api';
import './SubstitutionPage.css';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

export default function SubstitutionPage() {
    const [teachers, setTeachers] = useState([]);
    const [activeSubstitutions, setActiveSubstitutions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Mark Absent Form
    const [selectedTeacher, setSelectedTeacher] = useState(null);
    const [absenceDate, setAbsenceDate] = useState(new Date().toISOString().split('T')[0]);
    const [absenceReason, setAbsenceReason] = useState('');

    // Affected allocations and candidates
    const [affectedAllocations, setAffectedAllocations] = useState([]);
    const [candidates, setCandidates] = useState({});
    const [substitutionResult, setSubstitutionResult] = useState(null);
    const [processingAuto, setProcessingAuto] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [teachersRes, subsRes] = await Promise.all([
                teachersApi.getAll(),
                substitutionApi.getActive(),
            ]);
            setTeachers(teachersRes.data);
            setActiveSubstitutions(subsRes.data);
        } catch (err) {
            setError('Failed to load data');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleTeacherSelect = async (teacherId) => {
        setSelectedTeacher(teacherId);
        setAffectedAllocations([]);
        setCandidates({});
        setSubstitutionResult(null);

        if (!teacherId) return;

        try {
            const res = await substitutionApi.getAffectedAllocations(teacherId, absenceDate);
            setAffectedAllocations(res.data);

            // Fetch candidates for each allocation
            const candidatesMap = {};
            for (const alloc of res.data) {
                const candRes = await substitutionApi.getCandidates(alloc.allocation_id, absenceDate);
                candidatesMap[alloc.allocation_id] = candRes.data;
            }
            setCandidates(candidatesMap);
        } catch (err) {
            console.error('Error fetching affected allocations:', err);
        }
    };

    const handleDateChange = (date) => {
        setAbsenceDate(date);
        if (selectedTeacher) {
            handleTeacherSelect(selectedTeacher);
        }
    };

    const handleAutoSubstitute = async () => {
        if (!selectedTeacher) return;

        setProcessingAuto(true);
        setError(null);

        try {
            const res = await substitutionApi.autoSubstitute(
                selectedTeacher,
                absenceDate,
                absenceReason || null
            );
            setSubstitutionResult(res.data);
            fetchData(); // Refresh active substitutions
        } catch (err) {
            setError(err.response?.data?.detail || 'Auto-substitution failed');
            console.error(err);
        } finally {
            setProcessingAuto(false);
        }
    };

    const handleManualAssign = async (allocationId, substituteTeacherId) => {
        try {
            await substitutionApi.assign(
                {
                    allocation_id: allocationId,
                    substitution_date: absenceDate,
                    reason: absenceReason || null,
                },
                substituteTeacherId
            );
            fetchData();
            handleTeacherSelect(selectedTeacher); // Refresh affected allocations
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to assign substitute');
            console.error(err);
        }
    };

    const handleCancelSubstitution = async (subId) => {
        if (!confirm('Cancel this substitution?')) return;
        try {
            await substitutionApi.cancel(subId);
            fetchData();
        } catch (err) {
            setError('Failed to cancel substitution');
            console.error(err);
        }
    };

    const getSelectedTeacherName = () => {
        const teacher = teachers.find((t) => t.id === parseInt(selectedTeacher));
        return teacher ? teacher.name : '';
    };

    if (loading) {
        return <div className="loading"><div className="spinner"></div></div>;
    }

    return (
        <div className="substitution-page">
            <div className="page-header">
                <div>
                    <h1>Teacher Substitution</h1>
                    <p>Manage absences and assign substitutes automatically</p>
                </div>
            </div>

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                    <button onClick={() => setError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}>
                        <X size={16} />
                    </button>
                </div>
            )}

            <div className="substitution-grid">
                {/* Mark Absent Card */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">
                            <UserX size={20} />
                            Mark Teacher Absent
                        </h3>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Select Teacher</label>
                        <select
                            className="form-select"
                            value={selectedTeacher || ''}
                            onChange={(e) => handleTeacherSelect(e.target.value ? parseInt(e.target.value) : null)}
                        >
                            <option value="">-- Select Teacher --</option>
                            {teachers.map((t) => (
                                <option key={t.id} value={t.id}>
                                    {t.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Absence Date</label>
                        <input
                            type="date"
                            className="form-input"
                            value={absenceDate}
                            onChange={(e) => handleDateChange(e.target.value)}
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Reason (Optional)</label>
                        <input
                            type="text"
                            className="form-input"
                            value={absenceReason}
                            onChange={(e) => setAbsenceReason(e.target.value)}
                            placeholder="e.g., Medical leave"
                        />
                    </div>

                    {affectedAllocations.length > 0 && (
                        <button
                            className="btn btn-success btn-lg"
                            style={{ width: '100%', marginTop: '1rem' }}
                            onClick={handleAutoSubstitute}
                            disabled={processingAuto}
                        >
                            {processingAuto ? (
                                <>
                                    <Zap size={18} className="spinning" />
                                    Processing...
                                </>
                            ) : (
                                <>
                                    <Zap size={18} />
                                    Auto-Assign Substitutes
                                </>
                            )}
                        </button>
                    )}
                </div>

                {/* Active Substitutions Card */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">
                            <UserCheck size={20} />
                            Active Substitutions
                        </h3>
                        <span className="badge badge-info">{activeSubstitutions.length}</span>
                    </div>

                    {activeSubstitutions.length === 0 ? (
                        <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                            <UserCheck size={32} />
                            <p>No active substitutions</p>
                        </div>
                    ) : (
                        <div className="substitution-list">
                            {activeSubstitutions.map((sub) => (
                                <div key={sub.id} className="substitution-item">
                                    <div className="sub-info">
                                        <div className="sub-names">
                                            <span className="original">{sub.original_teacher_name}</span>
                                            <ArrowRight size={14} />
                                            <span className="substitute">{sub.substitute_teacher_name}</span>
                                        </div>
                                        <div className="sub-details">
                                            <span><Calendar size={12} /> {sub.substitution_date}</span>
                                            <span><Briefcase size={12} /> {sub.subject_name}</span>
                                        </div>
                                    </div>
                                    <div className="sub-actions">
                                        <span className={`badge badge-${sub.status === 'assigned' ? 'success' : 'warning'}`}>
                                            {sub.status}
                                        </span>
                                        <button
                                            className="btn btn-sm btn-secondary"
                                            onClick={() => handleCancelSubstitution(sub.id)}
                                        >
                                            <X size={14} />
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Affected Allocations */}
            {selectedTeacher && affectedAllocations.length > 0 && (
                <div className="card" style={{ marginTop: '1.5rem' }}>
                    <div className="card-header">
                        <h3 className="card-title">
                            Affected Classes for {getSelectedTeacherName()} on {absenceDate}
                        </h3>
                        <span className="badge badge-warning">{affectedAllocations.length} classes</span>
                    </div>

                    <div className="affected-grid">
                        {affectedAllocations.map((alloc) => (
                            <div key={alloc.allocation_id} className="affected-item">
                                <div className="affected-header">
                                    <div>
                                        <h4>{alloc.subject_name}</h4>
                                        <p className="text-sm text-muted">
                                            {DAY_NAMES[alloc.day]} • Period {alloc.slot + 1}
                                        </p>
                                    </div>
                                </div>

                                <div className="candidates-section">
                                    <h5>Available Substitutes (Ranked by Score)</h5>
                                    {candidates[alloc.allocation_id]?.length > 0 ? (
                                        <div className="candidates-list">
                                            {candidates[alloc.allocation_id].slice(0, 5).map((candidate, idx) => (
                                                <div
                                                    key={candidate.teacher_id}
                                                    className={`candidate-item ${idx === 0 ? 'top' : ''}`}
                                                >
                                                    <div className="candidate-info">
                                                        <span className="candidate-rank">#{idx + 1}</span>
                                                        <div>
                                                            <span className="candidate-name">{candidate.teacher_name}</span>
                                                            <div className="candidate-tags">
                                                                {candidate.subject_match && (
                                                                    <span className="tag tag-success">Qualified</span>
                                                                )}
                                                                <span className="tag">Load: {candidate.current_load}h</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div className="candidate-score">
                                                        <Star size={14} />
                                                        <span>{(candidate.score * 100).toFixed(0)}%</span>
                                                    </div>
                                                    <button
                                                        className="btn btn-sm btn-primary"
                                                        onClick={() => handleManualAssign(alloc.allocation_id, candidate.teacher_id)}
                                                    >
                                                        Assign
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <p className="text-muted text-sm">No available substitutes</p>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* No Affected Allocations */}
            {selectedTeacher && affectedAllocations.length === 0 && (
                <div className="card empty-state" style={{ marginTop: '1.5rem' }}>
                    <CheckCircle size={48} />
                    <h3>No Classes Affected</h3>
                    <p>This teacher has no classes scheduled on {absenceDate} ({DAY_NAMES[new Date(absenceDate).getDay() - 1] || 'Weekend'})</p>
                </div>
            )}

            {/* Auto-Substitution Result */}
            {substitutionResult && (
                <div className="card result-card success" style={{ marginTop: '1.5rem' }}>
                    <div className="result-icon">
                        <CheckCircle size={32} />
                    </div>
                    <div className="result-content">
                        <h3>Auto-Substitution Complete!</h3>
                        <p>
                            Processed absence for {substitutionResult.teacher_name} on {substitutionResult.absence_date}
                        </p>
                        <div className="result-subs">
                            {substitutionResult.substitutions.map((sub, idx) => (
                                <div key={idx} className="result-sub-item">
                                    {sub.substitution_id ? (
                                        <>
                                            <CheckCircle size={14} className="text-success" />
                                            <span>{sub.subject_name}: {sub.substitute_teacher_name} (Score: {(sub.score * 100).toFixed(0)}%)</span>
                                        </>
                                    ) : (
                                        <>
                                            <AlertCircle size={14} className="text-error" />
                                            <span>{sub.message}</span>
                                        </>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
