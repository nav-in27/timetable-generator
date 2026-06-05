/**
 * Teachers Management Page
 * CRUD operations for teachers
 */
import { useEffect, useState } from 'react';
import {
    Plus,
    Edit2,
    Trash2,
    X,
    User,
    Mail,
    Clock,
    Star,
    AlertCircle,
    Filter,
    Upload,
    Download,
    CheckCircle,
    XCircle,
    Loader2,
} from 'lucide-react';
import { teachersApi, subjectsApi, semestersApi, teacherImportApi } from '../services/api';
import { roomsApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import './CrudPage.css';

export default function TeachersPage() {
    const { departments, selectedDeptId, setSelectedDeptId, deptId, reloadDepartments } = useDepartmentContext();
    const [teachers, setTeachers] = useState([]);
    const [subjects, setSubjects] = useState([]);
    const [semesters, setSemesters] = useState([]);
    const [rooms, setRooms] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filterName, setFilterName] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [editingTeacher, setEditingTeacher] = useState(null);
    const [assignmentComponentType, setAssignmentComponentType] = useState('theory');
    const [selectedIds, setSelectedIds] = useState([]);

    // Import State
    const [showImportModal, setShowImportModal] = useState(false);
    const [importFile, setImportFile] = useState(null);
    const [importResult, setImportResult] = useState(null);
    const [importLoading, setImportLoading] = useState(false);
    const [importCommitting, setImportCommitting] = useState(false);
    const [importStep, setImportStep] = useState('upload');
    const [formData, setFormData] = useState({
        name: '',
        teacher_code: '',
        dept_id: '',
        email: '',
        phone: '',
        max_hours_per_week: 20,
        experience_years: 1,
        experience_score: 0.5,
        available_days: '0,1,2,3,4',
        subject_ids: [],
    });

    useEffect(() => {
        reloadDepartments();
        fetchData();
    }, []);

    useEffect(() => {
        fetchData();
    }, [deptId]);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        const semParams = {};
        if (deptId) semParams.deptId = deptId;

        // Load each resource INDEPENDENTLY so one failure doesn't block others
        const results = await Promise.allSettled([
            teachersApi.getAll(false, deptId),
            subjectsApi.getAll({ deptId }),
            semestersApi.getAll(semParams),
            roomsApi.getAll({ deptId }),
        ]);

        const [teachersRes, subjectsRes, semestersRes, roomsRes] = results;

        if (teachersRes.status === 'fulfilled') {
            setTeachers(teachersRes.value.data);
        } else {
            console.error('Teachers load failed:', teachersRes.reason);
            setTeachers([]);
            setError('Failed to load teachers');
        }

        if (subjectsRes.status === 'fulfilled') setSubjects(subjectsRes.value.data);
        else setSubjects([]);

        if (semestersRes.status === 'fulfilled') setSemesters(semestersRes.value.data);
        else setSemesters([]);

        if (roomsRes.status === 'fulfilled') setRooms(roomsRes.value.data);
        else setRooms([]);

        setLoading(false);
    };

    const openModal = (teacher = null) => {
        setAssignmentComponentType('theory');
        if (teacher) {
            setEditingTeacher(teacher);
            setFormData({
                name: teacher.name,
                teacher_code: teacher.teacher_code || '',
                dept_id: teacher.dept_id || '',
                email: teacher.email || '',
                phone: teacher.phone || '',
                max_hours_per_week: teacher.max_hours_per_week,
                experience_years: teacher.experience_years,
                experience_score: teacher.experience_score,
                available_days: teacher.available_days,
                subject_ids: teacher.subjects?.map(s => s.id) || [],
                is_common_service_dept: teacher.is_common_service_dept || false,
                allowed_department_ids: teacher.allowed_department_ids || [],
            });
        } else {
            setEditingTeacher(null);
            setFormData({
                name: '',
                teacher_code: '',
                dept_id: deptId ? String(deptId) : '',
                email: '',
                phone: '',
                max_hours_per_week: 20,
                experience_years: 1,
                experience_score: 0.5,
                available_days: '0,1,2,3,4',
                subject_ids: [],
                is_common_service_dept: false,
                allowed_department_ids: [],
            });
        }
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingTeacher(null);
        setAssignmentComponentType('theory');
    };

    const getErrorMessage = (err) => {
        if (typeof err === 'string') return err;
        const data = err?.response?.data;
        if (typeof data === 'string') return data;
        if (data?.detail) return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        if (data?.message) return data.message;
        if (Array.isArray(data)) return data.map(e => e.msg || JSON.stringify(e)).join('; ');
        return err?.message || 'An error occurred';
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            // Ensure dept_id and teacher_code are handled correctly
            const payload = {
                ...formData,
                dept_id: formData.dept_id ? parseInt(formData.dept_id) : null,
                // generate teacher code if empty? No, backend handles it or requires it.
                // It is required in schema, but nullable in model.
                // Let's assume user inputs it or handle in backend.
            };

            if (editingTeacher) {
                await teachersApi.update(editingTeacher.id, payload);
            } else {
                await teachersApi.create(payload);
            }
            fetchData();
            closeModal();
        } catch (err) {
            const errorMsg = getErrorMessage(err);
            setError(errorMsg);
            console.error(err);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Are you sure you want to remove this teacher?')) return;
        try {
            await teachersApi.delete(id);
            fetchData();
            setSelectedIds(prev => prev.filter(selectedId => selectedId !== id));
        } catch (err) {
            const errorMsg = getErrorMessage(err);
            setError(errorMsg);
            console.error(err);
        }
    };

    const toggleSelection = (id) => {
        setSelectedIds(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
    };
    
    const handleSelectAll = () => {
        if (selectedIds.length === filteredTeachers.length && filteredTeachers.length > 0) {
            setSelectedIds([]);
        } else {
            setSelectedIds(filteredTeachers.map(t => t.id));
        }
    };

    const handleBulkDelete = async () => {
        if (selectedIds.length === 0) return;
        if (!confirm(`Are you sure you want to remove ${selectedIds.length} selected teacher(s)?`)) return;
        
        try {
            await teachersApi.bulkDelete(selectedIds);
            setSelectedIds([]);
            fetchData();
        } catch (err) {
            const errorMsg = getErrorMessage(err);
            setError(errorMsg);
            console.error(err);
        }
    };



    // Filter Logic
    const filteredTeachers = teachers.filter(t => {
        if (filterName) {
            const search = filterName.toLowerCase();
            const matchesName = t.name.toLowerCase().includes(search);
            const matchesCode = (t.teacher_code || '').toLowerCase().includes(search);
            const matchesEmail = (t.email || '').toLowerCase().includes(search);
            return matchesName || matchesCode || matchesEmail;
        }
        return true;
    });

    // State for assignment form
    const [availableBatches, setAvailableBatches] = useState([]);

    const handleClassSelect = async (e) => {
        const semesterId = e.target.value;
        setAvailableBatches([]);
        if (semesterId) {
            try {
                const res = await semestersApi.getBatches(semesterId);
                setAvailableBatches(res.data);
            } catch (err) {
                console.error("Failed to fetch batches", err);
            }
        }
    };

    const handleAddAssignment = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);

        const data = {
            semester_id: parseInt(formData.get('semester_id')),
            subject_id: parseInt(formData.get('subject_id')),
            component_type: formData.get('component_type'),
        };

        const roomId = formData.get('room_id');
        if (roomId) data.room_id = parseInt(roomId);

        const parallelGroup = formData.get('parallel_lab_group');
        if (parallelGroup) data.parallel_lab_group = parallelGroup;

        try {
            await teachersApi.addAssignment(editingTeacher.id, data);

            // Refresh editingTeacher
            const updated = await teachersApi.getById(editingTeacher.id);
            setEditingTeacher(updated.data);

            // Refetch main list to update counts
            fetchData();

            e.target.reset();
            setAssignmentComponentType('theory');
            setAvailableBatches([]);
        } catch (err) {
            const errorMsg = getErrorMessage(err);
            setError(errorMsg);
        }
    };

    const handleRemoveAssignment = async (assignmentId) => {
        try {
            await teachersApi.removeAssignment(assignmentId);
            fetchData();
            // Refresh editingTeacher
            const updated = await teachersApi.getById(editingTeacher.id);
            setEditingTeacher(updated.data);
        } catch (err) {
            const errorMsg = getErrorMessage(err);
            setError(errorMsg);
        }
    };

    if (loading) {
        return <div className="loading"><div className="spinner"></div></div>;
    }

    return (
        <div className="crud-page">
            <div className="page-header">
                <div>
                    <h1>Teachers</h1>
                    <p>Manage faculty members and their subjects</p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button className="btn btn-primary" onClick={() => openModal()}>
                        <Plus size={18} />
                        Add Teacher
                    </button>
                    <button
                        className="btn"
                        onClick={() => { setShowImportModal(true); setImportStep('upload'); setImportResult(null); setImportFile(null); }}
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'linear-gradient(135deg, #0f4c81 0%, #1a73e8 100%)', color: 'white', border: 'none', borderRadius: '8px', padding: '8px 16px', cursor: 'pointer', fontWeight: 600 }}
                    >
                        <Upload size={18} />
                        Import Mappings
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
                    placeholder="Search by name or code..."
                    style={{ width: 'auto', minWidth: '200px', fontSize: '0.85rem', padding: '0.4rem 0.6rem' }}
                />

                {/* Department Filter - Integrated */}
                <select
                    className="form-select"
                    value={selectedDeptId || ''}
                    onChange={(e) => setSelectedDeptId(e.target.value)}
                    style={{ width: 'auto', minWidth: '180px', fontSize: '0.85rem' }}
                >
                    <option value="">All Departments</option>
                    {departments.map(d => (
                        <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                </select>

                {filterName && (
                    <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => setFilterName('')}
                        style={{ fontSize: '0.8rem' }}
                    >
                        Clear Search
                    </button>
                )}

                <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', cursor: 'pointer', marginRight: '10px', userSelect: 'none' }}>
                        <input 
                            type="checkbox" 
                            checked={filteredTeachers.length > 0 && selectedIds.length === filteredTeachers.length}
                            onChange={handleSelectAll}
                            style={{ width: '16px', height: '16px' }}
                        />
                        Select All Filtered
                    </label>
                    {selectedIds.length > 0 && (
                        <button className="btn btn-sm btn-danger" onClick={handleBulkDelete} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Trash2 size={14} /> Delete Selected ({selectedIds.length})
                        </button>
                    )}
                    <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)', whiteSpace: 'nowrap', marginLeft: '8px' }}>
                        {filteredTeachers.length} / {teachers.length} teachers
                    </span>
                </div>
            </div>

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            <div className="crud-grid">
                {filteredTeachers.map((teacher) => (
                    <div key={teacher.id} className={`crud-item ${!teacher.is_active ? 'inactive' : ''}`}>
                        <div className="crud-item-header">
                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                                <input 
                                    type="checkbox"
                                    checked={selectedIds.includes(teacher.id)}
                                    onChange={() => toggleSelection(teacher.id)}
                                    style={{ cursor: 'pointer', width: '18px', height: '18px', marginTop: '4px' }}
                                />
                                <div>
                                    <h3 className="crud-item-title">{teacher.name}</h3>
                                    {!teacher.is_active && <span className="badge badge-error" style={{ marginTop: '4px', display: 'inline-block' }}>Inactive</span>}
                                </div>
                            </div>
                            <div className="crud-item-actions">
                                <button className="btn btn-sm btn-secondary" onClick={() => openModal(teacher)}>
                                    <Edit2 size={14} />
                                </button>
                                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(teacher.id)}>
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </div>
                        <div className="crud-item-details">
                            {teacher.teacher_code && (
                                <span className="crud-item-detail" style={{ background: '#e0e7ff', color: '#3730a3', padding: '2px 6px', borderRadius: '4px', fontWeight: 'bold' }}>
                                    ID: {teacher.teacher_code}
                                </span>
                            )}
                            {teacher.email && (
                                <span className="crud-item-detail">
                                    <Mail size={14} /> {teacher.email}
                                </span>
                            )}
                            <span className="crud-item-detail">
                                <Clock size={14} /> Max {teacher.max_hours_per_week} hrs/week
                            </span>
                            <span className="crud-item-detail">
                                <Star size={14} /> {teacher.experience_years} yrs exp
                            </span>
                        </div>

                        {
                            teacher.class_assignments?.length > 0 && (
                                <div className="crud-item-assignments" style={{ marginTop: '10px', fontSize: '0.8rem', borderTop: '1px solid #f3f4f6', paddingTop: '8px' }}>
                                    <div style={{ fontWeight: '600', marginBottom: '4px', color: '#4b5563' }}>Teaching Classes:</div>
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                        {[...new Set(teacher.class_assignments.map(a => a.semester?.name))].map((name, i) => (
                                            <span key={i} style={{
                                                background: '#f3f4f6',
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                color: '#374151'
                                            }}>{name}</span>
                                        ))}
                                    </div>
                                </div>
                            )
                        }
                    </div>
                ))
                }
            </div >

            {
                teachers.length === 0 && (
                    <div className="empty-state">
                        <User size={48} />
                        <h3>No Teachers Yet</h3>
                        <p>Add your first teacher to get started</p>
                        <button className="btn btn-primary" onClick={() => openModal()}>
                            <Plus size={18} />
                            Add Teacher
                        </button>
                    </div>
                )
            }

            {/* Modal */}
            {
                showModal && (
                    <div className="modal-overlay" onClick={closeModal}>
                        <div className="modal" onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h2>{editingTeacher ? 'Edit Teacher' : 'Add Teacher'}</h2>
                                <button className="modal-close" onClick={closeModal}>
                                    <X size={20} />
                                </button>
                            </div>
                            <form onSubmit={handleSubmit}>
                                <div className="form-group">
                                    <label className="form-label">Name *</label>
                                    <input
                                        type="text"
                                        className="form-input"
                                        value={formData.name}
                                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                        required
                                    />
                                </div>
                                <div className="form-row">
                                    <div className="form-group">
                                        <label className="form-label">Teacher Code *</label>
                                        <input
                                            type="text"
                                            className="form-input"
                                            value={formData.teacher_code}
                                            onChange={(e) => setFormData({ ...formData, teacher_code: e.target.value })}
                                            placeholder="e.g. CSE001"
                                            required
                                        />
                                    </div>
                                </div>

                                <div className="form-group">
                                    <label className="form-label">Home Department</label>
                                    <select
                                        className="form-input"
                                        value={formData.dept_id || ''}
                                        onChange={(e) => setFormData({ ...formData, dept_id: e.target.value })}
                                    >
                                        <option value="">Select Department</option>
                                        {departments.map(d => (
                                            <option key={d.id} value={d.id}>{d.name}</option>
                                        ))}
                                    </select>
                                </div>

                                <div className="form-group" style={{ marginBottom: "1rem", padding: "10px", background: "var(--gray-50)", borderRadius: "8px", border: "1px solid var(--gray-200)" }}>
                                    <label className="form-label">Cross-Department Teaching</label>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginBottom: '8px' }}>
                                        <input
                                            type="checkbox"
                                            checked={formData.is_common_service_dept}
                                            onChange={(e) => setFormData({ ...formData, is_common_service_dept: e.target.checked })}
                                        />
                                        <span style={{ fontSize: "0.9rem", fontWeight: 500 }}>Common Service Department (Can teach any class)</span>
                                    </label>
                                    
                                    {!formData.is_common_service_dept && formData.dept_id && (
                                        <div style={{ marginTop: '0.75rem' }}>
                                            <label className="form-label" style={{ fontSize: '0.85rem', color: 'var(--gray-600)' }}>Allowed Additional Departments</label>
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '4px', padding: '12px', background: 'white', border: '1px solid var(--gray-200)', borderRadius: '6px' }}>
                                                {departments.filter(d => String(d.id) !== String(formData.dept_id)).map(d => (
                                                    <label key={d.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', cursor: 'pointer' }}>
                                                        <input 
                                                            type="checkbox" 
                                                            checked={formData.allowed_department_ids.includes(d.id)}
                                                            onChange={(e) => {
                                                                if (e.target.checked) {
                                                                    setFormData({...formData, allowed_department_ids: [...formData.allowed_department_ids, d.id]});
                                                                } else {
                                                                    setFormData({...formData, allowed_department_ids: formData.allowed_department_ids.filter(id => id !== d.id)});
                                                                }
                                                            }}
                                                        />
                                                        {d.name}
                                                    </label>
                                                ))}
                                            </div>
                                            <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '6px', fontStyle: 'italic' }}>
                                                Select departments this teacher is allowed to teach subjects in (e.g., Electives, basic sciences).
                                            </p>
                                        </div>
                                    )}
                                </div>

                                <div className="form-row">
                                    <div className="form-group">
                                        <label className="form-label">Email</label>
                                        <input
                                            type="email"
                                            className="form-input"
                                            value={formData.email}
                                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Phone</label>
                                        <input
                                            type="text"
                                            className="form-input"
                                            value={formData.phone}
                                            onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div className="form-row">
                                    <div className="form-group">
                                        <label className="form-label">Max Hours/Week</label>
                                        <input
                                            type="number"
                                            className="form-input"
                                            value={formData.max_hours_per_week}
                                            onChange={(e) => setFormData({ ...formData, max_hours_per_week: parseInt(e.target.value) })}
                                            min={1}
                                            max={40}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Experience (Years)</label>
                                        <input
                                            type="number"
                                            className="form-input"
                                            value={formData.experience_years}
                                            onChange={(e) => setFormData({ ...formData, experience_years: parseInt(e.target.value) })}
                                            min={0}
                                        />
                                    </div>
                                </div>

                                <div className="modal-actions">
                                    <button type="button" className="btn btn-secondary" onClick={closeModal}>
                                        Cancel
                                    </button>
                                    <button type="submit" className="btn btn-primary">
                                        {editingTeacher ? 'Update Info' : 'Create Teacher'}
                                    </button>
                                </div>
                            </form>

                            {
                                editingTeacher && (
                                    <div className="teacher-assignments-section" style={{ marginTop: '2rem', borderTop: '1px solid #eee', paddingTop: '1.5rem' }}>
                                        <h3>Class Assignments</h3>
                                        <p className="text-muted" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>
                                            Assign this teacher to specific subjects in specific classes.
                                        </p>

                                        <div className="assignments-list" style={{ marginBottom: '1.5rem' }}>
                                            {editingTeacher.class_assignments?.map(assignment => (
                                                <div key={assignment.id} className="assignment-item" style={{
                                                    display: 'flex',
                                                    justifyContent: 'space-between',
                                                    alignItems: 'center',
                                                    padding: '0.75rem',
                                                    background: '#f9fafb',
                                                    borderRadius: '0.5rem',
                                                    marginBottom: '0.5rem'
                                                }}>
                                                    <div>
                                                        <strong style={{ display: 'block' }}>{assignment.semester?.name}</strong>
                                                        <span style={{ fontSize: '0.8rem', color: '#666' }}>
                                                            {assignment.subject?.code} - {assignment.subject?.name} ({assignment.component_type}{assignment.room?.name ? `, ${assignment.room.name}` : ''})
                                                            {assignment.parallel_lab_group && (
                                                                <span style={{ marginLeft: '6px', fontSize: '0.7rem', background: '#ffedd5', color: '#9a3412', padding: '1px 4px', borderRadius: '4px' }}>
                                                                    ∥ {assignment.parallel_lab_group}
                                                                </span>
                                                            )}
                                                        </span>
                                                    </div>
                                                    <button
                                                        className="btn btn-sm btn-danger"
                                                        onClick={() => handleRemoveAssignment(assignment.id)}
                                                        title="Remove Assignment"
                                                    >
                                                        <Trash2 size={14} />
                                                    </button>
                                                </div>
                                            ))}
                                            {(!editingTeacher.class_assignments || editingTeacher.class_assignments.length === 0) && (
                                                <p className="text-muted" style={{ textAlign: 'center', padding: '1rem' }}>No classes assigned yet.</p>
                                            )}
                                        </div>

                                        <form onSubmit={handleAddAssignment} className="add-assignment-form" style={{
                                            display: 'grid',
                                            gridTemplateColumns: assignmentComponentType === 'lab'
                                                ? '1fr 1fr 1fr 1fr 1fr auto'
                                                : '1fr 1fr 1fr auto',
                                            gap: '0.5rem',
                                            alignItems: 'end'
                                        }}>
                                            <div className="form-group" style={{ marginBottom: 0 }}>
                                                <label className="form-label" style={{ fontSize: '0.75rem' }}>Class</label>
                                                <select
                                                    name="semester_id"
                                                    className="form-input"
                                                    required
                                                    onChange={handleClassSelect}
                                                >
                                                    <option value="">Select Class</option>
                                                    {semesters.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                                                </select>
                                            </div>

                                            <div className="form-group" style={{ marginBottom: 0 }}>
                                                <label className="form-label" style={{ fontSize: '0.75rem' }}>Subject</label>
                                                <select name="subject_id" className="form-input" required>
                                                    <option value="">Select Subject</option>
                                                    {subjects.map(s => (
                                                        <option key={s.id} value={s.id}>{s.code} - {s.name}</option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div className="form-group" style={{ marginBottom: 0 }}>
                                                <label className="form-label" style={{ fontSize: '0.75rem' }}>Type</label>
                                                <select
                                                    name="component_type"
                                                    className="form-input"
                                                    value={assignmentComponentType}
                                                    onChange={(event) => setAssignmentComponentType(event.target.value)}
                                                >
                                                    <option value="theory">Theory</option>
                                                    <option value="lab">Lab</option>
                                                    <option value="tutorial">Tutorial</option>
                                                </select>
                                            </div>
                                            {assignmentComponentType === 'lab' && (
                                                <div className="form-group" style={{ marginBottom: 0 }}>
                                                    <label className="form-label" style={{ fontSize: '0.75rem' }}>Lab Room</label>
                                                    <select name="room_id" className="form-input" required>
                                                        <option value="">Select Lab</option>
                                                        {rooms
                                                            .filter((room) => room.room_type === 'lab')
                                                            .map((room) => (
                                                                <option key={room.id} value={room.id}>
                                                                    {room.name}
                                                                </option>
                                                            ))}
                                                    </select>
                                                </div>
                                            )}
                                            {assignmentComponentType === 'lab' && (
                                                <div className="form-group" style={{ marginBottom: 0 }}>
                                                    <label className="form-label" style={{ fontSize: '0.75rem' }}>Parallel Group (Opt)</label>
                                                    <input
                                                        type="text"
                                                        name="parallel_lab_group"
                                                        className="form-input"
                                                        placeholder="e.g. G1"
                                                        title="Assign same group name to different lab subjects to schedule them in parallel"
                                                    />
                                                </div>
                                            )}
                                            <button type="submit" className="btn btn-primary" title="Add Assignment">
                                                <Plus size={18} />
                                            </button>
                                        </form>
                                    </div>
                                )
                            }
                        </div >
                    </div >
                )
            }
            {/* ── Teacher Mapping Import Modal ───────────────────── */}
            {showImportModal && (
                <div className="modal-overlay" onClick={() => setShowImportModal(false)}>
                    <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '950px', maxHeight: '90vh', overflow: 'auto' }}>
                        <div className="modal-header">
                            <h2 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                <Upload size={22} />
                                Bulk Teacher Mapping Import
                            </h2>
                            <button className="modal-close" onClick={() => setShowImportModal(false)}>
                                <X size={20} />
                            </button>
                        </div>

                        {/* Step 1: Upload */}
                        {importStep === 'upload' && (
                            <div style={{ padding: '20px' }}>
                                <div style={{
                                    background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                                    borderRadius: '12px',
                                    padding: '20px',
                                    border: '2px dashed #3b82f6',
                                    textAlign: 'center',
                                    marginBottom: '16px',
                                }}>
                                    <Upload size={40} style={{ color: '#2563eb', marginBottom: '10px' }} />
                                    <h3 style={{ margin: '0 0 8px 0', color: '#1e40af' }}>Upload Teacher Mapping File</h3>
                                    <p style={{ fontSize: '13px', color: '#1e3a5f', marginBottom: '8px' }}>
                                        Each row maps one teacher to a class + subject + component type.
                                    </p>
                                    <p style={{ fontSize: '12px', color: '#475569', marginBottom: '16px' }}>
                                        Columns: <strong>Teacher Name, Teacher Code, Department (or Home Department), Class Assigned, Subject Assigned, Type, Batch, Allowed Departments (Yes/No)</strong>
                                    </p>
                                    <input
                                        type="file"
                                        accept=".xlsx,.xls,.csv"
                                        id="teacher-import-file-input"
                                        style={{ display: 'none' }}
                                        onChange={(e) => {
                                            if (e.target.files?.[0]) setImportFile(e.target.files[0]);
                                        }}
                                    />
                                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
                                        <label
                                            htmlFor="teacher-import-file-input"
                                            className="btn btn-primary"
                                            style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                                        >
                                            <Upload size={16} />
                                            Choose File
                                        </label>
                                        <a
                                            href={teacherImportApi.getTemplateUrl()}
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
                                                    const res = await teacherImportApi.upload(importFile);
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
                                {importResult.schema_errors?.length > 0 && (
                                    <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', padding: '14px', marginBottom: '16px' }}>
                                        <h4 style={{ color: '#dc2626', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <XCircle size={18} /> Schema Errors
                                        </h4>
                                        {importResult.schema_errors.map((e, i) => (
                                            <div key={i} style={{ fontSize: '13px', color: '#b91c1c', padding: '4px 0' }}>{"\u2022"} {e}</div>
                                        ))}
                                    </div>
                                )}

                                {!importResult.schema_errors?.length && (
                                    <>
                                        {/* Summary Cards */}
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
                                                { label: 'New Teachers', value: importResult.rows?.filter(r => r.warnings?.some(w => w.includes('CREATE'))).length || 0, color: '#8b5cf6' },
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

                                        {/* Preview Table */}
                                        <div style={{ maxHeight: '400px', overflow: 'auto', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                                                <thead style={{ position: 'sticky', top: 0, background: '#1e293b', color: 'white', zIndex: 1 }}>
                                                    <tr>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Row</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Status</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Teacher</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Class</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Subject</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'center' }}>Type</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'center' }}>Batch</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Issues</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {importResult.rows?.map((row, idx) => {
                                                        const isInvalid = row.status === 'invalid';
                                                        const hasWarnings = row.warnings?.length > 0;
                                                        return (
                                                            <tr key={idx} style={{
                                                                background: isInvalid ? '#fef2f2' : hasWarnings ? '#fffbeb' : idx % 2 ? '#f8fafc' : 'white',
                                                                borderBottom: '1px solid #e2e8f0',
                                                            }}>
                                                                <td style={{ padding: '6px 10px', fontWeight: '600' }}>{row.row}</td>
                                                                <td style={{ padding: '6px 10px' }}>
                                                                    {isInvalid
                                                                        ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#dc2626', fontWeight: '600' }}><XCircle size={14} /> Invalid</span>
                                                                        : <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#16a34a', fontWeight: '600' }}><CheckCircle size={14} /> Valid</span>
                                                                    }
                                                                </td>
                                                                <td style={{ padding: '6px 10px' }}>
                                                                    <div style={{ fontWeight: '600' }}>{row.data?.['Teacher Code'] || '\u2014'}</div>
                                                                    <div style={{ fontSize: '11px', color: '#64748b' }}>{row.data?.['Teacher Name'] || ''}</div>
                                                                </td>
                                                                <td style={{ padding: '6px 10px', fontFamily: 'monospace', fontWeight: '600' }}>{row.data?.['Class Assigned'] || '\u2014'}</td>
                                                                <td style={{ padding: '6px 10px' }}>{row.data?.['Subject Assigned'] || '\u2014'}</td>
                                                                <td style={{ padding: '6px 10px', textAlign: 'center' }}>
                                                                    <span style={{
                                                                        padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: '600',
                                                                        background: (row.data?.['Type'] || '').toLowerCase() === 'lab' ? '#dcfce7' : '#dbeafe',
                                                                        color: (row.data?.['Type'] || '').toLowerCase() === 'lab' ? '#166534' : '#1e40af',
                                                                    }}>{row.data?.['Type'] || 'Theory'}</span>
                                                                </td>
                                                                <td style={{ padding: '6px 10px', textAlign: 'center', fontWeight: '600' }}>{row.data?.['Batch'] || 'All'}</td>
                                                                <td style={{ padding: '6px 10px', fontSize: '11px' }}>
                                                                    {row.errors?.map((e, i) => <div key={i} style={{ color: '#dc2626' }}>{"\u2717"} {e}</div>)}
                                                                    {row.warnings?.map((w, i) => <div key={`w${i}`} style={{ color: '#d97706' }}>{"\u26a0"} {w}</div>)}
                                                                </td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>

                                        {/* Actions */}
                                        <div className="modal-actions" style={{ marginTop: '16px' }}>
                                            <button className="btn btn-secondary" onClick={() => { setImportStep('upload'); setImportResult(null); }}>Back</button>
                                            <button className="btn btn-secondary" onClick={() => setShowImportModal(false)}>Cancel</button>
                                            {(importResult.total_rows - importResult.failed > 0) && (
                                                <button
                                                    className="btn btn-primary"
                                                    disabled={importCommitting}
                                                    style={{ background: importResult.failed > 0 ? 'linear-gradient(135deg, #f59e0b, #d97706)' : 'linear-gradient(135deg, #0f4c81, #1a73e8)', border: 'none' }}
                                                    onClick={async () => {
                                                        setImportCommitting(true);
                                                        setError(null);
                                                        try {
                                                            const res = await teacherImportApi.commit(importResult.batch_id);
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
                                                    {importCommitting
                                                        ? <><Loader2 size={16} className="spin" /> Importing...</>
                                                        : <><CheckCircle size={16} /> {importResult.failed > 0 ? `Import Valid Only (${importResult.total_rows - importResult.failed})` : `Commit All (${importResult.total_rows} mappings)`}</>
                                                    }
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
                                    textAlign: 'center', padding: '30px',
                                    background: 'linear-gradient(135deg, #eff6ff, #dbeafe)',
                                    borderRadius: '12px', marginBottom: '20px',
                                }}>
                                    <CheckCircle size={48} style={{ color: '#2563eb', marginBottom: '12px' }} />
                                    <h3 style={{ color: '#1e40af', margin: '0 0 8px 0' }}>Mapping Import Successful!</h3>
                                    <p style={{ color: '#1e3a5f', fontSize: '14px', margin: 0 }}>
                                        Teacher assignments are now active and ready for timetable generation.
                                    </p>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '20px' }}>
                                    {[
                                        { label: 'New Teachers', value: importResult.created_teachers, color: '#8b5cf6', icon: '+' },
                                        { label: 'Mappings Created', value: importResult.created_mappings, color: '#16a34a', icon: '\u2713' },
                                        { label: 'Duplicates Skipped', value: importResult.skipped_duplicates, color: '#f59e0b', icon: '\u2014' },
                                    ].map(({ label, value, color, icon }) => (
                                        <div key={label} style={{
                                            textAlign: 'center', padding: '14px', borderRadius: '10px',
                                            background: `${color}10`, border: `2px solid ${color}30`,
                                        }}>
                                            <div style={{ fontSize: '28px', fontWeight: '800', color }}>{icon} {value}</div>
                                            <div style={{ fontSize: '12px', color: '#64748b', fontWeight: '600' }}>{label}</div>
                                        </div>
                                    ))}
                                </div>

                                {importResult.health_check && (
                                    <div style={{
                                        background: importResult.health_check.all_clear ? '#f0fdf4' : '#fffbeb',
                                        border: `1px solid ${importResult.health_check.all_clear ? '#86efac' : '#fde68a'}`,
                                        borderRadius: '8px', padding: '14px', marginBottom: '16px',
                                    }}>
                                        <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            {importResult.health_check.all_clear ? <CheckCircle size={16} style={{ color: '#16a34a' }} /> : <AlertCircle size={16} style={{ color: '#f59e0b' }} />}
                                            Post-Import Health Check
                                        </h4>
                                        <div style={{ fontSize: '13px', color: '#475569' }}>
                                            <div>Total Active Teachers: <strong>{importResult.health_check.total_teachers}</strong></div>
                                            <div>Total Mappings: <strong>{importResult.health_check.total_mappings}</strong></div>
                                        </div>
                                        {importResult.health_check.warnings?.map((w, i) => (
                                            <div key={i} style={{ fontSize: '12px', color: '#d97706', marginTop: '4px' }}>{"\u26a0"} {w}</div>
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
        </div >
    );
}
