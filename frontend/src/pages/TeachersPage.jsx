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
    BookOpen,
    AlertCircle,
} from 'lucide-react';
import { teachersApi, subjectsApi, semestersApi } from '../services/api';
import './CrudPage.css';

export default function TeachersPage() {
    const [teachers, setTeachers] = useState([]);
    const [subjects, setSubjects] = useState([]);
    const [semesters, setSemesters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingTeacher, setEditingTeacher] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        email: '',
        phone: '',
        max_hours_per_week: 20,
        experience_years: 1,
        experience_score: 0.5,
        available_days: '0,1,2,3,4',
        subject_ids: [],
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [teachersRes, subjectsRes, semestersRes] = await Promise.all([
                teachersApi.getAll(true),
                subjectsApi.getAll(),
                semestersApi.getAll(),
            ]);
            setTeachers(teachersRes.data);
            setSubjects(subjectsRes.data);
            setSemesters(semestersRes.data);
        } catch (err) {
            setError('Failed to load data');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const openModal = (teacher = null) => {
        if (teacher) {
            setEditingTeacher(teacher);
            setFormData({
                name: teacher.name,
                email: teacher.email || '',
                phone: teacher.phone || '',
                max_hours_per_week: teacher.max_hours_per_week,
                experience_years: teacher.experience_years,
                experience_score: teacher.experience_score,
                available_days: teacher.available_days,
                subject_ids: teacher.subjects?.map(s => s.id) || [],
            });
        } else {
            setEditingTeacher(null);
            setFormData({
                name: '',
                email: '',
                phone: '',
                max_hours_per_week: 20,
                experience_years: 1,
                experience_score: 0.5,
                available_days: '0,1,2,3,4',
                subject_ids: [],
            });
        }
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingTeacher(null);
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
            if (editingTeacher) {
                await teachersApi.update(editingTeacher.id, formData);
            } else {
                await teachersApi.create(formData);
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
        } catch (err) {
            const errorMsg = getErrorMessage(err);
            setError(errorMsg);
            console.error(err);
        }
    };

    const toggleSubject = (subjectId) => {
        setFormData(prev => ({
            ...prev,
            subject_ids: prev.subject_ids.includes(subjectId)
                ? prev.subject_ids.filter(id => id !== subjectId)
                : [...prev.subject_ids, subjectId],
        }));
    };

    const handleAddAssignment = async (e) => {
        e.preventDefault();
        const assignmentData = {
            teacher_id: editingTeacher.id,
            semester_id: parseInt(e.target.semester_id.value),
            subject_id: parseInt(e.target.subject_id.value),
            component_type: e.target.component_type.value,
        };
        try {
            await teachersApi.addAssignment(editingTeacher.id, assignmentData);
            fetchData();
            // Refresh editingTeacher to show new assignment
            const updated = await teachersApi.getById(editingTeacher.id);
            setEditingTeacher(updated.data);
            e.target.reset();
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
                <button className="btn btn-primary" onClick={() => openModal()}>
                    <Plus size={18} />
                    Add Teacher
                </button>
            </div>

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            <div className="crud-grid">
                {teachers.map((teacher) => (
                    <div key={teacher.id} className={`crud-item ${!teacher.is_active ? 'inactive' : ''}`}>
                        <div className="crud-item-header">
                            <div>
                                <h3 className="crud-item-title">{teacher.name}</h3>
                                {!teacher.is_active && <span className="badge badge-error">Inactive</span>}
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
                        {teacher.subjects?.length > 0 && (
                            <div className="crud-item-tags">
                                {teacher.subjects.map(s => (
                                    <span key={s.id} className="tag">{s.code}</span>
                                ))}
                            </div>
                        )}
                        {teacher.class_assignments?.length > 0 && (
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
                        )}
                    </div>
                ))}
            </div>

            {teachers.length === 0 && (
                <div className="empty-state">
                    <User size={48} />
                    <h3>No Teachers Yet</h3>
                    <p>Add your first teacher to get started</p>
                    <button className="btn btn-primary" onClick={() => openModal()}>
                        <Plus size={18} />
                        Add Teacher
                    </button>
                </div>
            )}

            {/* Modal */}
            {showModal && (
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
                            <div className="form-group">
                                <label className="form-label">Experience Score (0-1)</label>
                                <input
                                    type="number"
                                    className="form-input"
                                    value={formData.experience_score}
                                    onChange={(e) => setFormData({ ...formData, experience_score: parseFloat(e.target.value) })}
                                    min={0}
                                    max={1}
                                    step={0.1}
                                />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Subjects (Click to toggle)</label>
                                <div className="subject-selector">
                                    {subjects.map((subject) => (
                                        <button
                                            key={subject.id}
                                            type="button"
                                            className={`subject-chip ${formData.subject_ids.includes(subject.id) ? 'selected' : ''}`}
                                            onClick={() => toggleSubject(subject.id)}
                                        >
                                            <BookOpen size={14} />
                                            {subject.code}
                                        </button>
                                    ))}
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

                        {editingTeacher && (
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
                                                    {assignment.subject?.code} - {assignment.subject?.name} ({assignment.component_type})
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
                                    gridTemplateColumns: '1fr 1fr 1fr auto',
                                    gap: '0.5rem',
                                    alignItems: 'end'
                                }}>
                                    <div className="form-group" style={{ marginBottom: 0 }}>
                                        <label className="form-label" style={{ fontSize: '0.75rem' }}>Class</label>
                                        <select name="semester_id" className="form-input" required>
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
                                        <select name="component_type" className="form-input">
                                            <option value="theory">Theory</option>
                                            <option value="lab">Lab</option>
                                            <option value="tutorial">Tutorial</option>
                                        </select>
                                    </div>
                                    <button type="submit" className="btn btn-primary" title="Add Assignment">
                                        <Plus size={18} />
                                    </button>
                                </form>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
