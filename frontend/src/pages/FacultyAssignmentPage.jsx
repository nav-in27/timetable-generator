/**
 * Module 3-5: Faculty Assignment Review Page
 * Admin → Faculty Assignment Review
 * Includes: allocation mode toggle, run allocation, assignment CRUD, swap, lock
 */
import { useState, useEffect } from 'react';
import { allocationApi, teachersApi, semestersApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import './FacultyAssignmentPage.css';

export default function FacultyAssignmentPage() {
  const [assignments, setAssignments] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [classes, setClasses] = useState([]);
  const [mode, setMode] = useState('manual');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({ teacher_id: '', class_id: '' });
  const [swapA, setSwapA] = useState(null);
  const { selectedDeptId } = useDepartmentContext();
  const [filterSemester, setFilterSemester] = useState('');

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedDeptId) params.department_id = selectedDeptId;
      if (filterSemester) params.semester_id = filterSemester;

      const [assignRes, modeRes, teacherRes, classRes] = await Promise.all([
        allocationApi.getAssignments(params),
        allocationApi.getMode(),
        teachersApi.getAll(selectedDeptId ? { dept_id: selectedDeptId } : {}),
        semestersApi.getAll(selectedDeptId ? { dept_id: selectedDeptId } : {}),
      ]);
      setAssignments(assignRes.data);
      setMode(modeRes.data.mode);
      setTeachers(teacherRes.data);
      setClasses(classRes.data);
    } catch (err) {
      console.error('Failed to load assignments', err);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [selectedDeptId, filterSemester]);

  const handleModeChange = async (newMode) => {
    try {
      await allocationApi.setMode(newMode);
      setMode(newMode);
    } catch (err) {
      alert('Failed to change mode');
    }
  };

  const handleRunAllocation = async () => {
    if (!window.confirm('Run preference-based allocation? This will create new assignments for unassigned slots.')) return;
    setRunning(true);
    try {
      const res = await allocationApi.runAllocation({
        department_id: selectedDeptId ? +selectedDeptId : null,
        dry_run: false,
      });
      alert(res.data.detail);
      fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Allocation failed');
    }
    setRunning(false);
  };

  const handleDryRun = async () => {
    setRunning(true);
    try {
      const res = await allocationApi.runAllocation({
        department_id: selectedDeptId ? +selectedDeptId : null,
        dry_run: true,
      });
      alert(`Dry run: ${res.data.assignments?.length || 0} proposed assignments`);
    } catch (err) {
      alert(err.response?.data?.detail || 'Dry run failed');
    }
    setRunning(false);
  };

  const handleUpdate = async (id) => {
    try {
      const data = {};
      if (editForm.teacher_id) data.teacher_id = +editForm.teacher_id;
      if (editForm.class_id) data.class_id = +editForm.class_id;
      await allocationApi.updateAssignment(id, data);
      setEditId(null);
      fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Update failed');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this assignment?')) return;
    try {
      await allocationApi.deleteAssignment(id);
      fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Delete failed');
    }
  };

  const handleLock = async (id) => {
    try {
      await allocationApi.lockAssignment(id);
      fetchData();
    } catch (err) { alert('Lock failed'); }
  };

  const handleUnlock = async (id) => {
    try {
      await allocationApi.unlockAssignment(id);
      fetchData();
    } catch (err) { alert('Unlock failed'); }
  };

  const handleSwap = async (id) => {
    if (!swapA) {
      setSwapA(id);
      return;
    }
    if (swapA === id) {
      setSwapA(null);
      return;
    }
    try {
      await allocationApi.swapAssignments(swapA, id);
      setSwapA(null);
      fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Swap failed');
      setSwapA(null);
    }
  };

  return (
    <div className="faculty-page">
      <div className="page-header">
        <h1>Faculty Assignment Review</h1>
        <div className="header-actions">
          <div className="mode-toggle">
            <span className="mode-label">Mode:</span>
            <button className={`mode-btn ${mode === 'manual' ? 'active' : ''}`} onClick={() => handleModeChange('manual')}>Manual</button>
            <button className={`mode-btn ${mode === 'preference' ? 'active' : ''}`} onClick={() => handleModeChange('preference')}>Preference</button>
          </div>
          {mode === 'preference' && (
            <>
              <button className="btn btn-secondary" onClick={handleDryRun} disabled={running}>Dry Run</button>
              <button className="btn btn-primary" onClick={handleRunAllocation} disabled={running}>
                {running ? 'Running...' : 'Run Allocation'}
              </button>
            </>
          )}
        </div>
      </div>

      {swapA && (
        <div className="swap-banner">
          Swap mode: Select another assignment to swap with (ID: {swapA}).
          <button className="btn btn-secondary" onClick={() => setSwapA(null)}>Cancel Swap</button>
        </div>
      )}

      <div className="filters-bar">
        <select value={filterSemester} onChange={e => setFilterSemester(e.target.value)}>
          <option value="">All Classes</option>
          {classes.map(c => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
        </select>
      </div>

      {loading ? <p className="loading">Loading...</p> : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Teacher</th>
                <th>Subject</th>
                <th>Class</th>
                <th>Type</th>
                <th>Hrs/Wk</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map(a => (
                <tr key={a.id} className={swapA === a.id ? 'swap-selected' : ''}>
                  <td>
                    {editId === a.id ? (
                      <select value={editForm.teacher_id || a.teacher_id} onChange={e => setEditForm({ ...editForm, teacher_id: e.target.value })}>
                        {teachers.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                      </select>
                    ) : a.teacher_name}
                  </td>
                  <td>{a.subject_name} <span className="code-hint">({a.subject_code})</span></td>
                  <td>
                    {editId === a.id ? (
                      <select value={editForm.class_id || a.class_id} onChange={e => setEditForm({ ...editForm, class_id: e.target.value })}>
                        {classes.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    ) : a.class_name}
                  </td>
                  <td><span className={`type-badge ${a.component_type}`}>{a.component_type.toUpperCase()}</span></td>
                  <td>{a.weekly_hours}</td>
                  <td>
                    {a.is_locked ? <span className="lock-badge locked">🔒 Locked</span> : <span className="lock-badge unlocked">🔓 Open</span>}
                  </td>
                  <td className="action-cell">
                    {editId === a.id ? (
                      <>
                        <button className="btn-sm btn-save" onClick={() => handleUpdate(a.id)}>Save</button>
                        <button className="btn-sm btn-cancel" onClick={() => setEditId(null)}>Cancel</button>
                      </>
                    ) : (
                      <>
                        <button className="btn-sm btn-edit" onClick={() => { setEditId(a.id); setEditForm({ teacher_id: a.teacher_id, class_id: a.class_id }); }}>Edit</button>
                        <button className="btn-sm btn-swap" onClick={() => handleSwap(a.id)}>{swapA === a.id ? 'Cancel' : 'Swap'}</button>
                        {a.is_locked ?
                          <button className="btn-sm btn-unlock" onClick={() => handleUnlock(a.id)}>Unlock</button> :
                          <button className="btn-sm btn-lock" onClick={() => handleLock(a.id)}>Lock</button>
                        }
                        <button className="btn-sm btn-delete" onClick={() => handleDelete(a.id)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {assignments.length === 0 && (
                <tr><td colSpan={7} className="empty-row">No assignments found. Use manual or preference-based allocation.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
