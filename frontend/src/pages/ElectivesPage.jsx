/**
 * Elective Baskets Management Page
 * Manage groups of subjects that share common scheduling slots.
 */
import { useEffect, useState } from 'react';
import { Plus, Edit2, Trash2, X, Layers, BookOpen, AlertCircle, Save } from 'lucide-react';
import api, { subjectsApi, semestersApi } from '../services/api'; // Extended with elective API
import './CrudPage.css';

// API for Elective Baskets
const electivesApi = {
    getAll: () => api.get('/elective-baskets/'),
    create: (data) => api.post('/elective-baskets/', data),
    update: (id, data) => api.put(`/elective-baskets/${id}`, data),
    delete: (id) => api.delete(`/elective-baskets/${id}`),
};

export default function ElectivesPage() {
    const [baskets, setBaskets] = useState([]);
    const [subjects, setSubjects] = useState([]);
    const [semesters, setSemesters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingBasket, setEditingBasket] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        code: '',
        semester_number: 1,
        theory_hours_per_week: 3,
        lab_hours_per_week: 0,
        tutorial_hours_per_week: 0,
        semester_ids: [],
        subject_ids: []
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [basketRes, subjRes, semRes] = await Promise.all([
                electivesApi.getAll(),
                subjectsApi.getAll(),
                semestersApi.getAll()
            ]);
            setBaskets(basketRes.data);
            setSubjects(subjRes.data);
            setSemesters(semRes.data);
        } catch (err) {
            setError('Failed to load data');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const openModal = (basket = null) => {
        if (basket) {
            setEditingBasket(basket);
            setFormData({
                name: basket.name,
                code: basket.code,
                semester_number: basket.semester_number,
                theory_hours_per_week: basket.theory_hours_per_week,
                lab_hours_per_week: basket.lab_hours_per_week,
                tutorial_hours_per_week: basket.tutorial_hours_per_week,
                semester_ids: basket.participating_semesters ? basket.participating_semesters.map(s => s.id) : [],
                subject_ids: subjects.filter(s => s.elective_basket_id === basket.id).map(s => s.id)
            });
        } else {
            setEditingBasket(null);
            setFormData({
                name: '',
                code: '',
                semester_number: 3,
                theory_hours_per_week: 3,
                lab_hours_per_week: 0,
                tutorial_hours_per_week: 0,
                semester_ids: [],
                subject_ids: []
            });
        }
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingBasket(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            console.log('Submitting elective basket:', formData);
            if (editingBasket) {
                await electivesApi.update(editingBasket.id, formData);
            } else {
                await electivesApi.create(formData);
            }
            closeModal();
            await fetchData();
        } catch (err) {
            console.error('Elective basket save error:', err);
            const errorDetail = err.response?.data?.detail || err.message || 'Failed to save basket';
            setError(typeof errorDetail === 'object' ? JSON.stringify(errorDetail) : errorDetail);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Delete this elective basket? Subjects will be unlinked, not deleted.')) return;
        try {
            await electivesApi.delete(id);
            fetchData();
        } catch (err) {
            setError('Failed to delete basket');
        }
    };

    const getAvailableSubjects = () => {
        // Subjects that are NOT assigned to a basket OR assigned to THIS basket
        return subjects.filter(s =>
            !s.elective_basket_id ||
            (editingBasket && s.elective_basket_id === editingBasket.id)
        );
    };

    // Filter semesters by selected number
    const availableSemesters = semesters.filter(s => s.semester_number === formData.semester_number);

    if (loading) return <div className="loading"><div className="spinner"></div></div>;

    return (
        <div className="crud-page">
            <div className="page-header">
                <div>
                    <h1>Elective Baskets</h1>
                    <p>Manage common slot groups for electives</p>
                </div>
                <button className="btn btn-primary" onClick={() => openModal()}>
                    <Plus size={18} />
                    Create Basket
                </button>
            </div>

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                    <button onClick={() => setError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none' }}><X size={14} /></button>
                </div>
            )}

            <div className="crud-grid">
                {baskets.map(basket => (
                    <div key={basket.id} className="crud-item" style={{ borderLeft: '4px solid #f59e0b' }}>
                        <div className="crud-item-header">
                            <div>
                                <h3 className="crud-item-title">{basket.name}</h3>
                                <div className="flex gap-2 items-center text-xs text-muted">
                                    <span style={{ fontWeight: 'bold' }}>{basket.code}</span>
                                    <span>•</span>
                                    <span>Sem {basket.semester_number}</span>
                                </div>
                            </div>
                            <div className="crud-item-actions">
                                <button className="btn btn-sm btn-secondary" onClick={() => openModal(basket)}><Edit2 size={14} /></button>
                                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(basket.id)}><Trash2 size={14} /></button>
                            </div>
                        </div>

                        <div style={{ marginTop: '12px', fontSize: '13px' }}>
                            <div style={{ display: 'flex', gap: '12px', marginBottom: '8px' }}>
                                <span className="badge" style={{ background: '#eff6ff', color: '#2563eb' }}>
                                    {basket.theory_hours_per_week}h Theory
                                </span>
                                {basket.lab_hours_per_week > 0 && (
                                    <span className="badge" style={{ background: '#f0fdf4', color: '#16a34a' }}>
                                        {basket.lab_hours_per_week}h Lab
                                    </span>
                                )}
                            </div>

                            <div className="text-muted mb-2">
                                <strong>Subjects:</strong>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
                                    {subjects.filter(s => s.elective_basket_id === basket.id).map(s => (
                                        <span key={s.id} style={{
                                            background: '#f3f4f6', padding: '2px 6px', borderRadius: '4px', fontSize: '11px'
                                        }}>
                                            {s.code}
                                        </span>
                                    ))}
                                    {subjects.filter(s => s.elective_basket_id === basket.id).length === 0 && (
                                        <span style={{ fontStyle: 'italic' }}>No subjects linked</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {baskets.length === 0 && (
                <div className="empty-state">
                    <Layers size={48} />
                    <h3>No Elective Baskets</h3>
                    <p>Create a basket to group electives for common scheduling</p>
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal" onClick={e => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>{editingBasket ? 'Edit Basket' : 'New Elective Basket'}</h2>
                            <button className="modal-close" onClick={closeModal}><X size={20} /></button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Basket Name *</label>
                                    <input className="form-input" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} placeholder="e.g. Open Elective 1" />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Code *</label>
                                    <input className="form-input" required value={formData.code} onChange={e => setFormData({ ...formData, code: e.target.value })} placeholder="e.g. OE-1" />
                                </div>
                            </div>

                            <div className="form-group">
                                <label className="form-label">Semester Number *</label>
                                <select className="form-select" value={formData.semester_number} onChange={e => setFormData({ ...formData, semester_number: parseInt(e.target.value) })}>
                                    {[1, 2, 3, 4, 5, 6, 7, 8].map(n => <option key={n} value={n}>{n}</option>)}
                                </select>
                            </div>

                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Theory Hours</label>
                                    <input type="number" className="form-input" min="0" value={formData.theory_hours_per_week} onChange={e => setFormData({ ...formData, theory_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Lab Hours</label>
                                    <input type="number" className="form-input" min="0" value={formData.lab_hours_per_week} onChange={e => setFormData({ ...formData, lab_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                            </div>

                            <div className="form-group">
                                <label className="form-label">Add Subjects to Basket</label>
                                <div style={{ maxHeight: '150px', overflowY: 'auto', border: '1px solid #eee', padding: '8px', borderRadius: '6px' }}>
                                    {getAvailableSubjects().map(s => (
                                        <label key={s.id} style={{ display: 'block', marginBottom: '4px', fontSize: '13px', cursor: 'pointer' }}>
                                            <input
                                                type="checkbox"
                                                checked={formData.subject_ids.includes(s.id)}
                                                onChange={e => {
                                                    const ids = new Set(formData.subject_ids);
                                                    if (e.target.checked) ids.add(s.id); else ids.delete(s.id);
                                                    setFormData({ ...formData, subject_ids: Array.from(ids) });
                                                }}
                                                style={{ marginRight: '8px' }}
                                            />
                                            {s.name} ({s.code})
                                        </label>
                                    ))}
                                    {getAvailableSubjects().length === 0 && <span className="text-muted text-xs">No available subjects</span>}
                                </div>
                            </div>

                            <div className="form-group">
                                <label className="form-label">Participating Classes (Sem {formData.semester_number})</label>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                                    {availableSemesters.map(s => (
                                        <label key={s.id} style={{
                                            padding: '4px 8px', borderRadius: '4px', border: formData.semester_ids.includes(s.id) ? '1px solid #2563eb' : '1px solid #ddd',
                                            background: formData.semester_ids.includes(s.id) ? '#eff6ff' : 'white', cursor: 'pointer', fontSize: '12px'
                                        }}>
                                            <input
                                                type="checkbox"
                                                style={{ display: 'none' }}
                                                checked={formData.semester_ids.includes(s.id)}
                                                onChange={e => {
                                                    const ids = new Set(formData.semester_ids);
                                                    if (e.target.checked) ids.add(s.id); else ids.delete(s.id);
                                                    setFormData({ ...formData, semester_ids: Array.from(ids) });
                                                }}
                                            />
                                            {s.name}
                                        </label>
                                    ))}
                                </div>
                            </div>

                            <div className="modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={closeModal}>Cancel</button>
                                <button type="submit" className="btn btn-primary">Save Basket</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
