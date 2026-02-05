/**
 * Manage Timetable Page
 * 
 * Allows admins to view timetables and manually lock slots before generation.
 * Combines viewing with slot locking functionality.
 */
import { useEffect, useState } from 'react';
import { Calendar, Lock, Unlock, AlertCircle, RefreshCw, Trash2, Settings, User, GraduationCap } from 'lucide-react';
import { timetableApi, semestersApi, fixedSlotsApi } from '../services/api';
import LockSlotModal from '../components/LockSlotModal';
import './ManageTimetablePage.css';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

const PERIODS = [
    { period: 1, time: '08:45 - 09:45', label: '1st', slot: 0 },
    { period: 2, time: '09:45 - 10:45', label: '2nd', slot: 1 },
    { type: 'break', time: '10:45 - 11:00', label: 'Break' },
    { period: 3, time: '11:00 - 12:00', label: '3rd', slot: 2 },
    { type: 'lunch', time: '12:00 - 01:00', label: 'Lunch' },
    { period: 4, time: '01:00 - 02:00', label: '4th', slot: 3 },
    { period: 5, time: '02:00 - 02:50', label: '5th', slot: 4 },
    { type: 'break', time: '02:50 - 03:05', label: 'Break' },
    { period: 6, time: '03:05 - 03:55', label: '6th', slot: 5 },
    { period: 7, time: '03:55 - 04:45', label: '7th', slot: 6 },
];

export default function ManageTimetablePage() {
    const [semesters, setSemesters] = useState([]);
    const [selectedSemesterId, setSelectedSemesterId] = useState(null);
    const [selectedSemester, setSelectedSemester] = useState(null);
    const [timetable, setTimetable] = useState(null);
    const [fixedSlots, setFixedSlots] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [successMessage, setSuccessMessage] = useState(null);

    // Lock modal state
    const [showLockModal, setShowLockModal] = useState(false);
    const [lockSlotTarget, setLockSlotTarget] = useState({ day: null, slot: null });

    useEffect(() => {
        fetchSemesters();
    }, []);

    useEffect(() => {
        if (selectedSemesterId) {
            fetchData();
        }
    }, [selectedSemesterId]);

    const fetchSemesters = async () => {
        try {
            const res = await semestersApi.getAll();
            setSemesters(res.data || []);
            if (res.data?.length > 0) {
                setSelectedSemesterId(res.data[0].id);
                setSelectedSemester(res.data[0]);
            }
        } catch (err) {
            console.error('Failed to load semesters:', err);
            setError('Failed to load classes');
        }
    };

    const fetchData = async () => {
        try {
            setLoading(true);
            setError(null);

            const [timetableRes, fixedSlotsRes] = await Promise.all([
                timetableApi.getBySemester(selectedSemesterId).catch(() => ({ data: null })),
                fixedSlotsApi.getAll(selectedSemesterId),
            ]);

            setTimetable(timetableRes.data);
            setFixedSlots(fixedSlotsRes.data || []);

            // Update selected semester info
            const sem = semesters.find(s => s.id === selectedSemesterId);
            setSelectedSemester(sem);
        } catch (err) {
            console.error('Failed to load data:', err);
            setError('Failed to load timetable data');
        } finally {
            setLoading(false);
        }
    };

    const handleSemesterChange = (e) => {
        const id = parseInt(e.target.value);
        setSelectedSemesterId(id);
        const sem = semesters.find(s => s.id === id);
        setSelectedSemester(sem);
    };

    const handleCellClick = (day, slot) => {
        // Check if slot is already filled (by allocation or fixed slot)
        const isFixedSlot = fixedSlots.some(fs => fs.day === day && fs.slot === slot);
        const slotData = getSlotData(day, slot);
        const hasAllocation = slotData && slotData.subject_name;

        if (isFixedSlot || hasAllocation) {
            // Don't allow locking already filled slots
            return;
        }

        // Open lock modal
        setLockSlotTarget({ day, slot });
        setShowLockModal(true);
    };

    const handleUnlockSlot = async (fixedSlotId) => {
        try {
            await fixedSlotsApi.delete(fixedSlotId);
            setSuccessMessage('Slot unlocked successfully');
            setTimeout(() => setSuccessMessage(null), 3000);
            fetchData();
        } catch (err) {
            console.error('Failed to unlock slot:', err);
            setError('Failed to unlock slot');
        }
    };

    const handleClearAllFixedSlots = async () => {
        if (!window.confirm('Are you sure you want to clear ALL locked slots for this class?')) {
            return;
        }

        try {
            await fixedSlotsApi.clearSemester(selectedSemesterId);
            setSuccessMessage('All locked slots cleared');
            setTimeout(() => setSuccessMessage(null), 3000);
            fetchData();
        } catch (err) {
            console.error('Failed to clear fixed slots:', err);
            setError('Failed to clear locked slots');
        }
    };

    const handleSlotLocked = () => {
        setSuccessMessage('Slot locked successfully');
        setTimeout(() => setSuccessMessage(null), 3000);
        fetchData();
    };

    // Get slot data from timetable
    const getSlotData = (day, slot) => {
        if (!timetable || !timetable.days) return null;

        const dayData = timetable.days.find(d => d.day === day);
        if (!dayData || !dayData.slots) return null;

        return dayData.slots[slot];
    };

    // Get fixed slot for a position
    const getFixedSlot = (day, slot) => {
        return fixedSlots.find(fs => fs.day === day && fs.slot === slot);
    };

    // Render a slot cell
    const renderSlotCell = (day, slot) => {
        const slotData = getSlotData(day, slot);
        const fixedSlot = getFixedSlot(day, slot);

        // If there's a fixed slot, show it with lock indicator
        if (fixedSlot) {
            return (
                <div className="manage-slot-cell locked" key={`${day}-${slot}`}>
                    <div className="slot-lock-indicator">
                        <Lock size={14} />
                    </div>
                    <div className="slot-content">
                        <div className="slot-subject">{fixedSlot.subject_name}</div>
                        <div className="slot-code">{fixedSlot.subject_code}</div>
                        <div className="slot-teacher">{fixedSlot.teacher_name}</div>
                    </div>
                    <button
                        className="slot-unlock-btn"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleUnlockSlot(fixedSlot.id);
                        }}
                        title="Unlock this slot"
                    >
                        <Unlock size={12} /> Unlock
                    </button>
                </div>
            );
        }

        // If there's an allocation from existing timetable
        if (slotData && slotData.subject_name) {
            const isLab = slotData.is_lab || slotData.component_type === 'lab';
            const isElective = slotData.is_elective;
            const isTutorial = slotData.component_type === 'tutorial';

            let typeClass = 'theory';
            if (isLab) typeClass = 'lab';
            else if (isTutorial) typeClass = 'tutorial';
            else if (isElective) typeClass = 'elective';

            return (
                <div className={`manage-slot-cell filled ${typeClass}`} key={`${day}-${slot}`}>
                    <div className="slot-content">
                        <div className="slot-subject">{slotData.subject_name}</div>
                        <div className="slot-code">{slotData.subject_code}</div>
                        <div className="slot-teacher">{slotData.teacher_name}</div>
                        {slotData.room_name && (
                            <div className="slot-room">{slotData.room_name}</div>
                        )}
                    </div>
                </div>
            );
        }

        // Empty slot - clickable to lock
        return (
            <div
                className="manage-slot-cell empty lockable"
                key={`${day}-${slot}`}
                onClick={() => handleCellClick(day, slot)}
                title="Click to lock this slot"
            >
                <span className="empty-slot-text">
                    Click to lock
                </span>
            </div>
        );
    };

    return (
        <div className="manage-timetable-page">
            <div className="page-header">
                <div>
                    <h1>
                        <Settings size={24} />
                        Manage Timetable
                    </h1>
                    <p>Lock specific slots before automatic generation</p>
                </div>
            </div>

            {/* Controls */}
            <div className="manage-controls card">
                <div className="control-group">
                    <label className="form-label">
                        <GraduationCap size={16} />
                        Select Class
                    </label>
                    <select
                        className="form-select"
                        value={selectedSemesterId || ''}
                        onChange={handleSemesterChange}
                    >
                        <option value="">-- Select --</option>
                        {semesters.map(s => (
                            <option key={s.id} value={s.id}>
                                {s.name} ({s.code})
                            </option>
                        ))}
                    </select>
                </div>

                <div className="control-actions">
                    <button
                        className="btn btn-secondary"
                        onClick={fetchData}
                        disabled={!selectedSemesterId || loading}
                    >
                        <RefreshCw size={16} />
                        Refresh
                    </button>
                    {fixedSlots.length > 0 && (
                        <button
                            className="btn btn-danger"
                            onClick={handleClearAllFixedSlots}
                        >
                            <Trash2 size={16} />
                            Clear All Locks ({fixedSlots.length})
                        </button>
                    )}
                </div>
            </div>

            {/* Messages */}
            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            {successMessage && (
                <div className="alert alert-success">
                    {successMessage}
                </div>
            )}

            {/* Info Banner */}
            {selectedSemester && (
                <div className="info-banner">
                    <Lock size={18} />
                    <div>
                        <strong>Lock slots for {selectedSemester.name}</strong>
                        <p>
                            Click on empty cells to lock subjects into specific time slots.
                            Locked slots will be respected during automatic timetable generation.
                        </p>
                    </div>
                    <span className="lock-count">
                        {fixedSlots.length} slot{fixedSlots.length !== 1 ? 's' : ''} locked
                    </span>
                </div>
            )}

            {/* Loading */}
            {loading && (
                <div className="loading">
                    <div className="spinner"></div>
                </div>
            )}

            {/* Timetable Grid */}
            {!loading && selectedSemesterId && (
                <div className="manage-timetable-container card">
                    <div className="manage-grid-wrapper">
                        <table className="manage-timetable-grid">
                            <thead>
                                <tr>
                                    <th className="time-header">Time</th>
                                    {DAYS.map((day, idx) => (
                                        <th key={idx} className="day-header">{day}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {PERIODS.map((periodInfo, periodIdx) => {
                                    // Break row
                                    if (periodInfo.type === 'break') {
                                        return (
                                            <tr key={`break-${periodIdx}`} className="break-row">
                                                <td className="time-cell">{periodInfo.time}</td>
                                                <td colSpan={5} className="break-content">
                                                    ☕ {periodInfo.label}
                                                </td>
                                            </tr>
                                        );
                                    }

                                    // Lunch row
                                    if (periodInfo.type === 'lunch') {
                                        return (
                                            <tr key={`lunch-${periodIdx}`} className="lunch-row">
                                                <td className="time-cell">{periodInfo.time}</td>
                                                <td colSpan={5} className="lunch-content">
                                                    🍽️ {periodInfo.label}
                                                </td>
                                            </tr>
                                        );
                                    }

                                    // Regular period row
                                    return (
                                        <tr key={periodIdx}>
                                            <td className="time-cell">
                                                <div className="period-label">{periodInfo.label}</div>
                                                <div className="period-time">{periodInfo.time}</div>
                                            </td>
                                            {DAYS.map((_, dayIdx) => (
                                                <td key={dayIdx} className="slot-cell-wrapper">
                                                    {renderSlotCell(dayIdx, periodInfo.slot)}
                                                </td>
                                            ))}
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>

                    {/* Legend */}
                    <div className="manage-legend">
                        <div className="legend-item">
                            <span className="legend-color locked-color"></span>
                            <span>Locked</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-color theory-color"></span>
                            <span>Theory</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-color lab-color"></span>
                            <span>Lab</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-color elective-color"></span>
                            <span>Elective</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-color empty-color"></span>
                            <span>Empty (Click to Lock)</span>
                        </div>
                    </div>
                </div>
            )}

            {/* No Selection */}
            {!selectedSemesterId && (
                <div className="card empty-state">
                    <Calendar size={48} />
                    <h3>Select a Class</h3>
                    <p>Choose a class from the dropdown above to manage slot locks.</p>
                </div>
            )}

            {/* Lock Slot Modal */}
            <LockSlotModal
                isOpen={showLockModal}
                onClose={() => setShowLockModal(false)}
                semesterId={selectedSemesterId}
                semesterName={selectedSemester ? `${selectedSemester.name} (${selectedSemester.code})` : ''}
                day={lockSlotTarget.day}
                slot={lockSlotTarget.slot}
                onSlotLocked={handleSlotLocked}
            />
        </div>
    );
}
