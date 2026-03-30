/**
 * Structured Composite Baskets Management Page
 * Handles multi-department, mixed lab/theory blocks.
 * Supports class-level (semester) targeting within selected departments.
 */
import { useEffect, useState, useCallback } from 'react';
import { Plus, Edit2, Trash2, X, Layers, AlertCircle, Loader2 } from 'lucide-react';
import { structuredCompositeBasketsApi, subjectsApi, departmentsApi, semestersApi } from '../services/api';
import './CrudPage.css';

const INITIAL_FORM = {
    name: '',
    semester: 1,
    theory_hours: 3,
    lab_hours: 2,
    continuous_lab_periods: 2,
    same_slot_across_departments: true,
    allow_lab_parallel: true,
    department_ids: [],
    class_ids: [],
    subject_ids: []
};

export default function StructuredBasketsPage() {
    const [baskets, setBaskets] = useState([]);
    const [subjects, setSubjects] = useState([]);
    const [departments, setDepartments] = useState([]);
    const [deptClasses, setDeptClasses] = useState([]); // classes for selected departments
    const [classesLoading, setClassesLoading] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingBasket, setEditingBasket] = useState(null);
    const [formData, setFormData] = useState({ ...INITIAL_FORM });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [basketRes, subjRes, deptRes] = await Promise.all([
                structuredCompositeBasketsApi.getAll(),
                subjectsApi.getAll(),
                departmentsApi.getAll()
            ]);
            setBaskets(basketRes.data);
            setSubjects(subjRes.data);
            setDepartments(deptRes.data);
        } catch (err) {
            setError('Failed to load data');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    // Fetch classes whenever department selection changes
    const fetchClassesForDepartments = useCallback(async (deptIds) => {
        if (!deptIds || deptIds.length === 0) {
            setDeptClasses([]);
            return;
        }
        setClassesLoading(true);
        try {
            const allClasses = [];
            for (const deptId of deptIds) {
                const res = await semestersApi.getAll({ deptId });
                if (res.data) {
                    allClasses.push(...res.data);
                }
            }
            // Deduplicate by id
            const seen = new Set();
            const unique = allClasses.filter(c => {
                if (seen.has(c.id)) return false;
                seen.add(c.id);
                return true;
            });
            setDeptClasses(unique);
        } catch (err) {
            console.error('Failed to fetch classes:', err);
            setDeptClasses([]);
        } finally {
            setClassesLoading(false);
        }
    }, []);

    const openModal = async (basket = null) => {
        if (basket) {
            setEditingBasket(basket);
            const deptIds = basket.departments_involved ? basket.departments_involved.map(d => d.id) : [];
            const classIds = basket.selected_classes ? basket.selected_classes.map(c => c.id) : [];
            setFormData({
                name: basket.name || '',
                semester: basket.semester,
                theory_hours: basket.theory_hours ?? 3,
                lab_hours: basket.lab_hours ?? 2,
                continuous_lab_periods: basket.continuous_lab_periods ?? 2,
                same_slot_across_departments: basket.same_slot_across_departments,
                allow_lab_parallel: basket.allow_lab_parallel,
                department_ids: deptIds,
                class_ids: classIds,
                subject_ids: basket.linked_subjects ? basket.linked_subjects.map(s => s.id) : []
            });
            // Load classes for the selected departments
            await fetchClassesForDepartments(deptIds);
        } else {
            setEditingBasket(null);
            setFormData({ ...INITIAL_FORM });
            setDeptClasses([]);
        }
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingBasket(null);
        setDeptClasses([]);
    };

    const handleDepartmentChange = async (deptId, checked) => {
        const ids = new Set(formData.department_ids);
        if (checked) ids.add(deptId); else ids.delete(deptId);
        const newDeptIds = Array.from(ids);

        // Remove class_ids that no longer belong to selected departments
        const removedDeptIds = formData.department_ids.filter(id => !newDeptIds.includes(id));
        let newClassIds = formData.class_ids;
        if (removedDeptIds.length > 0) {
            // We need to check which classes belonged to removed departments
            const removedClassIds = deptClasses
                .filter(c => removedDeptIds.includes(c.dept_id))
                .map(c => c.id);
            newClassIds = newClassIds.filter(id => !removedClassIds.includes(id));
        }

        setFormData(prev => ({
            ...prev,
            department_ids: newDeptIds,
            class_ids: newClassIds
        }));

        // Fetch classes for new department selection
        await fetchClassesForDepartments(newDeptIds);
    };

    const handleClassChange = (classId, checked) => {
        const ids = new Set(formData.class_ids);
        if (checked) ids.add(classId); else ids.delete(classId);
        setFormData(prev => ({ ...prev, class_ids: Array.from(ids) }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        // Validate: at least one class must be selected if departments are selected
        if (formData.department_ids.length > 0 && formData.class_ids.length === 0) {
            setError('Please select at least one class from the departments.');
            return;
        }

        try {
            if (editingBasket) {
                await structuredCompositeBasketsApi.update(editingBasket.id, formData);
            } else {
                await structuredCompositeBasketsApi.create(formData);
            }
            closeModal();
            await fetchData();
        } catch (err) {
            console.error('SCB save error:', err);
            const errorDetail = err.response?.data?.detail || err.message || 'Failed to save basket';
            setError(typeof errorDetail === 'object' ? JSON.stringify(errorDetail) : errorDetail);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Delete this Structured Composite Basket?')) return;
        try {
            await structuredCompositeBasketsApi.delete(id);
            fetchData();
        } catch (err) {
            setError('Failed to delete basket');
        }
    };

    // Group classes by department for display
    const classesByDept = {};
    for (const cls of deptClasses) {
        const deptId = cls.dept_id || 0;
        if (!classesByDept[deptId]) classesByDept[deptId] = [];
        classesByDept[deptId].push(cls);
    }

    if (loading) return <div className="loading"><div className="spinner"></div></div>;

    return (
        <div className="crud-page">
            <div className="page-header">
                <div>
                    <h1>Structured Baskets</h1>
                    <p>Manage composite baskets for mixed theory/lab continuity across departments</p>
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
                    <div key={basket.id} className="crud-item" style={{ borderLeft: '4px solid #8b5cf6' }}>
                        <div className="crud-item-header">
                            <div>
                                <h3 className="crud-item-title">{basket.name}</h3>
                                <div className="flex gap-2 items-center text-xs text-muted">
                                    <span>Sem {basket.semester}</span>
                                    <span>•</span>
                                    <span>{basket.theory_hours + basket.lab_hours} Hours</span>
                                </div>
                            </div>
                            <div className="crud-item-actions">
                                <button className="btn btn-sm btn-secondary" onClick={() => openModal(basket)}><Edit2 size={14} /></button>
                                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(basket.id)}><Trash2 size={14} /></button>
                            </div>
                        </div>

                        <div style={{ marginTop: '12px', fontSize: '13px' }}>
                            <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
                                {basket.same_slot_across_departments && (
                                    <span className="badge" style={{ background: '#eff6ff', color: '#2563eb' }}>Same Slot Cross-Dept</span>
                                )}
                                {basket.allow_lab_parallel && (
                                    <span className="badge" style={{ background: '#f0fdf4', color: '#16a34a' }}>Parallel Labs Allowed</span>
                                )}
                            </div>

                            <div className="text-muted mb-2">
                                <strong>Departments:</strong> {basket.departments_involved && basket.departments_involved.map(d => d.code).join(', ') || 'None'}
                            </div>

                            {basket.selected_classes && basket.selected_classes.length > 0 && (
                                <div className="text-muted mb-2">
                                    <strong>Classes:</strong> {basket.selected_classes.map(c => c.name || c.code).join(', ')}
                                </div>
                            )}

                            <div className="text-muted mb-2">
                                <strong>Hours:</strong> {basket.theory_hours}h Theory, {basket.lab_hours}h Lab ({basket.continuous_lab_periods}h continuous block requested)
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {baskets.length === 0 && (
                <div className="empty-state">
                    <Layers size={48} />
                    <h3>No Structured Baskets</h3>
                    <p>Create an SCB to enforce multiday, multimode continuities.</p>
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '750px' }}>
                        <div className="modal-header">
                            <h2>{editingBasket ? 'Edit SCB' : 'New Structured Composite Basket'}</h2>
                            <button className="modal-close" onClick={closeModal}><X size={20} /></button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Basket Name *</label>
                                    <input className="form-input" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} placeholder="e.g. PP Basket" />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Semester *</label>
                                    <select className="form-select" value={formData.semester} onChange={e => setFormData({ ...formData, semester: parseInt(e.target.value) })}>
                                        {[1, 2, 3, 4, 5, 6, 7, 8].map(n => <option key={n} value={n}>{n}</option>)}
                                    </select>
                                </div>
                            </div>

                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Theory Hours</label>
                                    <input type="number" className="form-input" required min="0" value={formData.theory_hours} onChange={e => setFormData({ ...formData, theory_hours: parseInt(e.target.value) })} />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Lab Hours</label>
                                    <input type="number" className="form-input" required min="0" value={formData.lab_hours} onChange={e => setFormData({ ...formData, lab_hours: parseInt(e.target.value) })} />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Continuous Lab Periods</label>
                                    <input type="number" className="form-input" required min="1" max="4" value={formData.continuous_lab_periods} onChange={e => setFormData({ ...formData, continuous_lab_periods: parseInt(e.target.value) })} />
                                </div>
                            </div>

                            <div className="form-row">
                                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                                    <input
                                        type="checkbox"
                                        checked={formData.same_slot_across_departments}
                                        onChange={e => setFormData({ ...formData, same_slot_across_departments: e.target.checked })}
                                    />
                                    Same Slot Across Departments
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                                    <input
                                        type="checkbox"
                                        checked={formData.allow_lab_parallel}
                                        onChange={e => setFormData({ ...formData, allow_lab_parallel: e.target.checked })}
                                    />
                                    Allow Lab Parallel Distribution
                                </label>
                            </div>

                            {/* Departments */}
                            <div className="form-row">
                                <div className="form-group" style={{ flex: 1 }}>
                                    <label className="form-label">Departments Involved</label>
                                    <div style={{ maxHeight: '130px', overflowY: 'auto', border: '1px solid #eee', padding: '8px', borderRadius: '6px' }}>
                                        {departments.map(d => (
                                            <label key={d.id} style={{ display: 'block', marginBottom: '4px', fontSize: '13px', cursor: 'pointer' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={formData.department_ids.includes(d.id)}
                                                    onChange={e => handleDepartmentChange(d.id, e.target.checked)}
                                                    style={{ marginRight: '8px' }}
                                                />
                                                {d.name} ({d.code})
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Classes (dependent on department selection) */}
                            {formData.department_ids.length > 0 && (
                                <div className="form-row">
                                    <div className="form-group" style={{ flex: 1 }}>
                                        <label className="form-label">
                                            Classes (Semesters) *
                                            <span style={{ fontSize: '11px', color: '#888', marginLeft: '8px' }}>
                                                Select specific classes from above departments
                                            </span>
                                        </label>
                                        {classesLoading ? (
                                            <div style={{
                                                display: 'flex', alignItems: 'center', gap: '8px',
                                                padding: '16px', border: '1px solid #eee', borderRadius: '6px',
                                                color: '#888', fontSize: '13px'
                                            }}>
                                                <Loader2 size={16} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
                                                Loading classes...
                                            </div>
                                        ) : deptClasses.length === 0 ? (
                                            <div style={{
                                                padding: '16px', border: '1px dashed #ddd', borderRadius: '6px',
                                                color: '#999', fontSize: '13px', textAlign: 'center'
                                            }}>
                                                No classes found for selected departments
                                            </div>
                                        ) : (
                                            <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid #eee', padding: '8px', borderRadius: '6px' }}>
                                                {Object.entries(classesByDept).map(([dId, classes]) => {
                                                    const dept = departments.find(d => d.id === parseInt(dId));
                                                    return (
                                                        <div key={dId} style={{ marginBottom: '8px' }}>
                                                            <div style={{
                                                                fontSize: '11px', fontWeight: 600, color: '#666',
                                                                textTransform: 'uppercase', letterSpacing: '0.5px',
                                                                marginBottom: '4px', paddingBottom: '2px',
                                                                borderBottom: '1px solid #f0f0f0'
                                                            }}>
                                                                {dept ? `${dept.name} (${dept.code})` : `Dept ${dId}`}
                                                            </div>
                                                            {classes.map(c => (
                                                                <label key={c.id} style={{ display: 'block', marginBottom: '3px', fontSize: '13px', cursor: 'pointer', paddingLeft: '8px' }}>
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={formData.class_ids.includes(c.id)}
                                                                        onChange={e => handleClassChange(c.id, e.target.checked)}
                                                                        style={{ marginRight: '8px' }}
                                                                    />
                                                                    {c.name} ({c.code}) — Year {c.year}, Sec {c.section}
                                                                </label>
                                                            ))}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                        {formData.department_ids.length > 0 && formData.class_ids.length === 0 && !classesLoading && deptClasses.length > 0 && (
                                            <div style={{ color: '#dc2626', fontSize: '12px', marginTop: '4px' }}>
                                                ⚠ Please select at least one class
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Subjects */}
                            <div className="form-row">
                                <div className="form-group" style={{ flex: 1 }}>
                                    <label className="form-label">Subjects Linked (from Depts)</label>
                                    <div style={{ maxHeight: '150px', overflowY: 'auto', border: '1px solid #eee', padding: '8px', borderRadius: '6px' }}>
                                        {subjects.filter(s => formData.department_ids.includes(s.dept_id) || !s.dept_id).map(s => (
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
                                    </div>
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

            <style>{`
                @keyframes spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
}
