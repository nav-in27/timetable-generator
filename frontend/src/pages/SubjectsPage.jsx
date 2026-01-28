/**
 * Subjects Management Page
 * CRUD operations for subjects
 */
import { useEffect, useState } from 'react';
import { Plus, Edit2, Trash2, X, BookOpen, Clock, AlertCircle } from 'lucide-react';
import { subjectsApi } from '../services/api';
import './CrudPage.css';

export default function SubjectsPage() {
    const [subjects, setSubjects] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingSubject, setEditingSubject] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        code: '',
        weekly_hours: 3,
        subject_type: 'theory',
        consecutive_slots: 1,
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const res = await subjectsApi.getAll();
            setSubjects(res.data);
        } catch (err) {
            setError('Failed to load subjects');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const openModal = (subject = null) => {
        if (subject) {
            setEditingSubject(subject);
            setFormData({
                name: subject.name,
                code: subject.code,
                weekly_hours: subject.weekly_hours,
                subject_type: subject.subject_type,
                consecutive_slots: subject.consecutive_slots,
            });
        } else {
            setEditingSubject(null);
            setFormData({
                name: '',
                code: '',
                weekly_hours: 3,
                subject_type: 'theory',
                consecutive_slots: 1,
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
        try {
            if (editingSubject) {
                await subjectsApi.update(editingSubject.id, formData);
            } else {
                await subjectsApi.create(formData);
            }
            fetchData();
            closeModal();
        } catch (err) {
            setError('Failed to save subject');
            console.error(err);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Are you sure you want to delete this subject?')) return;
        try {
            await subjectsApi.delete(id);
            fetchData();
        } catch (err) {
            setError('Failed to delete subject');
            console.error(err);
        }
    };

    if (loading) {
        return <div className="loading"><div className="spinner"></div></div>;
    }

    return (
        <div className="crud-page">
            <div className="page-header">
                <div>
                    <h1>Subjects</h1>
                    <p>Manage courses and their configurations</p>
                </div>
                <button className="btn btn-primary" onClick={() => openModal()}>
                    <Plus size={18} />
                    Add Subject
                </button>
            </div>

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            <div className="crud-grid">
                {subjects.map((subject) => (
                    <div key={subject.id} className="crud-item">
                        <div className="crud-item-header">
                            <div>
                                <h3 className="crud-item-title">{subject.name}</h3>
                                <span className="text-sm text-muted">{subject.code}</span>
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
                        <div className="crud-item-details">
                            <span className="crud-item-detail">
                                <Clock size={14} /> {subject.weekly_hours} hrs/week
                            </span>
                            <span className={`badge badge-${subject.subject_type}`}>
                                {subject.subject_type}
                            </span>
                            {subject.subject_type === 'lab' && (
                                <span className="crud-item-detail">
                                    {subject.consecutive_slots} consecutive slots
                                </span>
                            )}
                        </div>
                    </div>
                ))}
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
                    <div className="modal" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>{editingSubject ? 'Edit Subject' : 'Add Subject'}</h2>
                            <button className="modal-close" onClick={closeModal}>
                                <X size={20} />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit}>
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
                                    <label className="form-label">Weekly Hours</label>
                                    <input
                                        type="number"
                                        className="form-input"
                                        value={formData.weekly_hours}
                                        onChange={(e) => setFormData({ ...formData, weekly_hours: parseInt(e.target.value) })}
                                        min={1}
                                        max={10}
                                    />
                                </div>
                            </div>
                            <div className="form-group">
                                <label className="form-label">Type</label>
                                <div className="type-selector">
                                    {['theory', 'lab', 'tutorial'].map((type) => (
                                        <button
                                            key={type}
                                            type="button"
                                            className={`type-btn ${formData.subject_type === type ? 'active' : ''}`}
                                            onClick={() => setFormData({
                                                ...formData,
                                                subject_type: type,
                                                consecutive_slots: type === 'lab' ? 2 : 1
                                            })}
                                        >
                                            {type.charAt(0).toUpperCase() + type.slice(1)}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            {formData.subject_type === 'lab' && (
                                <div className="form-group">
                                    <label className="form-label">Consecutive Slots</label>
                                    <input
                                        type="number"
                                        className="form-input"
                                        value={formData.consecutive_slots}
                                        onChange={(e) => setFormData({ ...formData, consecutive_slots: parseInt(e.target.value) })}
                                        min={1}
                                        max={4}
                                    />
                                    <p className="text-xs text-muted mt-1">Number of consecutive periods for lab sessions</p>
                                </div>
                            )}
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
        </div>
    );
}
