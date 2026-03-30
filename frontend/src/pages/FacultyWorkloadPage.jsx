/**
 * Module 6: Faculty Workload Dashboard
 * Admin → Faculty Workload Dashboard
 */
import { useState, useEffect } from 'react';
import { allocationApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import './FacultyWorkloadPage.css';

export default function FacultyWorkloadPage() {
  const [workload, setWorkload] = useState([]);
  const [loading, setLoading] = useState(true);
  const { selectedDeptId } = useDepartmentContext();

  const fetchWorkload = async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedDeptId) params.department_id = selectedDeptId;
      const res = await allocationApi.getWorkload(params);
      setWorkload(res.data);
    } catch (err) {
      console.error('Failed to load workload data', err);
    }
    setLoading(false);
  };

  useEffect(() => { fetchWorkload(); }, [selectedDeptId]);

  const summary = {
    total: workload.length,
    underload: workload.filter(w => w.status === 'Underload').length,
    balanced: workload.filter(w => w.status === 'Balanced').length,
    overload: workload.filter(w => w.status === 'Overload').length,
    avgHours: workload.length > 0 ? (workload.reduce((s, w) => s + w.total_weekly_hours, 0) / workload.length).toFixed(1) : 0,
  };

  return (
    <div className="workload-page">
      <div className="page-header">
        <h1>Faculty Workload Dashboard</h1>
      </div>

      <div className="summary-cards">
        <div className="summary-card">
          <div className="card-value">{summary.total}</div>
          <div className="card-label">Total Faculty</div>
        </div>
        <div className="summary-card underload">
          <div className="card-value">{summary.underload}</div>
          <div className="card-label">Underload (0-12h)</div>
        </div>
        <div className="summary-card balanced">
          <div className="card-value">{summary.balanced}</div>
          <div className="card-label">Balanced (13-16h)</div>
        </div>
        <div className="summary-card overload">
          <div className="card-value">{summary.overload}</div>
          <div className="card-label">Overload (17+h)</div>
        </div>
        <div className="summary-card">
          <div className="card-value">{summary.avgHours}</div>
          <div className="card-label">Avg Hours/Week</div>
        </div>
      </div>

      {loading ? <p className="loading">Loading...</p> : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Teacher</th>
                <th>Theory Subjects</th>
                <th>Labs</th>
                <th>Total Weekly Hours</th>
                <th>Status</th>
                <th>Workload Bar</th>
              </tr>
            </thead>
            <tbody>
              {workload.map(w => (
                <tr key={w.teacher_id}>
                  <td><strong>{w.teacher_name}</strong></td>
                  <td>{w.theory_subjects}</td>
                  <td>{w.labs}</td>
                  <td>{w.total_weekly_hours}</td>
                  <td><span className={`status-badge ${w.status.toLowerCase()}`}>{w.status}</span></td>
                  <td>
                    <div className="workload-bar-bg">
                      <div
                        className={`workload-bar-fill ${w.status.toLowerCase()}`}
                        style={{ width: `${Math.min((w.total_weekly_hours / 20) * 100, 100)}%` }}
                      ></div>
                    </div>
                  </td>
                </tr>
              ))}
              {workload.length === 0 && (
                <tr><td colSpan={6} className="empty-row">No workload data. Assign teachers to subjects first.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
