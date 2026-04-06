/**
 * Lab Master View — Classic College Timetable Format
 *
 * Each lab gets a separate table showing:
 *   Rows = Days (MON–FRI)
 *   Columns = Period 1 | Period 2 | BREAK | Period 3 | LUNCH | Period 4 | Period 5 | BREAK | Period 6 | Period 7
 *
 * Two viewing modes:
 *   1) All Labs (stacked, one table per lab)
 *   2) Single Lab (printable)
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useDepartmentContext } from '../context/DepartmentContext';
import { reportsApi } from '../services/api';
import {
    Download, Printer, AlertCircle, Filter, Building2,
    RefreshCw, Beaker, ChevronDown, Eye, Layers
} from 'lucide-react';
import './MasterLabTimetablePage.css';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
const DAY_SHORT = ['MON', 'TUE', 'WED', 'THU', 'FRI'];

// The visual column structure matching real college timetable
// Periods 1-7 with breaks and lunch injected between them
const COLUMN_STRUCTURE = [
    { type: 'period', slot: 0, label: '1', time: '08:45–09:45' },
    { type: 'period', slot: 1, label: '2', time: '09:45–10:45' },
    { type: 'break', label: 'Break', time: '10:45–11:00' },
    { type: 'period', slot: 2, label: '3', time: '11:00–12:00' },
    { type: 'break', label: 'Lunch', time: '12:00–01:00', isLunch: true },
    { type: 'period', slot: 3, label: '4', time: '01:00–02:00' },
    { type: 'period', slot: 4, label: '5', time: '02:00–02:50' },
    { type: 'break', label: 'Break', time: '02:50–03:05' },
    { type: 'period', slot: 5, label: '6', time: '03:05–03:55' },
    { type: 'period', slot: 6, label: '7', time: '03:55–04:45' },
];

export default function MasterLabTimetablePage() {
    const { selectedDeptId, setSelectedDeptId, departments } = useDepartmentContext();
    const [semesterType, setSemesterType] = useState('EVEN');
    const [academicYear, setAcademicYear] = useState(new Date().getFullYear());
    const [selectedLabId, setSelectedLabId] = useState(''); // '' = all labs
    const [viewMode, setViewMode] = useState('all'); // 'all' | 'single'

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [data, setData] = useState({ rooms: [], grid: {}, department: null });

    const printRef = useRef(null);

    const fetchTimetable = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await reportsApi.getMasterLabTimetable({
                deptId: selectedDeptId,
                semesterType,
            });
            setData(response.data);
        } catch (err) {
            console.error(err);
            setError('Failed to load master lab timetable.');
        } finally {
            setLoading(false);
        }
    }, [selectedDeptId, semesterType]);

    useEffect(() => {
        fetchTimetable();
    }, [fetchTimetable]);

    // Reset selected lab when list changes
    useEffect(() => {
        if (selectedLabId && data.rooms.length > 0) {
            const found = data.rooms.find(r => String(r.id) === String(selectedLabId));
            if (!found) setSelectedLabId('');
        }
    }, [data.rooms, selectedLabId]);

    const handlePrint = () => window.print();

    const handleDownloadCSV = () => {
        const roomsToExport = getVisibleRooms();
        let csv = "data:text/csv;charset=utf-8,";

        roomsToExport.forEach(room => {
            csv += `\r\n"${room.name}"\r\n`;
            csv += `"Day","1","2","Break","3","Lunch","4","5","Break","6","7"\r\n`;
            for (let d = 0; d < 5; d++) {
                let row = `"${DAY_SHORT[d]}"`;
                COLUMN_STRUCTURE.forEach(col => {
                    if (col.type === 'break') { row += ',""'; return; }
                    const allocs = data.grid[d]?.[col.slot]?.[room.id] || [];
                    if (allocs.length === 0) { row += ',""'; }
                    else {
                        const txt = allocs.map(a =>
                            `${a.subject_name || a.subject_code} ${a.class_name}${a.batch ? ' ' + a.batch : ''} ${a.teacher}`
                        ).join(' / ');
                        row += `,"${txt.replace(/"/g, '""')}"`;
                    }
                });
                csv += row + "\r\n";
            }
        });

        const link = document.createElement("a");
        link.setAttribute("href", encodeURI(csv));
        link.setAttribute("download", `Lab_Master_${getDeptName()}_${new Date().toISOString().split('T')[0]}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    const getDeptName = () => {
        if (!selectedDeptId) return "All Departments";
        const dept = departments.find(d => String(d.id) === String(selectedDeptId));
        return dept ? dept.name : "All Departments";
    };

    const getVisibleRooms = () => {
        if (viewMode === 'single' && selectedLabId) {
            return data.rooms.filter(r => String(r.id) === String(selectedLabId));
        }
        return data.rooms;
    };

    const renderLabTable = (room) => {
        return (
            <div key={room.id} className="lm-lab-card">
                {/* Lab Header */}
                <div className="lm-lab-card-header">
                    <div className="lm-lab-card-title">
                        <div className="lm-college-name">KR College of Engineering and Technology</div>
                        <div className="lm-dept-name">{data.department?.name || getDeptName()}</div>
                        <div className="lm-lab-meta">
                            <span>Academic Year: {academicYear}–{Number(academicYear) + 1}</span>
                            <span>Semester: {semesterType}</span>
                        </div>
                        <div className="lm-lab-room-name">
                            <Beaker size={16} />
                            {room.name}
                        </div>
                    </div>
                </div>

                {/* Classic Table */}
                <table className="lm-classic-table">
                    <thead>
                        <tr>
                            <th className="lm-day-col-header">Days</th>
                            {COLUMN_STRUCTURE.map((col, idx) => (
                                <th
                                    key={idx}
                                    className={
                                        col.type === 'break'
                                            ? (col.isLunch ? 'lm-lunch-header' : 'lm-break-header')
                                            : 'lm-period-col-header'
                                    }
                                >
                                    <div className="lm-col-label">{col.label}</div>
                                    <div className="lm-col-time">{col.time}</div>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {DAYS.map((dayName, dayIdx) => (
                            <tr key={dayIdx}>
                                <td className="lm-day-cell">{DAY_SHORT[dayIdx]}</td>
                                {COLUMN_STRUCTURE.map((col, colIdx) => {
                                    if (col.type === 'break') {
                                        return (
                                            <td key={colIdx} className={col.isLunch ? 'lm-lunch-cell' : 'lm-break-cell'}>
                                                <div className="lm-break-text">{col.label}</div>
                                            </td>
                                        );
                                    }

                                    const allocs = data.grid[dayIdx]?.[col.slot]?.[room.id] || [];

                                    if (allocs.length === 0) {
                                        return <td key={colIdx} className="lm-empty-cell"></td>;
                                    }

                                    return (
                                        <td key={colIdx} className="lm-alloc-cell">
                                            {allocs.map((a, i) => (
                                                <div key={i} className="lm-alloc-entry">
                                                    <div className="lm-alloc-subject">
                                                        {a.subject_name || a.subject_code}
                                                    </div>
                                                    <div className="lm-alloc-class">
                                                        {a.class_name}
                                                        {a.batch && <span className="lm-alloc-batch"> ({a.batch})</span>}
                                                    </div>
                                                    <div className="lm-alloc-teacher">{a.teacher}</div>
                                                </div>
                                            ))}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    const visibleRooms = getVisibleRooms();

    return (
        <div className="lab-master-page">
            {/* Header */}
            <div className="lm-header no-print">
                <div>
                    <h1>
                        <Beaker size={24} style={{ color: '#6366f1' }} />
                        Lab Master View
                    </h1>
                    <p>
                        Master scheduling view for laboratory rooms
                        {selectedDeptId && <span className="lm-dept-tag"> — {getDeptName()}</span>}
                    </p>
                </div>
                <div className="lm-header-actions">
                    <button className="btn btn-secondary" onClick={fetchTimetable} disabled={loading}>
                        <RefreshCw size={16} /> Refresh
                    </button>
                    <button className="btn btn-secondary" onClick={handleDownloadCSV} disabled={loading || data.rooms.length === 0}>
                        <Download size={16} /> Export CSV
                    </button>
                    <button className="btn btn-primary" onClick={handlePrint} disabled={loading || data.rooms.length === 0}>
                        <Printer size={16} /> Print
                    </button>
                </div>
            </div>

            {/* Filters */}
            <div className="lm-filter-bar no-print">
                <Filter size={16} style={{ color: '#6b7280', flexShrink: 0 }} />
                <div className="lm-filter-group">
                    <label>Department</label>
                    <select value={selectedDeptId || ''} onChange={e => setSelectedDeptId(e.target.value)}>
                        <option value="">All Departments</option>
                        {departments.map(d => (
                            <option key={d.id} value={d.id}>{d.name}</option>
                        ))}
                    </select>
                </div>
                <div className="lm-filter-group">
                    <label>Semester</label>
                    <select value={semesterType} onChange={e => setSemesterType(e.target.value)}>
                        <option value="ODD">ODD Semester</option>
                        <option value="EVEN">EVEN Semester</option>
                    </select>
                </div>
                <div className="lm-filter-group">
                    <label>Year</label>
                    <input
                        type="number"
                        value={academicYear}
                        onChange={(e) => setAcademicYear(e.target.value)}
                    />
                </div>
                <div className="lm-filter-group">
                    <label>Lab Room</label>
                    <select value={selectedLabId} onChange={e => {
                        setSelectedLabId(e.target.value);
                        setViewMode(e.target.value ? 'single' : 'all');
                    }}>
                        <option value="">All Labs</option>
                        {data.rooms.map(r => (
                            <option key={r.id} value={r.id}>{r.name}</option>
                        ))}
                    </select>
                </div>
                <div className="lm-filter-divider"></div>
                <div className="lm-view-toggle">
                    <button
                        className={`lm-view-btn ${viewMode === 'all' ? 'active' : ''}`}
                        onClick={() => { setViewMode('all'); setSelectedLabId(''); }}
                        title="All Labs (Stacked)"
                    >
                        <Layers size={14} /> All
                    </button>
                    <button
                        className={`lm-view-btn ${viewMode === 'single' ? 'active' : ''}`}
                        onClick={() => {
                            setViewMode('single');
                            if (!selectedLabId && data.rooms.length > 0)
                                setSelectedLabId(String(data.rooms[0].id));
                        }}
                        title="Single Lab View"
                    >
                        <Eye size={14} /> Single
                    </button>
                </div>
                {data.rooms.length > 0 && (
                    <span className="lm-room-count">
                        <Building2 size={14} />
                        {visibleRooms.length} / {data.rooms.length} lab{data.rooms.length !== 1 ? 's' : ''}
                    </span>
                )}
            </div>

            {/* Content */}
            {loading ? (
                <div className="lm-empty-state">
                    <div className="spinner"></div>
                    <p>Loading master timetable...</p>
                </div>
            ) : error ? (
                <div className="lm-error">
                    <AlertCircle size={20} />
                    <span>{error}</span>
                </div>
            ) : data.rooms.length === 0 ? (
                <div className="lm-empty-state">
                    <Beaker size={48} style={{ color: '#94a3b8' }} />
                    <h3>No Lab Rooms Found</h3>
                    <p>No labs found for the selected department. Try selecting a different department.</p>
                </div>
            ) : (
                <div className="lm-stacked-labs" ref={printRef}>
                    {visibleRooms.map(room => renderLabTable(room))}
                </div>
            )}
        </div>
    );
}
