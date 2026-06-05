/**
 * Integrity Report Page
 * Shows database integrity diagnostics and provides a repair tool
 * to clean stale teacher mappings, orphaned records, and mismatched data.
 */
import { useEffect, useState, useCallback } from 'react';
import {
    ShieldCheck,
    ShieldAlert,
    Wrench,
    RefreshCw,
    CheckCircle,
    AlertTriangle,
    Trash2,
    Loader,
    XCircle,
    Info,
} from 'lucide-react';
import { integrityApi } from '../services/api';

export default function IntegrityPage() {
    const [loading, setLoading] = useState(false);
    const [repairing, setRepairing] = useState(false);
    const [diagnostics, setDiagnostics] = useState(null);
    const [repairResult, setRepairResult] = useState(null);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState('all');

    const fetchDiagnostics = useCallback(async () => {
        setLoading(true);
        setError(null);
        setRepairResult(null);
        try {
            const res = await integrityApi.getDiagnostics();
            setDiagnostics(res.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to load diagnostics');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchDiagnostics();
    }, [fetchDiagnostics]);

    const handleRepair = async () => {
        if (!confirm(
            'This will remove all stale and mismatched mappings from the database.\n\n' +
            'This action cannot be undone. Proceed?'
        )) return;

        setRepairing(true);
        setError(null);
        try {
            const res = await integrityApi.repair();
            setRepairResult(res.data);
            // Refresh diagnostics after repair
            await fetchDiagnostics();
        } catch (err) {
            setError(err.response?.data?.detail || 'Repair failed');
        } finally {
            setRepairing(false);
        }
    };

    const filteredIssues = diagnostics?.issues?.filter(issue => {
        if (filter === 'all') return true;
        return issue.type === filter;
    }) || [];

    const typeLabels = {
        stale_teacher_mapping: { label: 'Stale Teacher Mapping', color: '#f59e0b', icon: AlertTriangle },
        year_semester_mismatch: { label: 'Year/Semester Mismatch', color: '#ef4444', icon: XCircle },
        batch_semester_mismatch: { label: 'Phantom Batch Mismatch', color: '#ec4899', icon: AlertTriangle },
        orphaned_cst: { label: 'Orphaned Record', color: '#8b5cf6', icon: Trash2 },
        orphaned_batch: { label: 'Orphaned Batch', color: '#8b5cf6', icon: Trash2 },
        orphaned_cst_batch: { label: 'Orphaned Mapping Batch', color: '#8b5cf6', icon: Trash2 },
    };

    return (
        <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                <div>
                    <h1 style={{ margin: '0 0 4px 0', display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <ShieldCheck size={28} style={{ color: '#6366f1' }} />
                        Integrity Report
                    </h1>
                    <p style={{ margin: 0, color: 'var(--text-secondary, #666)', fontSize: '14px' }}>
                        Scan and repair stale mappings, orphaned records, and year/semester mismatches
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                        className="btn btn-secondary"
                        onClick={fetchDiagnostics}
                        disabled={loading}
                        style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                        <RefreshCw size={16} className={loading ? 'spinning' : ''} />
                        Refresh
                    </button>
                    <button
                        className="btn btn-primary"
                        onClick={handleRepair}
                        disabled={repairing || !diagnostics || diagnostics.total_issues === 0}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            background: diagnostics?.total_issues > 0
                                ? 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)'
                                : undefined,
                        }}
                    >
                        {repairing ? (
                            <>
                                <Loader size={16} className="spinning" />
                                Repairing...
                            </>
                        ) : (
                            <>
                                <Wrench size={16} />
                                Repair All Issues
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Repair Result Banner */}
            {repairResult && (
                <div style={{
                    background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
                    border: '1px solid #86efac',
                    borderRadius: '12px',
                    padding: '16px 20px',
                    marginBottom: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                }}>
                    <CheckCircle size={24} style={{ color: '#16a34a', flexShrink: 0 }} />
                    <div>
                        <div style={{ fontWeight: '700', color: '#15803d', fontSize: '15px' }}>
                            {repairResult.message}
                        </div>
                        {repairResult.total_removed > 0 && (
                            <div style={{ fontSize: '13px', color: '#166534', marginTop: '4px' }}>
                                {Object.entries(repairResult.removed_breakdown || {})
                                    .filter(([, count]) => count > 0)
                                    .map(([key, count]) => `${key.replace(/_/g, ' ')}: ${count}`)
                                    .join(' • ')}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="alert alert-error" style={{ marginBottom: '20px' }}>
                    <AlertTriangle size={18} />
                    {error}
                </div>
            )}

            {/* Summary Cards */}
            {diagnostics && (
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '12px',
                    marginBottom: '20px',
                }}>
                    {/* Total */}
                    <div style={{
                        background: diagnostics.total_issues === 0
                            ? 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)'
                            : 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)',
                        borderRadius: '12px',
                        padding: '16px',
                        textAlign: 'center',
                        border: diagnostics.total_issues === 0
                            ? '1px solid #86efac'
                            : '1px solid #fca5a5',
                    }}>
                        {diagnostics.total_issues === 0 ? (
                            <ShieldCheck size={28} style={{ color: '#16a34a', marginBottom: '4px' }} />
                        ) : (
                            <ShieldAlert size={28} style={{ color: '#dc2626', marginBottom: '4px' }} />
                        )}
                        <div style={{
                            fontSize: '28px',
                            fontWeight: '800',
                            color: diagnostics.total_issues === 0 ? '#16a34a' : '#dc2626'
                        }}>
                            {diagnostics.total_issues}
                        </div>
                        <div style={{ fontSize: '12px', fontWeight: '600', color: '#64748b' }}>
                            Total Issues
                        </div>
                    </div>

                    {/* Per-type cards */}
                    {Object.entries(diagnostics.summary || {}).map(([type, count]) => {
                        const meta = typeLabels[type] || { label: type, color: '#64748b', icon: Info };
                        const Icon = meta.icon;
                        return (
                            <div key={type}
                                onClick={() => setFilter(filter === type ? 'all' : type)}
                                style={{
                                    background: filter === type
                                        ? `${meta.color}15`
                                        : 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
                                    borderRadius: '12px',
                                    padding: '16px',
                                    textAlign: 'center',
                                    cursor: 'pointer',
                                    border: filter === type
                                        ? `2px solid ${meta.color}`
                                        : '1px solid #e2e8f0',
                                    transition: 'all 0.2s ease',
                                }}
                            >
                                <Icon size={22} style={{ color: meta.color, marginBottom: '4px' }} />
                                <div style={{ fontSize: '24px', fontWeight: '800', color: meta.color }}>
                                    {count}
                                </div>
                                <div style={{ fontSize: '11px', fontWeight: '600', color: '#64748b' }}>
                                    {meta.label}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Filter bar */}
            {diagnostics?.total_issues > 0 && (
                <div style={{
                    display: 'flex',
                    gap: '8px',
                    marginBottom: '16px',
                    flexWrap: 'wrap',
                }}>
                    <button
                        className={`btn btn-sm ${filter === 'all' ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setFilter('all')}
                    >
                        All ({diagnostics.total_issues})
                    </button>
                    {Object.entries(diagnostics.summary || {}).map(([type, count]) => {
                        const meta = typeLabels[type] || { label: type };
                        return (
                            <button
                                key={type}
                                className={`btn btn-sm ${filter === type ? 'btn-primary' : 'btn-secondary'}`}
                                onClick={() => setFilter(filter === type ? 'all' : type)}
                            >
                                {meta.label} ({count})
                            </button>
                        );
                    })}
                </div>
            )}

            {/* Issues Table */}
            {loading ? (
                <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
                    <Loader size={32} className="spinning" />
                    <p style={{ marginTop: '12px' }}>Scanning database...</p>
                </div>
            ) : diagnostics?.total_issues === 0 ? (
                <div style={{
                    textAlign: 'center',
                    padding: '60px 20px',
                    background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
                    borderRadius: '16px',
                    border: '1px solid #86efac',
                }}>
                    <ShieldCheck size={48} style={{ color: '#16a34a', marginBottom: '12px' }} />
                    <h3 style={{ margin: '0 0 6px 0', color: '#15803d' }}>All Clear!</h3>
                    <p style={{ margin: 0, color: '#166534', fontSize: '14px' }}>
                        No integrity issues found. All mappings are valid and current.
                    </p>
                </div>
            ) : (
                <div className="card" style={{ overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '700', color: '#475569' }}>Type</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '700', color: '#475569' }}>Subject</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '700', color: '#475569' }}>Class</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '700', color: '#475569' }}>Teacher</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '700', color: '#475569' }}>Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredIssues.map((issue, idx) => {
                                    const meta = typeLabels[issue.type] || { label: issue.type, color: '#64748b' };
                                    return (
                                        <tr key={idx} style={{
                                            borderBottom: '1px solid #f1f5f9',
                                            background: idx % 2 === 0 ? 'white' : '#fafbfc',
                                        }}>
                                            <td style={{ padding: '10px 12px' }}>
                                                <span style={{
                                                    background: `${meta.color}18`,
                                                    color: meta.color,
                                                    padding: '3px 8px',
                                                    borderRadius: '6px',
                                                    fontSize: '11px',
                                                    fontWeight: '700',
                                                    whiteSpace: 'nowrap',
                                                }}>
                                                    {meta.label}
                                                </span>
                                            </td>
                                            <td style={{ padding: '10px 12px' }}>
                                                <div style={{ fontWeight: '600' }}>{issue.subject_code || '—'}</div>
                                                {issue.subject_year && (
                                                    <div style={{ fontSize: '11px', color: '#64748b' }}>
                                                        Y{issue.subject_year}/S{issue.subject_semester}
                                                    </div>
                                                )}
                                            </td>
                                            <td style={{ padding: '10px 12px' }}>
                                                <div style={{ fontWeight: '600' }}>{issue.class_code || '—'}</div>
                                                {issue.class_year && (
                                                    <div style={{ fontSize: '11px', color: '#64748b' }}>
                                                        Y{issue.class_year}/S{issue.class_semester}
                                                    </div>
                                                )}
                                            </td>
                                            <td style={{ padding: '10px 12px', color: '#475569' }}>
                                                {issue.teacher || '—'}
                                                {issue.component_type && (
                                                    <span style={{
                                                        marginLeft: '6px',
                                                        fontSize: '10px',
                                                        background: '#e2e8f0',
                                                        padding: '1px 6px',
                                                        borderRadius: '4px',
                                                        color: '#475569',
                                                    }}>
                                                        {issue.component_type}
                                                    </span>
                                                )}
                                            </td>
                                            <td style={{ padding: '10px 12px', fontSize: '12px', color: '#64748b', maxWidth: '300px' }}>
                                                {issue.reason}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                    {filteredIssues.length === 0 && filter !== 'all' && (
                        <div style={{ padding: '20px', textAlign: 'center', color: '#64748b' }}>
                            No issues of this type found.
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
