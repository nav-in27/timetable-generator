/**
 * Subjects Management Page
 * UPDATED: Supports component-based subject model (Theory + Lab + Tutorial)
 */
import { useEffect, useState } from 'react';
import { Plus, Edit2, Trash2, X, BookOpen, Clock, AlertCircle, Beaker, GraduationCap, Star, Filter, TrendingUp, Upload, Download, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { subjectsApi, semestersApi, subjectImportApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import './CrudPage.css';

export default function SubjectsPage() {
    const { deptId } = useDepartmentContext();
    const [subjects, setSubjects] = useState([]);
    const [semesters, setSemesters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingSubject, setEditingSubject] = useState(null);

    // Import State
    const [showImportModal, setShowImportModal] = useState(false);
    const [importFile, setImportFile] = useState(null);
    const [importResult, setImportResult] = useState(null);
    const [importLoading, setImportLoading] = useState(false);
    const [importCommitting, setImportCommitting] = useState(false);
    const [importStep, setImportStep] = useState('upload'); // upload | preview | committed

    // Filter State
    const [filterName, setFilterName] = useState('');
    const [filterYear, setFilterYear] = useState('');
    const [filterSemester, setFilterSemester] = useState('');
    const [filterType, setFilterType] = useState('');
    const [formData, setFormData] = useState({
        name: '',
        code: '',
        // Component-based hours (NEW - Correct Academic Model)
        theory_hours_per_week: 3,
        lab_hours_per_week: 0,
        tutorial_hours_per_week: 0,
        // Extended components (Optional)
        self_study_hours_per_week: 0,
        seminar_hours_per_week: 0,
        seminar_block_size: 2,
        seminar_day_based: false,
        // Legacy fields
        weekly_hours: 3,
        subject_type: 'regular',
        consecutive_slots: 1,
        // Department context (optional/backward-compatible)
        dept_id: null,
        year: 1,
        semester: 1,
        // Assignment
        semester_ids: [],
        is_elective: false,
        // Academic Importance
        importance_level: 'NORMAL',
        previous_year_pass_percentage: null,
    });

    useEffect(() => {
        fetchData();
    }, [deptId]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [subjRes, semRes] = await Promise.all([
                subjectsApi.getAll({ deptId }),
                semestersApi.getAll({ deptId })
            ]);
            setSubjects(subjRes.data);
            setSemesters(semRes.data);
        } catch (err) {
            setError('Failed to load data');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };



    // Filter Logic
    const filteredSubjects = subjects.filter(subject => {
        if (filterName) {
            const search = filterName.toLowerCase();
            if (!subject.name.toLowerCase().includes(search) && !subject.code.toLowerCase().includes(search)) return false;
        }
        if (filterYear && subject.year !== parseInt(filterYear)) return false;
        if (filterSemester && subject.semester !== parseInt(filterSemester)) return false;
        if (filterType) {
            if (filterType === 'theory' && !subject.theory_hours_per_week) return false;
            if (filterType === 'lab' && !subject.lab_hours_per_week) return false;
            if (filterType === 'tutorial' && !subject.tutorial_hours_per_week) return false;
            if (filterType === 'elective' && !subject.is_elective) return false;
        }
        return true;
    });

    const openModal = (subject = null) => {
        if (subject) {
            setEditingSubject(subject);
            setFormData({
                name: subject.name,
                code: subject.code,
                theory_hours_per_week: subject.theory_hours_per_week ?? subject.weekly_hours ?? 3,
                lab_hours_per_week: subject.lab_hours_per_week ?? 0,
                tutorial_hours_per_week: subject.tutorial_hours_per_week ?? 0,
                self_study_hours_per_week: subject.self_study_hours_per_week ?? 0,
                seminar_hours_per_week: subject.seminar_hours_per_week ?? 0,
                seminar_block_size: subject.seminar_block_size ?? 2,
                seminar_day_based: subject.seminar_day_based ?? false,
                weekly_hours: subject.weekly_hours ?? 3,
                subject_type: subject.subject_type || 'regular',
                consecutive_slots: subject.consecutive_slots || 1,
                dept_id: subject.dept_id ?? deptId ?? null,
                year: subject.year ?? 1,
                semester: subject.semester ?? 1,
                semester_ids: subject.semesters ? subject.semesters.map(s => s.id) : [],
                is_elective: subject.is_elective || subject.subject_type === 'elective',
                importance_level: subject.importance_level || 'NORMAL',
                previous_year_pass_percentage: subject.previous_year_pass_percentage ?? null,
            });
        } else {
            setEditingSubject(null);
            setFormData({
                name: '',
                code: '',
                theory_hours_per_week: 3,
                lab_hours_per_week: 0,
                tutorial_hours_per_week: 0,
                self_study_hours_per_week: 0,
                seminar_hours_per_week: 0,
                seminar_block_size: 2,
                seminar_day_based: false,
                subject_type: 'regular',
                consecutive_slots: 1,
                dept_id: deptId ?? null,
                year: 1,
                semester: 1,
                semester_ids: [],
                is_elective: false,
                importance_level: 'NORMAL',
                previous_year_pass_percentage: null,
            });
        }
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingSubject(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        if (formData.semester_ids.length === 0) {
            alert("Please assign at least one class to this subject.");
            return;
        }

        // Block validation helpers (matches backend validation rules)
        const validateBlock = (label, hours, blockSize) => {
            if (!hours || hours <= 0) return true;
            if (blockSize === 2 && hours % 2 !== 0) {
                alert(`${label} hours must be even when block size is 2 (continuous).`);
                return false;
            }
            return true;
        };

        const seminarDayBased = !!formData.seminar_day_based;
        const seminarBlock = seminarDayBased ? 7 : (formData.seminar_block_size >= 2 ? 2 : 1);
        if (seminarDayBased && formData.seminar_hours_per_week > 0 && formData.seminar_hours_per_week < 7) {
            alert('Seminar day-based mode requires at least 7 periods per week.');
            return;
        }
        if (!seminarDayBased && !validateBlock('Seminar', formData.seminar_hours_per_week, seminarBlock)) return;

        // Calculate total weekly hours from components
        const totalHours =
            formData.theory_hours_per_week +
            formData.lab_hours_per_week +
            formData.tutorial_hours_per_week +
            formData.self_study_hours_per_week +
            formData.seminar_hours_per_week;

        if (totalHours === 0) {
            alert("Subject must have at least 1 hour per week (any component).");
            return;
        }

        const submitData = {
            ...formData,
            weekly_hours: totalHours,
            dept_id: deptId ?? formData.dept_id ?? null,
            seminar_block_size: seminarBlock,
        };

        try {
            if (editingSubject) {
                await subjectsApi.update(editingSubject.id, submitData);
            } else {
                await subjectsApi.create(submitData);
            }
            closeModal();
            await fetchData();
        } catch (err) {
            console.error('Save error:', err);
            const errorDetail = err.response?.data?.detail || err.message || 'Failed to save subject';
            setError(typeof errorDetail === 'object' ? JSON.stringify(errorDetail) : errorDetail);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Are you sure you want to delete this subject?\n\nThis will also remove:\n- All timetable allocations\n- Teacher assignments\n- Component assignments')) return;
        try {
            await subjectsApi.delete(id);
            fetchData();
        } catch (err) {
            setError('Failed to delete subject');
            console.error(err);
        }
    };

    const getTotalHours = () => {
        return formData.theory_hours_per_week +
            formData.lab_hours_per_week +
            formData.tutorial_hours_per_week +
            formData.self_study_hours_per_week +
            formData.seminar_hours_per_week;
    };

    const getLabBlocks = () => {
        return Math.floor(formData.lab_hours_per_week / 2);
    };

    if (loading) {
        return <div className="loading"><div className="spinner"></div></div>;
    }

    return (
        <div className="crud-page">
            <div className="page-header">
                <div>
                    <h1>Subjects</h1>
                    <p>Manage courses with component hours (Theory, Lab, Tutorial, Self Study, Seminar)</p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button className="btn btn-primary" onClick={() => openModal()}>
                        <Plus size={18} />
                        Add Subject
                    </button>
                    <button
                        className="btn btn-secondary"
                        onClick={() => { setShowImportModal(true); setImportStep('upload'); setImportResult(null); setImportFile(null); }}
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)', color: 'white', border: 'none' }}
                    >
                        <Upload size={18} />
                        Import Excel
                    </button>
                </div>
            </div>

            {/* Filter Bar */}
            <div style={{
                display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap',
                marginBottom: '1rem', padding: '0.75rem 1rem',
                background: 'var(--gray-50)', borderRadius: 'var(--radius)',
                border: '1px solid var(--gray-200)'
            }}>
                <Filter size={16} style={{ color: 'var(--gray-500)', flexShrink: 0 }} />
                <input
                    type="text"
                    className="form-input"
                    value={filterName}
                    onChange={(e) => setFilterName(e.target.value)}
                    placeholder="Search Code or Name..."
                    style={{ width: 'auto', minWidth: '150px', fontSize: '0.85rem', padding: '0.4rem 0.6rem' }}
                />

                <select
                    className="form-select"
                    value={filterType}
                    onChange={(e) => setFilterType(e.target.value)}
                    style={{ width: 'auto', minWidth: '120px', fontSize: '0.85rem' }}
                >
                    <option value="">All Types</option>
                    <option value="theory">Theory</option>
                    <option value="lab">Lab</option>
                    <option value="tutorial">Tutorial</option>
                    <option value="elective">Elective</option>
                </select>

                <select
                    className="form-select"
                    value={filterYear}
                    onChange={(e) => setFilterYear(e.target.value)}
                    style={{ width: 'auto', minWidth: '100px', fontSize: '0.85rem' }}
                >
                    <option value="">All Years</option>
                    {[1, 2, 3, 4].map(y => <option key={y} value={y}>Year {y}</option>)}
                </select>

                <select
                    className="form-select"
                    value={filterSemester}
                    onChange={(e) => setFilterSemester(e.target.value)}
                    style={{ width: 'auto', minWidth: '100px', fontSize: '0.85rem' }}
                >
                    <option value="">All Semesters</option>
                    {[1, 2, 3, 4, 5, 6, 7, 8].map(s => <option key={s} value={s}>Sem {s}</option>)}
                </select>

                {(filterName || filterYear || filterSemester || filterType) && (
                    <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => { setFilterName(''); setFilterYear(''); setFilterSemester(''); setFilterType(''); }}
                        style={{ fontSize: '0.8rem' }}
                    >
                        Clear
                    </button>
                )}

                <span style={{ marginLeft: 'auto', fontSize: '0.8rem', color: 'var(--gray-500)', whiteSpace: 'nowrap' }}>
                    {filteredSubjects.length} / {subjects.length} subjects
                </span>
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

            <div className="crud-grid">
                {filteredSubjects.map((subject) => {
                    const theoryHours = subject.theory_hours_per_week ?? subject.weekly_hours ?? 0;
                    const labHours = subject.lab_hours_per_week ?? 0;
                    const tutorialHours = subject.tutorial_hours_per_week ?? 0;
                    const selfStudyHours = subject.self_study_hours_per_week ?? 0;
                    const seminarHours = subject.seminar_hours_per_week ?? 0;
                    const totalHours =
                        theoryHours +
                        labHours +
                        tutorialHours +
                        selfStudyHours +
                        seminarHours;
                    const isElective = subject.is_elective || subject.subject_type === 'elective';

                    return (
                        <div key={subject.id} className={`crud-item ${isElective ? 'elective-highlight' : ''}`}>
                            <div className="crud-item-header">
                                <div>
                                    <h3 className="crud-item-title">
                                        {subject.name}
                                        {isElective && (
                                            <Star size={14} style={{ marginLeft: '6px', color: '#f59e0b' }} />
                                        )}
                                    </h3>
                                    <div className="flex gap-2 items-center">
                                        <span className="text-sm text-muted">{subject.code}</span>
                                        {subject.year && (
                                            <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: '#eef2ff', color: '#6366f1', fontWeight: 600 }}>
                                                Year {subject.year}
                                            </span>
                                        )}
                                        {subject.semester && (
                                            <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: '#f0fdf4', color: '#16a34a', fontWeight: 600 }}>
                                                Sem {subject.semester}
                                            </span>
                                        )}
                                        {subject.semesters && (
                                            <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: '#f1f5f9', color: '#64748b', fontWeight: 600 }}>
                                                {subject.semesters.length} Classes
                                            </span>
                                        )}
                                    </div>
                                </div>
                                <div className="crud-item-actions">
                                    <button className="btn btn-sm btn-secondary" onClick={() => openModal(subject)}>
                                        <Edit2 size={14} />
                                    </button>
                                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(subject.id)}>
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            </div>

                            {/* Component Breakdown */}
                            <div className="component-breakdown" style={{
                                display: 'flex',
                                gap: '8px',
                                flexWrap: 'wrap',
                                marginTop: '10px'
                            }}>
                                {theoryHours > 0 && (
                                    <span className="component-badge theory" style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '4px',
                                        padding: '4px 8px',
                                        borderRadius: '12px',
                                        fontSize: '11px',
                                        fontWeight: '600',
                                        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                        color: 'white'
                                    }}>
                                        <GraduationCap size={12} />
                                        {theoryHours}h Theory
                                    </span>
                                )}
                                {labHours > 0 && (
                                    <span className="component-badge lab" style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '4px',
                                        padding: '4px 8px',
                                        borderRadius: '12px',
                                        fontSize: '11px',
                                        fontWeight: '600',
                                        background: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
                                        color: 'white'
                                    }}>
                                        <Beaker size={12} />
                                        {labHours}h Lab ({Math.floor(labHours / 2)} block)
                                    </span>
                                )}
                                {tutorialHours > 0 && (
                                    <span className="component-badge tutorial" style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '4px',
                                        padding: '4px 8px',
                                        borderRadius: '12px',
                                        fontSize: '11px',
                                        fontWeight: '600',
                                        background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                                        color: 'white'
                                    }}>
                                        {tutorialHours}h Tutorial
                                    </span>
                                )}
                                {selfStudyHours > 0 && (
                                    <span className="component-badge self-study" style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '4px',
                                        padding: '4px 8px',
                                        borderRadius: '12px',
                                        fontSize: '11px',
                                        fontWeight: '600',
                                        background: 'linear-gradient(135deg, #a855f7 0%, #ec4899 100%)',
                                        color: 'white'
                                    }}>
                                        {selfStudyHours}h Self Study
                                    </span>
                                )}
                                {seminarHours > 0 && (
                                    <span className="component-badge self-study" style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '4px',
                                        padding: '4px 8px',
                                        borderRadius: '12px',
                                        fontSize: '11px',
                                        fontWeight: '600',
                                        background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
                                        color: 'white'
                                    }}>
                                        {seminarHours}h Seminar
                                    </span>
                                )}
                            </div>

                            <div className="crud-item-details" style={{ marginTop: '8px', alignItems: 'center' }}>
                                <span className="crud-item-detail">
                                    <Clock size={14} /> {totalHours} hrs/week
                                </span>
                                {isElective && (
                                    <span className="badge badge-elective" style={{
                                        background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                                        color: 'white',
                                        fontWeight: '600'
                                    }}>
                                        Elective
                                    </span>
                                )}
                                {/* Pass Rate & Priority as simple text */}
                                {subject.previous_year_pass_percentage != null && (
                                    <span className="crud-item-detail" style={{ marginLeft: 'auto', fontSize: '12px', color: '#64748b' }}>
                                        Pass: {subject.previous_year_pass_percentage}%
                                    </span>
                                )}
                            </div>

                            {subject.semesters && subject.semesters.length > 0 && (
                                <div className="mt-3 text-xs text-muted border-t pt-2">
                                    <strong>Classes:</strong> {subject.semesters.map(s => s.name.replace('Semester', 'Sem')).join(', ')}
                                </div>
                            )}
                            {subject.departments && subject.departments.length > 0 && (
                                <div className="text-xs text-muted" style={{ marginTop: '4px' }}>
                                    <strong>Depts:</strong>{' '}
                                    {subject.departments.map(d => (
                                        <span key={d.id} style={{
                                            display: 'inline-block',
                                            padding: '1px 6px',
                                            borderRadius: '4px',
                                            background: '#ede9fe',
                                            color: '#7c3aed',
                                            fontWeight: 600,
                                            fontSize: '10px',
                                            marginRight: '4px'
                                        }}>
                                            {d.code}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {subjects.length === 0 && (
                <div className="empty-state">
                    <BookOpen size={48} />
                    <h3>No Subjects Yet</h3>
                    <p>Add your first subject to get started</p>
                    <button className="btn btn-primary" onClick={() => openModal()}>
                        <Plus size={18} />
                        Add Subject
                    </button>
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '600px' }}>
                        <div className="modal-header">
                            <h2>{editingSubject ? 'Edit Subject' : 'Add Subject'}</h2>
                            <button className="modal-close" onClick={closeModal}>
                                <X size={20} />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            {/* Basic Info */}
                            <div className="form-group">
                                <label className="form-label">Subject Name *</label>
                                <input
                                    type="text"
                                    className="form-input"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    required
                                    placeholder="e.g., Data Structures"
                                />
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Subject Code *</label>
                                    <input
                                        type="text"
                                        className="form-input"
                                        value={formData.code}
                                        onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                        required
                                        placeholder="e.g., CS201"
                                    />
                                </div>
                                <div className="form-group">
                                    <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <input
                                            type="checkbox"
                                            checked={formData.is_elective}
                                            onChange={(e) => setFormData({
                                                ...formData,
                                                is_elective: e.target.checked,
                                                subject_type: e.target.checked ? 'elective' : 'regular'
                                            })}
                                            style={{ width: '18px', height: '18px' }}
                                        />
                                        <Star size={16} style={{ color: formData.is_elective ? '#f59e0b' : '#9ca3af' }} />
                                        Mark as Elective
                                    </label>
                                    <p className="text-xs text-muted mt-1">
                                        Electives are scheduled at common slots across all departments.
                                    </p>
                                </div>
                            </div>

                            {/* Year & Semester Selection */}
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Year *</label>
                                    <select
                                        className="form-select"
                                        value={formData.year}
                                        onChange={(e) => setFormData({ ...formData, year: parseInt(e.target.value), semester_ids: [] })}
                                    >
                                        {[1, 2, 3, 4].map(y => (
                                            <option key={y} value={y}>Year {y}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Semester *</label>
                                    <select
                                        className="form-select"
                                        value={formData.semester}
                                        onChange={(e) => setFormData({ ...formData, semester: parseInt(e.target.value), semester_ids: [] })}
                                    >
                                        {[1, 2, 3, 4, 5, 6, 7, 8].map(s => (
                                            <option key={s} value={s}>Semester {s}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* Component Hours Section */}
                            <div style={{
                                background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
                                borderRadius: '12px',
                                padding: '16px',
                                marginBottom: '16px',
                                border: '1px solid #e2e8f0'
                            }}>
                                <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#475569' }}>
                                    Weekly Component Hours
                                </h4>
                                <p className="text-xs text-muted mb-3">
                                    Add weekly hours per component. Labs (and 2-period blocks) are scheduled as continuous periods.
                                </p>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
                                    {/* Theory Hours */}
                                    <div style={{
                                        background: 'white',
                                        borderRadius: '8px',
                                        padding: '12px',
                                        textAlign: 'center',
                                        border: '2px solid #667eea'
                                    }}>
                                        <GraduationCap size={20} style={{ color: '#667eea', marginBottom: '6px' }} />
                                        <div className="text-xs font-bold text-gray-600 mb-1">Theory</div>
                                        <input
                                            type="number"
                                            className="form-input"
                                            value={formData.theory_hours_per_week}
                                            onChange={(e) => setFormData({
                                                ...formData,
                                                theory_hours_per_week: parseInt(e.target.value) || 0
                                            })}
                                            min={0}
                                            max={25}
                                            style={{ textAlign: 'center', fontWeight: 'bold' }}
                                        />
                                        <div className="text-xs text-muted mt-1">hours/week</div>
                                    </div>

                                    {/* Lab Hours */}
                                    <div style={{
                                        background: 'white',
                                        borderRadius: '8px',
                                        padding: '12px',
                                        textAlign: 'center',
                                        border: '2px solid #11998e'
                                    }}>
                                        <Beaker size={20} style={{ color: '#11998e', marginBottom: '6px' }} />
                                        <div className="text-xs font-bold text-gray-600 mb-1">Lab</div>
                                        <select
                                            className="form-input"
                                            value={formData.lab_hours_per_week}
                                            onChange={(e) => setFormData({
                                                ...formData,
                                                lab_hours_per_week: parseInt(e.target.value)
                                            })}
                                            style={{ textAlign: 'center', fontWeight: 'bold' }}
                                        >
                                            <option value={0}>0 hours</option>
                                            <option value={2}>2 hours (1 block)</option>
                                            <option value={4}>4 hours (2 blocks)</option>
                                            <option value={6}>6 hours (3 blocks)</option>
                                        </select>
                                        <div className="text-xs text-muted mt-1">1 block = 2 periods</div>
                                    </div>

                                    {/* Tutorial Hours */}
                                    <div style={{
                                        background: 'white',
                                        borderRadius: '8px',
                                        padding: '12px',
                                        textAlign: 'center',
                                        border: '2px solid #f093fb'
                                    }}>
                                        <BookOpen size={20} style={{ color: '#f093fb', marginBottom: '6px' }} />
                                        <div className="text-xs font-bold text-gray-600 mb-1">Tutorial</div>
                                        <input
                                            type="number"
                                            className="form-input"
                                            value={formData.tutorial_hours_per_week}
                                            onChange={(e) => setFormData({
                                                ...formData,
                                                tutorial_hours_per_week: parseInt(e.target.value) || 0
                                            })}
                                            min={0}
                                            max={4}
                                            style={{ textAlign: 'center', fontWeight: 'bold' }}
                                        />
                                        <div className="text-xs text-muted mt-1">hours/week</div>
                                    </div>
                                </div>

                                {/* Optional / Extended Components */}
                                <div style={{ marginTop: '14px' }}>
                                    <div className="text-xs font-bold text-gray-600 mb-2">
                                        Optional Components
                                    </div>

                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
                                        {/* Self Study */}
                                        <div style={{
                                            background: 'white',
                                            borderRadius: '8px',
                                            padding: '12px',
                                            border: '2px solid #a855f7'
                                        }}>
                                            <div className="text-xs font-bold text-gray-600 mb-2">Self Study</div>
                                            <input
                                                type="number"
                                                className="form-input"
                                                value={formData.self_study_hours_per_week}
                                                onChange={(e) => setFormData({
                                                    ...formData,
                                                    self_study_hours_per_week: parseInt(e.target.value) || 0
                                                })}
                                                min={0}
                                                max={10}
                                                style={{ textAlign: 'center', fontWeight: 'bold' }}
                                            />
                                            <div className="text-xs text-muted mt-1">hours/week</div>
                                            <div className="text-xs text-muted mt-2">Single period</div>
                                        </div>

                                        {/* Seminar */}
                                        <div style={{
                                            background: 'white',
                                            borderRadius: '8px',
                                            padding: '12px',
                                            border: '2px solid #f97316'
                                        }}>
                                            <div className="text-xs font-bold text-gray-600 mb-2">Seminar</div>
                                            <input
                                                type="number"
                                                className="form-input"
                                                value={formData.seminar_hours_per_week}
                                                onChange={(e) => setFormData({
                                                    ...formData,
                                                    seminar_hours_per_week: parseInt(e.target.value) || 0
                                                })}
                                                min={0}
                                                max={35}
                                                style={{ textAlign: 'center', fontWeight: 'bold' }}
                                            />
                                            <div className="text-xs text-muted mt-1">periods/week</div>

                                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px', fontSize: '12px' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={!!formData.seminar_day_based}
                                                    onChange={(e) => setFormData({
                                                        ...formData,
                                                        seminar_day_based: e.target.checked
                                                    })}
                                                />
                                                Day-based (7 periods)
                                            </label>

                                            <select
                                                className="form-input mt-2"
                                                value={formData.seminar_block_size}
                                                onChange={(e) => setFormData({
                                                    ...formData,
                                                    seminar_block_size: parseInt(e.target.value) || 2
                                                })}
                                                disabled={!!formData.seminar_day_based}
                                            >
                                                <option value={1}>Single period</option>
                                                <option value={2}>Continuous (2)</option>
                                            </select>
                                            {formData.seminar_day_based && (
                                                <div className="text-xs text-muted mt-1">
                                                    Day-based overrides block size.
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Total Summary */}
                                <div style={{
                                    marginTop: '12px',
                                    padding: '10px',
                                    background: 'linear-gradient(135deg, #1e293b 0%, #334155 100%)',
                                    borderRadius: '8px',
                                    color: 'white',
                                    textAlign: 'center'
                                }}>
                                    <strong>Total: {getTotalHours()} hours/week</strong>
                                    {getLabBlocks() > 0 && (
                                        <span style={{ marginLeft: '12px', opacity: 0.8 }}>
                                            ({getLabBlocks()} lab block{getLabBlocks() > 1 ? 's' : ''})
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Academic Performance & Importance Section */}
                            <div style={{
                                background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
                                borderRadius: '12px',
                                padding: '16px',
                                marginBottom: '16px',
                                border: '1px solid #e2e8f0'
                            }}>
                                <h4 style={{ margin: '0 0 4px 0', fontSize: '14px', color: '#475569', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <TrendingUp size={16} style={{ color: '#f59e0b' }} />
                                    Academic Importance
                                </h4>
                                <p className="text-xs text-muted mb-3">
                                    Higher importance + lower pass rate = prioritized for morning slots.
                                </p>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
                                    {/* Pass Rate */}
                                    <div style={{
                                        background: 'white',
                                        borderRadius: '8px',
                                        padding: '12px',
                                        textAlign: 'center',
                                        border: '2px solid #22c55e'
                                    }}>
                                        <Star size={20} style={{ color: '#22c55e', marginBottom: '6px' }} />
                                        <div className="text-xs font-bold text-gray-600 mb-1">Pass Rate</div>
                                        <input
                                            type="number"
                                            className="form-input"
                                            value={formData.previous_year_pass_percentage ?? ''}
                                            onChange={(e) => setFormData({
                                                ...formData,
                                                previous_year_pass_percentage: e.target.value === '' ? null : Math.min(100, Math.max(0, parseInt(e.target.value) || 0)),
                                                // Default importance_level to NORMAL so backend doesn't complain if required
                                                importance_level: 'NORMAL'
                                            })}
                                            min={0}
                                            max={100}
                                            placeholder="—"
                                            style={{ textAlign: 'center', fontWeight: 'bold' }}
                                        />
                                        <div className="text-xs text-muted mt-1">prev. year %</div>
                                    </div>

                                    {/* Auto Priority Score */}
                                    <div style={{
                                        background: 'white',
                                        borderRadius: '8px',
                                        padding: '12px',
                                        textAlign: 'center',
                                        border: '2px solid #6366f1'
                                    }}>
                                        <Clock size={20} style={{ color: '#6366f1', marginBottom: '6px' }} />
                                        <div className="text-xs font-bold text-gray-600 mb-1">Priority</div>
                                        {(() => {
                                            const pct = formData.previous_year_pass_percentage;
                                            let score = 0; // Default P0

                                            // New logic: Priority strictly based on pass percentage
                                            if (pct != null) {
                                                if (pct < 50) score = 3;       // Critical for < 50%
                                                else if (pct < 70) score = 2;  // Elevated for 50-69%
                                                else if (pct < 85) score = 1;  // Standard for 70-84%
                                                else score = 0;                // None for >= 85%
                                            }

                                            const labels = { 0: 'None', 1: 'Standard', 2: 'Elevated', 3: 'Critical' };
                                            const bgColors = { 0: '#f1f5f9', 1: '#eef2ff', 2: '#fef3c7', 3: '#fee2e2' };
                                            const textColors = { 0: '#64748b', 1: '#6366f1', 2: '#d97706', 3: '#dc2626' };
                                            return (
                                                <div style={{
                                                    padding: '8px 12px',
                                                    borderRadius: '8px',
                                                    background: bgColors[score],
                                                    marginTop: '4px',
                                                }}>
                                                    <div style={{
                                                        fontSize: '18px',
                                                        fontWeight: '800',
                                                        color: textColors[score],
                                                    }}>
                                                        P{score}
                                                    </div>
                                                    <div style={{
                                                        fontSize: '10px',
                                                        fontWeight: '600',
                                                        color: textColors[score],
                                                        marginTop: '2px',
                                                    }}>
                                                        {labels[score]}
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    </div>
                                </div>
                            </div>

                            {/* Class Assignment */}
                            <div className="form-group">
                                <label className="form-label">Assigned Classes (Mandatory) *</label>
                                {/* Year/Semester filter info */}
                                {!formData.is_elective && (
                                    <div style={{
                                        background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                                        border: '1px solid #93c5fd',
                                        borderRadius: '8px',
                                        padding: '8px 12px',
                                        marginBottom: '8px',
                                        fontSize: '12px',
                                        color: '#1e40af',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '6px'
                                    }}>
                                        <AlertCircle size={14} />
                                        Showing only Year {formData.year}, Semester {formData.semester} classes.
                                        Change the year/semester above to see different classes.
                                    </div>
                                )}
                                <div style={{
                                    maxHeight: '200px',
                                    overflowY: 'auto',
                                    border: '1px solid #e2e8f0',
                                    padding: '12px',
                                    borderRadius: '6px',
                                    backgroundColor: '#f8fafc'
                                }}>
                                    {(() => {
                                        // Filter semesters: for non-elective, show only matching year & semester
                                        const eligibleSemesters = formData.is_elective
                                            ? semesters
                                            : semesters.filter(s =>
                                                s.year === formData.year &&
                                                s.semester_number === formData.semester
                                            );
                                        
                                        if (eligibleSemesters.length === 0) {
                                            return (
                                                <div style={{
                                                    padding: '16px',
                                                    textAlign: 'center',
                                                    color: '#dc2626',
                                                    fontSize: '13px'
                                                }}>
                                                    <AlertCircle size={20} style={{ marginBottom: '4px' }} />
                                                    <p style={{ margin: '4px 0' }}>
                                                        No classes found for Year {formData.year}, Semester {formData.semester}.
                                                    </p>
                                                    <p className="text-xs text-muted">
                                                        Make sure classes exist for this year and semester, or change the subject's year/semester.
                                                    </p>
                                                </div>
                                            );
                                        }
                                        
                                        const groupedBySemNum = [...new Set(eligibleSemesters.map(s => s.semester_number))].sort((a, b) => a - b);
                                        return groupedBySemNum.map(semNum => (
                                            <div key={semNum} className="mb-3">
                                                <div className="text-xs font-bold text-gray-500 mb-1 uppercase tracking-wider">
                                                    {semNum === 1 ? '1st' : semNum === 2 ? '2nd' : semNum === 3 ? '3rd' : `${semNum}th`} Semester
                                                </div>
                                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '8px' }}>
                                                    {eligibleSemesters.filter(s => s.semester_number === semNum).map((sem) => (
                                                        <label key={sem.id} style={{
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            gap: '8px',
                                                            fontSize: '13px',
                                                            cursor: 'pointer',
                                                            padding: '4px',
                                                            borderRadius: '4px',
                                                            backgroundColor: 'white',
                                                            border: formData.semester_ids.includes(sem.id)
                                                                ? '2px solid #667eea'
                                                                : '1px solid #eee'
                                                        }}>
                                                            <input
                                                                type="checkbox"
                                                                checked={formData.semester_ids.includes(sem.id)}
                                                                onChange={(e) => {
                                                                    const ids = new Set(formData.semester_ids);
                                                                    if (e.target.checked) ids.add(sem.id);
                                                                    else ids.delete(sem.id);
                                                                    setFormData({ ...formData, semester_ids: Array.from(ids) })
                                                                }}
                                                            />
                                                            <span>{sem.name}</span>
                                                        </label>
                                                    ))}
                                                </div>
                                            </div>
                                        ));
                                    })()}
                                </div>
                                <p className="text-xs text-muted mt-1">
                                    <strong>Academic Rule:</strong> Subjects can only be assigned to classes of the same year and semester.
                                    {formData.is_elective && <span style={{ color: '#f59e0b' }}> (Elective - can span multiple semesters)</span>}
                                </p>
                            </div>

                            <div className="modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={closeModal}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    {editingSubject ? 'Update' : 'Create'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
            {/* Import Modal */}
            {showImportModal && (
                <div className="modal-overlay" onClick={() => setShowImportModal(false)}>
                    <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px', maxHeight: '90vh', overflow: 'auto' }}>
                        <div className="modal-header">
                            <h2 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                <Upload size={22} />
                                Bulk Subject Import
                            </h2>
                            <button className="modal-close" onClick={() => setShowImportModal(false)}>
                                <X size={20} />
                            </button>
                        </div>

                        {/* Step 1: Upload */}
                        {importStep === 'upload' && (
                            <div style={{ padding: '20px' }}>
                                <div style={{
                                    background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
                                    borderRadius: '12px',
                                    padding: '20px',
                                    border: '2px dashed #16a34a',
                                    textAlign: 'center',
                                    marginBottom: '16px',
                                }}>
                                    <Upload size={40} style={{ color: '#16a34a', marginBottom: '10px' }} />
                                    <h3 style={{ margin: '0 0 8px 0', color: '#15803d' }}>Upload Excel or CSV</h3>
                                    <p style={{ fontSize: '13px', color: '#166534', marginBottom: '16px' }}>
                                        Use the template with SUBJECT_IMPORT sheet and fill in your subjects.
                                    </p>
                                    <input
                                        type="file"
                                        accept=".xlsx,.xls,.csv"
                                        id="import-file-input"
                                        style={{ display: 'none' }}
                                        onChange={(e) => {
                                            if (e.target.files?.[0]) setImportFile(e.target.files[0]);
                                        }}
                                    />
                                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
                                        <label
                                            htmlFor="import-file-input"
                                            className="btn btn-primary"
                                            style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                                        >
                                            <Upload size={16} />
                                            Choose File
                                        </label>
                                        <a
                                            href={subjectImportApi.getTemplateUrl()}
                                            className="btn btn-secondary"
                                            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', textDecoration: 'none' }}
                                        >
                                            <Download size={16} />
                                            Download Template
                                        </a>
                                    </div>
                                    {importFile && (
                                        <div style={{ marginTop: '14px', padding: '10px', background: 'white', borderRadius: '8px', display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                            <CheckCircle size={16} style={{ color: '#16a34a' }} />
                                            <strong>{importFile.name}</strong>
                                            <span style={{ fontSize: '12px', color: '#64748b' }}>({(importFile.size / 1024).toFixed(1)} KB)</span>
                                        </div>
                                    )}
                                </div>

                                {importFile && (
                                    <div className="modal-actions">
                                        <button className="btn btn-secondary" onClick={() => setShowImportModal(false)}>Cancel</button>
                                        <button
                                            className="btn btn-primary"
                                            disabled={importLoading}
                                            onClick={async () => {
                                                setImportLoading(true);
                                                setError(null);
                                                try {
                                                    const res = await subjectImportApi.upload(importFile);
                                                    setImportResult(res.data);
                                                    setImportStep('preview');
                                                } catch (err) {
                                                    const detail = err.response?.data?.detail || err.message;
                                                    setError(typeof detail === 'object' ? JSON.stringify(detail) : detail);
                                                } finally {
                                                    setImportLoading(false);
                                                }
                                            }}
                                        >
                                            {importLoading ? <><Loader2 size={16} className="spin" /> Validating...</> : 'Validate & Preview'}
                                        </button>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Step 2: Preview */}
                        {importStep === 'preview' && importResult && (
                            <div style={{ padding: '20px' }}>
                                {/* Schema errors */}
                                {importResult.schema_errors?.length > 0 && (
                                    <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', padding: '14px', marginBottom: '16px' }}>
                                        <h4 style={{ color: '#dc2626', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <XCircle size={18} /> Schema Errors
                                        </h4>
                                        {importResult.schema_errors.map((e, i) => (
                                            <div key={i} style={{ fontSize: '13px', color: '#b91c1c', padding: '4px 0' }}>• {e}</div>
                                        ))}
                                    </div>
                                )}

                                {/* Summary */}
                                {!importResult.schema_errors?.length && (
                                    <>
                                        <div style={{
                                            display: 'grid',
                                            gridTemplateColumns: 'repeat(4, 1fr)',
                                            gap: '12px',
                                            marginBottom: '16px',
                                        }}>
                                            {[
                                                { label: 'Total Rows', value: importResult.total_rows, color: '#3b82f6' },
                                                { label: 'Valid', value: importResult.total_rows - importResult.failed, color: '#16a34a' },
                                                { label: 'Invalid', value: importResult.failed, color: '#dc2626' },
                                                { label: 'Will Update', value: importResult.rows?.filter(r => r.warnings?.some(w => w.includes('UPDATE'))).length || 0, color: '#f59e0b' },
                                            ].map(({ label, value, color }) => (
                                                <div key={label} style={{
                                                    textAlign: 'center',
                                                    padding: '12px',
                                                    borderRadius: '10px',
                                                    background: `${color}10`,
                                                    border: `2px solid ${color}30`,
                                                }}>
                                                    <div style={{ fontSize: '24px', fontWeight: '800', color }}>{value}</div>
                                                    <div style={{ fontSize: '12px', color: '#64748b', fontWeight: '600' }}>{label}</div>
                                                </div>
                                            ))}
                                        </div>

                                        {/* Row table */}
                                        <div style={{ maxHeight: '400px', overflow: 'auto', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                                                <thead style={{ position: 'sticky', top: 0, background: '#1e293b', color: 'white', zIndex: 1 }}>
                                                    <tr>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Row</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Status</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Code</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Name</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Dept</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'center' }}>Hours</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Issues</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {importResult.rows?.map((row, idx) => {
                                                        const isInvalid = row.status === 'invalid';
                                                        const hasWarnings = row.warnings?.length > 0;
                                                        const totalH = (parseInt(row.data?.['Theory Hours'] || 0) || 0)
                                                            + (parseInt(row.data?.['Lab Hours'] || 0) || 0)
                                                            + (parseInt(row.data?.['Tutorial Hours'] || 0) || 0)
                                                            + (parseInt(row.data?.['Seminar Hours'] || 0) || 0)
                                                            + (parseInt(row.data?.['Self Study Hours'] || 0) || 0);
                                                        return (
                                                            <tr key={idx} style={{
                                                                background: isInvalid ? '#fef2f2' : hasWarnings ? '#fffbeb' : idx % 2 ? '#f8fafc' : 'white',
                                                                borderBottom: '1px solid #e2e8f0',
                                                            }}>
                                                                <td style={{ padding: '6px 10px', fontWeight: '600' }}>{row.row}</td>
                                                                <td style={{ padding: '6px 10px' }}>
                                                                    {isInvalid ? (
                                                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#dc2626', fontWeight: '600' }}>
                                                                            <XCircle size={14} /> Invalid
                                                                        </span>
                                                                    ) : (
                                                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#16a34a', fontWeight: '600' }}>
                                                                            <CheckCircle size={14} /> Valid
                                                                        </span>
                                                                    )}
                                                                </td>
                                                                <td style={{ padding: '6px 10px', fontFamily: 'monospace', fontWeight: '600' }}>{row.data?.['Subject Code'] || '—'}</td>
                                                                <td style={{ padding: '6px 10px' }}>{row.data?.['Subject Name'] || '—'}</td>
                                                                <td style={{ padding: '6px 10px' }}>{row.data?.['Department'] || '—'}</td>
                                                                <td style={{ padding: '6px 10px', textAlign: 'center', fontWeight: '600' }}>{totalH}</td>
                                                                <td style={{ padding: '6px 10px', fontSize: '11px' }}>
                                                                    {row.errors?.map((e, i) => (
                                                                        <div key={i} style={{ color: '#dc2626' }}>✗ {e}</div>
                                                                    ))}
                                                                    {row.warnings?.map((w, i) => (
                                                                        <div key={`w${i}`} style={{ color: '#d97706' }}>⚠ {w}</div>
                                                                    ))}
                                                                </td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>

                                        <div className="modal-actions" style={{ marginTop: '16px' }}>
                                            <button className="btn btn-secondary" onClick={() => { setImportStep('upload'); setImportResult(null); }}>Back</button>
                                            <button className="btn btn-secondary" onClick={() => setShowImportModal(false)}>Cancel</button>
                                            {importResult.failed === 0 && (
                                                <button
                                                    className="btn btn-primary"
                                                    disabled={importCommitting}
                                                    style={{ background: 'linear-gradient(135deg, #059669, #10b981)', border: 'none' }}
                                                    onClick={async () => {
                                                        setImportCommitting(true);
                                                        setError(null);
                                                        try {
                                                            const res = await subjectImportApi.commit(importResult.batch_id);
                                                            setImportResult(res.data);
                                                            setImportStep('committed');
                                                            fetchData();
                                                        } catch (err) {
                                                            const detail = err.response?.data?.detail || err.message;
                                                            setError(typeof detail === 'object' ? JSON.stringify(detail) : detail);
                                                        } finally {
                                                            setImportCommitting(false);
                                                        }
                                                    }}
                                                >
                                                    {importCommitting ? <><Loader2 size={16} className="spin" /> Importing...</> : <><CheckCircle size={16} /> Commit Import ({importResult.total_rows - importResult.failed} subjects)</>}
                                                </button>
                                            )}
                                            {importResult.failed > 0 && importResult.total_rows - importResult.failed > 0 && (
                                                <button
                                                    className="btn btn-primary"
                                                    disabled={importCommitting}
                                                    style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)', border: 'none' }}
                                                    onClick={async () => {
                                                        setImportCommitting(true);
                                                        setError(null);
                                                        try {
                                                            const res = await subjectImportApi.commit(importResult.batch_id);
                                                            setImportResult(res.data);
                                                            setImportStep('committed');
                                                            fetchData();
                                                        } catch (err) {
                                                            const detail = err.response?.data?.detail || err.message;
                                                            setError(typeof detail === 'object' ? JSON.stringify(detail) : detail);
                                                        } finally {
                                                            setImportCommitting(false);
                                                        }
                                                    }}
                                                >
                                                    {importCommitting ? <><Loader2 size={16} className="spin" /> Importing...</> : <><CheckCircle size={16} /> Import Valid Only ({importResult.total_rows - importResult.failed})</>}
                                                </button>
                                            )}
                                        </div>
                                    </>
                                )}
                            </div>
                        )}

                        {/* Step 3: Committed */}
                        {importStep === 'committed' && importResult && (
                            <div style={{ padding: '20px' }}>
                                <div style={{
                                    textAlign: 'center',
                                    padding: '30px',
                                    background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)',
                                    borderRadius: '12px',
                                    marginBottom: '20px',
                                }}>
                                    <CheckCircle size={48} style={{ color: '#16a34a', marginBottom: '12px' }} />
                                    <h3 style={{ color: '#15803d', margin: '0 0 8px 0' }}>Import Successful!</h3>
                                    <p style={{ color: '#166534', fontSize: '14px', margin: 0 }}>
                                        Subjects are now available in the system.
                                    </p>
                                </div>

                                <div style={{
                                    display: 'grid',
                                    gridTemplateColumns: 'repeat(4, 1fr)',
                                    gap: '12px',
                                    marginBottom: '20px',
                                }}>
                                    {[
                                        { label: 'Imported', value: importResult.imported, color: '#16a34a', icon: '✓' },
                                        { label: 'Updated', value: importResult.updated, color: '#3b82f6', icon: '↻' },
                                        { label: 'Skipped', value: importResult.skipped, color: '#f59e0b', icon: '—' },
                                        { label: 'Failed', value: importResult.failed, color: '#dc2626', icon: '✗' },
                                    ].map(({ label, value, color, icon }) => (
                                        <div key={label} style={{
                                            textAlign: 'center',
                                            padding: '14px',
                                            borderRadius: '10px',
                                            background: `${color}10`,
                                            border: `2px solid ${color}30`,
                                        }}>
                                            <div style={{ fontSize: '28px', fontWeight: '800', color }}>{icon} {value}</div>
                                            <div style={{ fontSize: '12px', color: '#64748b', fontWeight: '600' }}>{label}</div>
                                        </div>
                                    ))}
                                </div>

                                {/* Health Check */}
                                {importResult.health_check && (
                                    <div style={{
                                        background: importResult.health_check.all_clear ? '#f0fdf4' : '#fffbeb',
                                        border: `1px solid ${importResult.health_check.all_clear ? '#86efac' : '#fde68a'}`,
                                        borderRadius: '8px',
                                        padding: '14px',
                                        marginBottom: '16px',
                                    }}>
                                        <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            {importResult.health_check.all_clear ? <CheckCircle size={16} style={{ color: '#16a34a' }} /> : <AlertCircle size={16} style={{ color: '#f59e0b' }} />}
                                            Post-Import Health Check
                                        </h4>
                                        <div style={{ fontSize: '13px', color: '#475569' }}>
                                            <div>Total Subjects: <strong>{importResult.health_check.total_subjects}</strong></div>
                                            <div>Total Classes: <strong>{importResult.health_check.total_classes}</strong></div>
                                            <div style={{ marginTop: '4px' }}>
                                                Generator Status: <strong style={{ color: importResult.generator_readiness === 'ready' ? '#16a34a' : '#f59e0b' }}>
                                                    {importResult.generator_readiness === 'ready' ? '✓ Ready' : '⚠ Warnings'}
                                                </strong>
                                            </div>
                                        </div>
                                        {importResult.health_check.warnings?.map((w, i) => (
                                            <div key={i} style={{ fontSize: '12px', color: '#d97706', marginTop: '4px' }}>⚠ {w}</div>
                                        ))}
                                        {importResult.health_check.errors?.map((e, i) => (
                                            <div key={i} style={{ fontSize: '12px', color: '#dc2626', marginTop: '4px' }}>✗ {e}</div>
                                        ))}
                                    </div>
                                )}

                                <div className="modal-actions">
                                    <button className="btn btn-primary" onClick={() => setShowImportModal(false)}>Done</button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
