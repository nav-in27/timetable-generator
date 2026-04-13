/**
 * Departments Management Page
 *
 * Allows admin to add/edit departments and (optionally) configure per-department rule toggles.
 * Note: No delete UI by default to avoid accidental data loss/orphaning.
 */
import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Plus, Edit2, X, Save, Upload, Download, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { departmentsApi, ruleTogglesApi, departmentImportApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import './CrudPage.css';

const DEFAULT_TOGGLES = {
    lab_continuity_strict: false,
    teacher_gap_preference: false,
    max_consecutive_enabled: false,
    max_consecutive_limit: 3,
    lab_continuity_is_hard: false,
    teacher_gap_is_hard: false,
    max_consecutive_is_hard: false,
};

function normalizeToggle(value) {
    return {
        ...DEFAULT_TOGGLES,
        ...(value || {}),
    };
}

export default function DepartmentsPage() {
    const { departments, reloadDepartments, selectedDeptId, setSelectedDeptId } = useDepartmentContext();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Add/Edit modal state
    const [showModal, setShowModal] = useState(false);
    const [editing, setEditing] = useState(null);
    const [formData, setFormData] = useState({ name: '', code: '' });

    // Import State
    const [showImportModal, setShowImportModal] = useState(false);
    const [importFile, setImportFile] = useState(null);
    const [importResult, setImportResult] = useState(null);
    const [importLoading, setImportLoading] = useState(false);
    const [importCommitting, setImportCommitting] = useState(false);
    const [importStep, setImportStep] = useState('upload'); // upload | preview | committed

    // Rule toggles state (per dept)
    const [togglesByDeptId, setTogglesByDeptId] = useState({});
    const [savingTogglesFor, setSavingTogglesFor] = useState(null);
    const [savedAtByDeptId, setSavedAtByDeptId] = useState({});

    const deptIdSet = useMemo(() => new Set((departments || []).map((d) => d.id)), [departments]);

    const loadToggles = async () => {
        try {
            const res = await ruleTogglesApi.getAll();
            const map = {};
            (res.data || []).forEach((row) => {
                if (!row?.dept_id) return;
                map[row.dept_id] = normalizeToggle(row);
            });

            // Ensure every department has defaults even if no row exists yet.
            const withDefaults = {};
            (departments || []).forEach((dept) => {
                withDefaults[dept.id] = normalizeToggle(map[dept.id]);
            });
            setTogglesByDeptId(withDefaults);
        } catch (err) {
            console.error('Failed to load rule toggles', err);
        }
    };

    useEffect(() => {
        // Page-level loading: departments come from context; we still set a spinner briefly for toggle loading.
        setLoading(true);
        Promise.resolve()
            .then(() => loadToggles())
            .catch(() => {})
            .finally(() => setLoading(false));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [departments?.length]);

    const openModal = (dept = null) => {
        setEditing(dept);
        setFormData({
            name: dept?.name || '',
            code: dept?.code || '',
        });
        setError(null);
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditing(null);
        setFormData({ name: '', code: '' });
        setError(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);

        try {
            if (editing) {
                await departmentsApi.update(editing.id, formData);
            } else {
                await departmentsApi.create(formData);
            }
            await reloadDepartments();
            closeModal();
        } catch (err) {
            console.error('Failed to save department', err);
            const detail = err.response?.data?.detail || err.message || 'Failed to save department';
            setError(typeof detail === 'object' ? JSON.stringify(detail) : detail);
        }
    };

    const updateToggleLocal = (deptId, patch) => {
        setTogglesByDeptId((prev) => ({
            ...prev,
            [deptId]: normalizeToggle({
                ...(prev?.[deptId] || DEFAULT_TOGGLES),
                ...patch,
            }),
        }));
    };

    const saveToggles = async (deptId) => {
        setSavingTogglesFor(deptId);
        setError(null);
        try {
            const toggle = normalizeToggle(togglesByDeptId[deptId]);
            const payload = {
                lab_continuity_strict: !!toggle.lab_continuity_strict,
                teacher_gap_preference: !!toggle.teacher_gap_preference,
                max_consecutive_enabled: !!toggle.max_consecutive_enabled,
                max_consecutive_limit: Number(toggle.max_consecutive_limit || 3),
                lab_continuity_is_hard: !!toggle.lab_continuity_is_hard,
                teacher_gap_is_hard: !!toggle.teacher_gap_is_hard,
                max_consecutive_is_hard: !!toggle.max_consecutive_is_hard,
            };
            const res = await ruleTogglesApi.update(deptId, payload);
            setTogglesByDeptId((prev) => ({
                ...prev,
                [deptId]: normalizeToggle(res.data),
            }));
            setSavedAtByDeptId((prev) => ({ ...prev, [deptId]: Date.now() }));
        } catch (err) {
            console.error('Failed to save rule toggles', err);
            const detail = err.response?.data?.detail || err.message || 'Failed to save rule toggles';
            setError(typeof detail === 'object' ? JSON.stringify(detail) : detail);
        } finally {
            setSavingTogglesFor(null);
        }
    };

    if (loading) {
        return <div className="loading"><div className="spinner"></div></div>;
    }

    return (
        <div className="crud-page">
            <div className="page-header">
                <div>
                    <h1>Departments</h1>
                    <p>Add/edit departments and configure optional department rules.</p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button className="btn btn-primary" onClick={() => openModal()}>
                        <Plus size={18} />
                        Add Department
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

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                    <button
                        onClick={() => setError(null)}
                        style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                        <X size={16} />
                    </button>
                </div>
            )}

            <div className="crud-grid">
                {departments.map((dept) => {
                    const toggle = normalizeToggle(togglesByDeptId[dept.id]);
                    const savedAt = savedAtByDeptId[dept.id];
                    const isSelected = selectedDeptId && Number(selectedDeptId) === dept.id;

                    return (
                        <div key={dept.id} className="crud-item">
                            <div className="crud-item-header">
                                <div>
                                    <h3 className="crud-item-title" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                        <span>{dept.name}</span>
                                        <span className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">
                                            {dept.code}
                                        </span>
                                        {isSelected && (
                                            <span className="text-xs bg-green-100 px-2 py-0.5 rounded text-green-700">
                                                Selected
                                            </span>
                                        )}
                                    </h3>
                                </div>
                                <div className="crud-item-actions">
                                    <button className="btn btn-sm btn-secondary" onClick={() => openModal(dept)}>
                                        <Edit2 size={14} />
                                    </button>
                                </div>
                            </div>

                            <div className="flex gap-2 mt-2" style={{ flexWrap: 'wrap' }}>
                                <button
                                    className="btn btn-sm btn-secondary"
                                    onClick={() => setSelectedDeptId(String(dept.id))}
                                    disabled={isSelected}
                                    title="Set as current department context"
                                >
                                    Use This Department
                                </button>
                                <button
                                    className="btn btn-sm btn-secondary"
                                    onClick={() => {
                                        // Force reload for both departments and toggles (safe, read-only).
                                        reloadDepartments().then(() => loadToggles());
                                    }}
                                    title="Refresh departments and rule settings"
                                >
                                    Refresh
                                </button>
                            </div>

                            <details style={{ marginTop: '12px' }}>
                                <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
                                    Optional Rule Toggles (Stored Only)
                                </summary>
                                <p className="text-xs text-muted" style={{ marginTop: '6px' }}>
                                    These settings are saved per department. (Generation behavior is unchanged unless you explicitly wire rules into generation.)
                                </p>

                                <div style={{ display: 'grid', gap: '10px', marginTop: '10px' }}>
                                    <div className="form-row" style={{ gridTemplateColumns: '1fr auto auto' }}>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>Lab Continuity Strictness</div>
                                            <div className="text-xs text-muted">Labs must be continuous when enabled.</div>
                                        </div>
                                        <label className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <input
                                                type="checkbox"
                                                checked={!!toggle.lab_continuity_strict}
                                                onChange={(e) => updateToggleLocal(dept.id, { lab_continuity_strict: e.target.checked })}
                                            />
                                            Enabled
                                        </label>
                                        <label className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <input
                                                type="checkbox"
                                                checked={!!toggle.lab_continuity_is_hard}
                                                onChange={(e) => updateToggleLocal(dept.id, { lab_continuity_is_hard: e.target.checked })}
                                                disabled={!toggle.lab_continuity_strict}
                                            />
                                            Hard
                                        </label>
                                    </div>

                                    <div className="form-row" style={{ gridTemplateColumns: '1fr auto auto' }}>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>Teacher Gap Preference</div>
                                            <div className="text-xs text-muted">Prefer gaps between classes instead of consecutive periods.</div>
                                        </div>
                                        <label className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <input
                                                type="checkbox"
                                                checked={!!toggle.teacher_gap_preference}
                                                onChange={(e) => updateToggleLocal(dept.id, { teacher_gap_preference: e.target.checked })}
                                            />
                                            Enabled
                                        </label>
                                        <label className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <input
                                                type="checkbox"
                                                checked={!!toggle.teacher_gap_is_hard}
                                                onChange={(e) => updateToggleLocal(dept.id, { teacher_gap_is_hard: e.target.checked })}
                                                disabled={!toggle.teacher_gap_preference}
                                            />
                                            Hard
                                        </label>
                                    </div>

                                    <div style={{ display: 'grid', gap: '8px' }}>
                                        <div className="form-row" style={{ gridTemplateColumns: '1fr auto auto' }}>
                                            <div>
                                                <div style={{ fontWeight: 600 }}>Max Consecutive Periods</div>
                                                <div className="text-xs text-muted">Enforce a department-defined maximum consecutive limit.</div>
                                            </div>
                                            <label className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={!!toggle.max_consecutive_enabled}
                                                    onChange={(e) => updateToggleLocal(dept.id, { max_consecutive_enabled: e.target.checked })}
                                                />
                                                Enabled
                                            </label>
                                            <label className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={!!toggle.max_consecutive_is_hard}
                                                    onChange={(e) => updateToggleLocal(dept.id, { max_consecutive_is_hard: e.target.checked })}
                                                    disabled={!toggle.max_consecutive_enabled}
                                                />
                                                Hard
                                            </label>
                                        </div>

                                        <div className="form-row" style={{ gridTemplateColumns: '1fr 1fr' }}>
                                            <div className="form-group" style={{ marginBottom: 0 }}>
                                                <label className="form-label">Maximum Consecutive Limit</label>
                                                <input
                                                    type="number"
                                                    className="form-input"
                                                    min={1}
                                                    max={7}
                                                    value={toggle.max_consecutive_limit}
                                                    onChange={(e) =>
                                                        updateToggleLocal(dept.id, {
                                                            max_consecutive_limit: Number(e.target.value),
                                                        })
                                                    }
                                                    disabled={!toggle.max_consecutive_enabled}
                                                />
                                                <p className="text-xs text-muted mt-1">
                                                    Applies only when the toggle is enabled.
                                                </p>
                                            </div>
                                            <div />
                                        </div>

                                        <div className="flex gap-2 items-center" style={{ justifyContent: 'flex-end' }}>
                                            {savedAt && (
                                                <span className="text-xs text-muted">
                                                    Saved {new Date(savedAt).toLocaleTimeString()}
                                                </span>
                                            )}
                                            <button
                                                className="btn btn-sm btn-primary"
                                                onClick={() => saveToggles(dept.id)}
                                                disabled={savingTogglesFor === dept.id || !deptIdSet.has(dept.id)}
                                            >
                                                <Save size={14} />
                                                {savingTogglesFor === dept.id ? 'Saving...' : 'Save Rules'}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </details>
                        </div>
                    );
                })}

                {departments.length === 0 && (
                    <div className="empty-state">
                        <h3>No Departments Yet</h3>
                        <p>Add your first department to get started.</p>
                        <button className="btn btn-primary" onClick={() => openModal()}>
                            <Plus size={18} />
                            Add Department
                        </button>
                    </div>
                )}
            </div>

            {showModal && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '520px' }}>
                        <div className="modal-header">
                            <h2>{editing ? 'Edit Department' : 'Add Department'}</h2>
                            <button className="modal-close" onClick={closeModal}>
                                <X size={20} />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit}>
                            <div className="form-group">
                                <label className="form-label">Department Name *</label>
                                <input
                                    type="text"
                                    className="form-input"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    required
                                    placeholder="e.g., Computer Science and Engineering"
                                />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Department Code *</label>
                                <input
                                    type="text"
                                    className="form-input"
                                    value={formData.code}
                                    onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                    required
                                    placeholder="e.g., CSE"
                                />
                            </div>

                            <div className="modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={closeModal}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    {editing ? 'Update Department' : 'Create Department'}
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
                                Bulk Department Import
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
                                        Use the template with DEPARTMENTS sheet and fill in your departments.
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
                                            href={departmentImportApi.getTemplateUrl()}
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
                                                    const res = await departmentImportApi.upload(importFile);
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
                                            <div key={i} style={{ fontSize: '13px', color: '#b91c1c', padding: '4px 0' }}>• {e}</div>
                                        ))}
                                    </div>
                                )}

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

                                        <div style={{ maxHeight: '400px', overflow: 'auto', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                                                <thead style={{ position: 'sticky', top: 0, background: '#1e293b', color: 'white', zIndex: 1 }}>
                                                    <tr>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Row</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Status</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Code</th>
                                                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Name</th>
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
                                                                <td style={{ padding: '6px 10px', fontFamily: 'monospace', fontWeight: '600' }}>{row.data?.['Department Code'] || '—'}</td>
                                                                <td style={{ padding: '6px 10px' }}>{row.data?.['Department Name'] || '—'}</td>
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
                                                            const res = await departmentImportApi.commit(importResult.batch_id);
                                                            setImportResult(res.data);
                                                            setImportStep('committed');
                                                            reloadDepartments();
                                                        } catch (err) {
                                                            const detail = err.response?.data?.detail || err.message;
                                                            setError(typeof detail === 'object' ? JSON.stringify(detail) : detail);
                                                        } finally {
                                                            setImportCommitting(false);
                                                        }
                                                    }}
                                                >
                                                    {importCommitting ? <><Loader2 size={16} className="spin" /> Importing...</> : <><CheckCircle size={16} /> Commit Import ({importResult.total_rows - importResult.failed})</>}
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
                                                            const res = await departmentImportApi.commit(importResult.batch_id);
                                                            setImportResult(res.data);
                                                            setImportStep('committed');
                                                            reloadDepartments();
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
                                        Departments are now available in the system.
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
                                            <div>Total Departments: <strong>{importResult.health_check.total_departments}</strong></div>
                                        </div>
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

