/**
 * Module 9: Timetable Feasibility Analyzer Page
 * Detect scheduling conflicts before generation
 */
import { useState } from 'react';
import { feasibilityApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import './FeasibilityPage.css';

export default function FeasibilityPage() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const { selectedDeptId } = useDepartmentContext();

  const runAnalysis = async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedDeptId) params.department_id = selectedDeptId;
      const res = await feasibilityApi.analyze(params);
      setReport(res.data);
    } catch (err) {
      console.error('Analysis failed', err);
      alert('Feasibility analysis failed');
    }
    setLoading(false);
  };

  const severityIcon = (s) => {
    if (s === 'error') return '❌';
    if (s === 'warning') return '⚠️';
    return 'ℹ️';
  };

  return (
    <div className="feasibility-page">
      <div className="page-header">
        <h1>Timetable Feasibility Analyzer</h1>
        <button className="btn btn-primary" onClick={runAnalysis} disabled={loading}>
          {loading ? 'Analyzing...' : 'Run Analysis'}
        </button>
      </div>

      <p className="description">
        Checks for scheduling conflicts before timetable generation: slot capacity, teacher workload,
        lab room availability, elective sync, and parallel scheduling feasibility.
      </p>

      {report && (
        <div className="report">
          <div className={`report-banner ${report.feasible ? 'feasible' : 'infeasible'}`}>
            <span className="banner-icon">{report.feasible ? '✅' : '🚫'}</span>
            <div>
              <strong>{report.feasible ? 'Schedule Appears Feasible' : 'Conflicts Detected'}</strong>
              <p>{report.summary}</p>
            </div>
          </div>

          <div className="report-stats">
            <span className="stat error-stat">Errors: {report.error_count}</span>
            <span className="stat warning-stat">Warnings: {report.warning_count}</span>
          </div>

          {report.warnings && report.warnings.length > 0 && (
            <div className="warnings-list">
              {report.warnings.map((w, i) => (
                <div key={i} className={`warning-item ${w.severity}`}>
                  <span className="warning-icon">{severityIcon(w.severity)}</span>
                  <div className="warning-body">
                    <span className="warning-category">{w.category.replace(/_/g, ' ').toUpperCase()}</span>
                    <p className="warning-message">{w.message}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {report.warnings && report.warnings.length === 0 && (
            <p className="all-clear">All checks passed. No conflicts detected.</p>
          )}
        </div>
      )}
    </div>
  );
}
