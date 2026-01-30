/**
 * Semesters/Classes Management Page
 * CRUD operations for classes
 */
import { useEffect, useState } from 'react';
import { Plus, Edit2, Trash2, X, GraduationCap, Users, AlertCircle } from 'lucide-react';
import { semestersApi } from '../services/api';
import './CrudPage.css';

export default function SemestersPage() {
    const [semesters, setSemesters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingSemester, setEditingSemester] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        code: '',
        year: 2,
        semester_number: 3,
        section: 'A',
        student_count: 60,
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const res = await semestersApi.getAll();
            setSemesters(res.data);
        } catch (err) {
            setError('Failed to load classes');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const openModal = (semester = null) => {
        if (semester) {
            setEditingSemester(semester);
            setFormData({
                name: semester.name,
                code: semester.code,
                year: semester.year,
                semester_number: semester.semester_number || (semester.year * 2 - 1),
                section: semester.section,
                student_count: semester.student_count,
            });
        } else {
            setEditingSemester(null);
            setFormData({
                name: '',
                code: '',
                year: 2,
                semester_number: 3,
                section: 'A',
                student_count: 60,
            });
        }
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingSemester(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            if (editingSemester) {
                await semestersApi.update(editingSemester.id, formData);
            } else {
                await semestersApi.create(formData);
            }
            fetchData();
            closeModal();
        } catch (err) {
            setError('Failed to save class');
            console.error(err);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Are you sure you want to delete this class?')) return;
        try {
            await semestersApi.delete(id);
            fetchData();
        } catch (err) {
            setError('Failed to delete class');
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
                    <h1>Classes (Semesters)</h1>
                    <p>Manage student batches and sections</p>
                </div>
                <button className="btn btn-primary" onClick={() => openModal()}>
                    <Plus size={18} />
                    Add Class
                </button>
            </div>

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            <div className="crud-grid">
                {semesters.map((semester) => (
                    <div key={semester.id} className="crud-item">
                        <div className="crud-item-header">
                            <div>
                                <h3 className="crud-item-title">{semester.name}</h3>
                                <span className="badge badge-info">{semester.code}</span>
                                <span className="badge badge-success" style={{ marginLeft: '8px' }}>Sem {semester.semester_number || '?'}</span>
                            </div>
                            <div className="crud-item-actions">
                                <button className="btn btn-sm btn-secondary" onClick={() => openModal(semester)}>
                                    <Edit2 size={14} />
                                </button>
                                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(semester.id)}>
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </div>
                        <div className="crud-item-details">
                            <span className="crud-item-detail">
                                <GraduationCap size={14} /> Year {semester.year}
                            </span>
                            <span className="crud-item-detail">
                                Section {semester.section}
                            </span>
                            <span className="crud-item-detail">
                                <Users size={14} /> {semester.student_count} students
                            </span>
                        </div>
                    </div>
                ))}
            </div>

            {semesters.length === 0 && (
                <div className="empty-state">
                    <GraduationCap size={48} />
                    <h3>No Classes Yet</h3>
                    <p>Add your first class to get started</p>
                    <button className="btn btn-primary" onClick={() => openModal()}>
                        <Plus size={18} />
                        Add Class
                    </button>
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>{editingSemester ? 'Edit Class' : 'Add Class'}</h2>
                            <button className="modal-close" onClick={closeModal}>
                                <X size={20} />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div className="form-group">
                                <label className="form-label">Class Name *</label>
                                <input
                                    type="text"
                                    className="form-input"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    required
                                    placeholder="e.g., 3rd Semester - Section A"
                                />
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Code *</label>
                                    <input
                                        type="text"
                                        className="form-input"
                                        value={formData.code}
                                        onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                        required
                                        placeholder="e.g., CS3A"
                                    />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Year</label>
                                    <select
                                        className="form-select"
                                        value={formData.year}
                                        onChange={(e) => setFormData({ ...formData, year: parseInt(e.target.value) })}
                                    >
                                        {[1, 2, 3, 4, 5, 6].map((y) => (
                                            <option key={y} value={y}>Year {y}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Semester Number *</label>
                                    <select
                                        className="form-select"
                                        value={formData.semester_number}
                                        onChange={(e) => setFormData({ ...formData, semester_number: parseInt(e.target.value) })}
                                    >
                                        {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
                                            <option key={s} value={s}>Semester {s}</option>
                                        ))}
                                    </select>
                                    <small style={{ color: '#666', fontSize: '12px' }}>This determines which semester subjects can be assigned</small>
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Section</label>
                                    <input
                                        type="text"
                                        className="form-input"
                                        value={formData.section}
                                        onChange={(e) => setFormData({ ...formData, section: e.target.value })}
                                        maxLength={5}
                                        placeholder="A"
                                    />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Student Count</label>
                                    <input
                                        type="number"
                                        className="form-input"
                                        value={formData.student_count}
                                        onChange={(e) => setFormData({ ...formData, student_count: parseInt(e.target.value) })}
                                        min={1}
                                        max={200}
                                    />
                                </div>
                            </div>
                            <div className="modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={closeModal}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    {editingSemester ? 'Update' : 'Create'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
