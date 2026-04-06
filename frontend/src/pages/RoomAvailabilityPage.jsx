/**
 * Room Availability Dashboard
 *
 * Redesigned grid layout:
 *  - Rows = Room/Lab names
 *  - Columns = Days (Mon–Fri), each with 7 period sub-columns
 *  - Department-wise filtering
 *  - Summary & Free Room Finder views
 */
import { useEffect, useMemo, useState } from 'react';
import {
    RefreshCw, Filter, Building2, AlertTriangle, ChevronDown, ChevronRight,
    Search, Clock, CheckCircle2, XCircle, Columns3
} from 'lucide-react';
import { roomAvailabilityApi } from '../services/api';
import { useDepartmentContext } from '../context/DepartmentContext';
import './RoomAvailabilityPage.css';

const DAY_LABELS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
const DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

export default function RoomAvailabilityPage() {
    const { departments, selectedDeptId, setSelectedDeptId, deptId } = useDepartmentContext();

    // ── State ─────────────────────────────────────────────────────
    const [scheduleData, setScheduleData] = useState(null);
    const [summaryData, setSummaryData] = useState(null);
    const [freeRoomsData, setFreeRoomsData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Filters
    const [roomType, setRoomType] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [view, setView] = useState('grid'); // 'grid' | 'summary' | 'finder'

    // Free-room finder state
    const [finderDay, setFinderDay] = useState(0);
    const [finderSlot, setFinderSlot] = useState(0);
    const [finderType, setFinderType] = useState('');

    // Conflict detail panel
    const [showConflicts, setShowConflicts] = useState(false);

    // ── Data Loading ──────────────────────────────────────────────
    const loadData = async (retry = true) => {
        setLoading(true);
        setError(null);
        try {
            const params = { deptId, roomType: roomType || undefined };
            const [schedRes, summRes] = await Promise.all([
                roomAvailabilityApi.getSchedule(params),
                roomAvailabilityApi.getSummary({ deptId }),
            ]);
            setScheduleData(schedRes.data);
            setSummaryData(summRes.data);
        } catch (err) {
            console.error('Failed to load room availability', err);
            if (retry) {
                await new Promise((r) => setTimeout(r, 1500));
                return loadData(false);
            }
            setError('Unable to load room availability data. Check the server.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, [deptId, roomType]);

    // ── Free-room finder ──────────────────────────────────────────
    const loadFreeRooms = async () => {
        try {
            const res = await roomAvailabilityApi.getFreeRooms(finderDay, finderSlot, {
                deptId,
                roomType: finderType || undefined,
            });
            setFreeRoomsData(res.data);
        } catch (err) {
            console.error('Failed to load free rooms', err);
        }
    };

    useEffect(() => {
        if (view === 'finder') loadFreeRooms();
    }, [view, finderDay, finderSlot, finderType, deptId]);

    // ── Derived ───────────────────────────────────────────────────
    const slotTimings = scheduleData?.slot_timings || [];
    const numSlots = slotTimings.length || 7;

    const filteredRooms = useMemo(() => {
        if (!scheduleData?.rooms) return [];
        return scheduleData.rooms.filter((r) => {
            if (searchTerm) {
                const s = searchTerm.toLowerCase();
                if (!r.room_name.toLowerCase().includes(s)) return false;
            }
            return true;
        });
    }, [scheduleData, searchTerm]);

    // Stat aggregates
    const totalRooms = summaryData?.total_rooms ?? 0;
    const avgUtil = summaryData?.avg_utilization ?? 0;
    const totalConflicts = summaryData?.conflicts?.length ?? 0;
    const totalOccupied = (summaryData?.rooms || []).reduce((s, r) => s + r.total_occupied, 0);
    const totalFree = (summaryData?.rooms || []).reduce((s, r) => s + r.total_free, 0);

    // Current department name
    const currentDeptName = useMemo(() => {
        if (!deptId) return 'All Departments';
        const dept = departments.find(d => String(d.id) === String(deptId));
        return dept ? dept.name : 'All Departments';
    }, [deptId, departments]);

    // ── Render ────────────────────────────────────────────────────
    if (loading) {
        return <div className="loading"><div className="spinner"></div></div>;
    }

    return (
        <div className="room-availability-page">
            {/* Header */}
            <div className="page-header">
                <div>
                    <h1>Room Availability Dashboard</h1>
                    <p>
                        Real-time room schedules, free slots, and utilization analytics
                        {deptId && <span style={{ fontWeight: 600, color: 'var(--primary-700)', marginLeft: 6 }}>— {currentDeptName}</span>}
                    </p>
                </div>
                <button className="btn btn-secondary" onClick={loadData}>
                    <RefreshCw size={16} /> Refresh
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="ra-conflict-alert">
                    <AlertTriangle size={16} /> {error}
                </div>
            )}

            {/* Conflicts */}
            {totalConflicts > 0 && (
                <div>
                    <div
                        className="ra-conflict-alert"
                        onClick={() => setShowConflicts(!showConflicts)}
                        style={{ cursor: 'pointer', userSelect: 'none' }}
                    >
                        <AlertTriangle size={16} />
                        <strong>{totalConflicts} conflict(s) detected</strong> — multiple classes assigned to the same room at the same time.
                        <span style={{ marginLeft: 'auto', fontSize: '0.75rem', fontWeight: 600, opacity: 0.7 }}>
                            {showConflicts ? '▲ Hide Details' : '▼ Click to View Details'}
                        </span>
                    </div>

                    {showConflicts && (
                        <div className="ra-conflict-details">
                            {(summaryData?.conflicts || []).map((c, idx) => (
                                <div key={idx} className="ra-conflict-item">
                                    <div className="ra-conflict-item-header">
                                        <span className="ra-conflict-room">{c.room_name}</span>
                                        <span className="ra-conflict-time">
                                            {c.day_name} · {c.slot_label} ({c.slot_start}–{c.slot_end})
                                        </span>
                                        <span className="ra-conflict-count">{c.count} classes</span>
                                    </div>
                                    <div className="ra-conflict-classes">
                                        {(c.clashing_classes || []).map((cls, ci) => (
                                            <div key={ci} className="ra-conflict-class-chip">
                                                <span className="ra-conflict-subject">{cls.subject_code || cls.subject_name || '—'}</span>
                                                <span className="ra-conflict-semester">{cls.semester_code || cls.semester_name || ''}</span>
                                                {cls.teacher_name && <span className="ra-conflict-teacher">👤 {cls.teacher_name}</span>}
                                                <span className={`ra-slot-component ${cls.component || 'theory'}`}>{cls.component || 'theory'}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Filter Bar */}
            <div className="ra-filter-bar">
                <Filter size={16} style={{ color: 'var(--gray-500)', flexShrink: 0 }} />
                <input
                    type="text"
                    placeholder="Search room..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    style={{ minWidth: '180px' }}
                />
                <select value={selectedDeptId || ''} onChange={(e) => setSelectedDeptId(e.target.value)}>
                    <option value="">All Departments</option>
                    {departments.map((d) => (
                        <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                </select>
                <select value={roomType} onChange={(e) => setRoomType(e.target.value)}>
                    <option value="">All Types</option>
                    <option value="lecture">Lecture</option>
                    <option value="lab">Lab</option>
                    <option value="seminar">Seminar</option>
                </select>
            </div>

            {/* Stats */}
            <div className="ra-stats-grid">
                <div className="ra-stat-card">
                    <div className="ra-stat-icon rooms"><Building2 size={20} /></div>
                    <div className="ra-stat-content">
                        <h3>{totalRooms}</h3>
                        <p>Total Rooms</p>
                    </div>
                </div>
                <div className="ra-stat-card">
                    <div className="ra-stat-icon occupied"><XCircle size={20} /></div>
                    <div className="ra-stat-content">
                        <h3>{totalOccupied}</h3>
                        <p>Occupied Slots</p>
                    </div>
                </div>
                <div className="ra-stat-card">
                    <div className="ra-stat-icon free"><CheckCircle2 size={20} /></div>
                    <div className="ra-stat-content">
                        <h3>{totalFree}</h3>
                        <p>Free Slots</p>
                    </div>
                </div>
                <div className="ra-stat-card">
                    <div className="ra-stat-icon util"><Clock size={20} /></div>
                    <div className="ra-stat-content">
                        <h3>{avgUtil}%</h3>
                        <p>Avg Utilization</p>
                    </div>
                </div>
                {totalConflicts > 0 && (
                    <div className="ra-stat-card">
                        <div className="ra-stat-icon conflict"><AlertTriangle size={20} /></div>
                        <div className="ra-stat-content">
                            <h3>{totalConflicts}</h3>
                            <p>Conflicts</p>
                        </div>
                    </div>
                )}
            </div>

            {/* View Toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                <div className="ra-view-toggle">
                    <button className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')}>
                        <Columns3 size={14} style={{ marginRight: 4 }} />
                        Schedule Grid
                    </button>
                    <button className={view === 'summary' ? 'active' : ''} onClick={() => setView('summary')}>
                        Summary
                    </button>
                    <button className={view === 'finder' ? 'active' : ''} onClick={() => setView('finder')}>
                        Free Room Finder
                    </button>
                </div>
                {view === 'grid' && filteredRooms.length > 0 && (
                    <span className="text-xs text-muted">
                        Showing {filteredRooms.length} room{filteredRooms.length !== 1 ? 's' : ''}
                    </span>
                )}
            </div>

            {/* ─── Grid View (Transposed: Rooms as rows, Days as columns) ─── */}
            {view === 'grid' && (
                <div className="ra-grid-container">
                    {filteredRooms.length === 0 ? (
                        <div className="empty-state" style={{ padding: '3rem' }}>
                            <Building2 size={40} />
                            <h3>No rooms found</h3>
                            <p>Try adjusting your filters or select a different department.</p>
                        </div>
                    ) : (
                        <div className="ra-master-table-wrap">
                            <table className="ra-master-table">
                                <thead>
                                    <tr>
                                        <th className="ra-room-name-col" rowSpan={2}>Room</th>
                                        <th className="ra-room-info-col" rowSpan={2}>Info</th>
                                        {DAY_SHORT.map((dayName, dayIdx) => (
                                            <th
                                                key={dayIdx}
                                                className={`ra-day-header ${dayIdx % 2 === 0 ? 'even' : 'odd'}`}
                                                colSpan={numSlots}
                                            >
                                                {dayName}
                                            </th>
                                        ))}
                                    </tr>
                                    <tr>
                                        {DAY_SHORT.map((_, dayIdx) =>
                                            slotTimings.map((st) => (
                                                <th
                                                    key={`${dayIdx}-${st.slot}`}
                                                    className={`ra-period-header ${dayIdx % 2 === 0 ? 'even' : 'odd'}`}
                                                    title={`${st.start} – ${st.end}`}
                                                >
                                                    P{st.slot + 1}
                                                </th>
                                            ))
                                        )}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredRooms.map((room) => {
                                        const utilCls =
                                            room.utilization_percent > 80 ? 'high' :
                                                room.utilization_percent > 50 ? 'mid' : 'low';

                                        return (
                                            <tr key={room.room_id}>
                                                {/* Room Name */}
                                                <td className="ra-room-name-cell">
                                                    <div className="ra-room-name-inner">
                                                        <span className="ra-room-label">{room.room_name}</span>
                                                        <span className={`ra-room-type-tag ${room.room_type}`}>
                                                            {room.room_type}
                                                        </span>
                                                    </div>
                                                </td>

                                                {/* Room Info */}
                                                <td className="ra-room-info-cell">
                                                    <div className="ra-room-info-inner">
                                                        <span className="ra-cap-badge">
                                                            {room.capacity}
                                                        </span>
                                                        <div className="ra-util-bar-mini">
                                                            <div
                                                                className={`ra-util-fill ${utilCls}`}
                                                                style={{ width: `${room.utilization_percent}%` }}
                                                            />
                                                        </div>
                                                        <span className="ra-util-pct">{room.utilization_percent}%</span>
                                                    </div>
                                                </td>

                                                {/* Schedule Cells */}
                                                {DAY_SHORT.map((_, dayIdx) =>
                                                    slotTimings.map((st) => {
                                                        const cell = room.schedule?.[String(dayIdx)]?.[String(st.slot)];
                                                        const isEvenDay = dayIdx % 2 === 0;

                                                        if (!cell) {
                                                            return (
                                                                <td
                                                                    key={`${dayIdx}-${st.slot}`}
                                                                    className={`ra-cell ${isEvenDay ? 'even-day' : 'odd-day'}`}
                                                                >
                                                                    <div className="ra-cell-free">
                                                                        Free
                                                                    </div>
                                                                </td>
                                                            );
                                                        }

                                                        const compCls = cell.component || 'theory';
                                                        return (
                                                            <td
                                                                key={`${dayIdx}-${st.slot}`}
                                                                className={`ra-cell ${isEvenDay ? 'even-day' : 'odd-day'}`}
                                                                title={`${cell.subject_name || ''}\n${cell.semester_name || ''}\n${cell.teacher_name || ''}`}
                                                            >
                                                                <div className={`ra-cell-occupied comp-${compCls}`}>
                                                                    <span className="ra-cell-subject">
                                                                        {cell.subject_code || cell.subject_name?.substring(0, 8) || '—'}
                                                                    </span>
                                                                    <span className="ra-cell-class">
                                                                        {cell.semester_code || cell.semester_name?.substring(0, 10) || ''}
                                                                    </span>
                                                                </div>
                                                            </td>
                                                        );
                                                    })
                                                )}
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* ─── Summary View ──────────────────────────────────── */}
            {view === 'summary' && (
                <div className="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Room</th>
                                <th>Type</th>
                                <th>Capacity</th>
                                <th>Occupied</th>
                                <th>Free</th>
                                <th>Utilization</th>
                                <th>Peak Day</th>
                                <th>Conflicts</th>
                            </tr>
                        </thead>
                        <tbody>
                            {(summaryData?.rooms || [])
                                .filter((r) => !searchTerm || r.room_name.toLowerCase().includes(searchTerm.toLowerCase()))
                                .map((r) => (
                                    <tr key={r.room_id}>
                                        <td style={{ fontWeight: 600 }}>{r.room_name}</td>
                                        <td>
                                            <span className={`ra-room-badge ${r.room_type}`}>{r.room_type}</span>
                                        </td>
                                        <td>{r.capacity}</td>
                                        <td>{r.total_occupied}</td>
                                        <td style={{ color: '#16a34a', fontWeight: 600 }}>{r.total_free}</td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                <div className="ra-util-bar" style={{ width: 60 }}>
                                                    <div
                                                        className={`ra-util-fill ${r.utilization_percent > 80 ? 'high' : r.utilization_percent > 50 ? 'mid' : 'low'}`}
                                                        style={{ width: `${r.utilization_percent}%` }}
                                                    />
                                                </div>
                                                <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>{r.utilization_percent}%</span>
                                            </div>
                                        </td>
                                        <td>{r.peak_day || '—'}</td>
                                        <td>
                                            {r.has_conflict ? (
                                                <span style={{ color: '#dc2626', fontWeight: 700 }}>⚠ Yes</span>
                                            ) : (
                                                <span style={{ color: '#16a34a' }}>✓ None</span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            {!(summaryData?.rooms?.length) && (
                                <tr>
                                    <td colSpan="8" style={{ textAlign: 'center', color: 'var(--gray-500)' }}>
                                        No room data available.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ─── Free Room Finder View ─────────────────────────── */}
            {view === 'finder' && (
                <div className="ra-free-finder">
                    <h2>
                        <Search size={18} style={{ marginRight: 6, verticalAlign: 'middle' }} />
                        Find Available Rooms
                    </h2>
                    <div className="ra-free-finder-form">
                        <label>
                            Day
                            <select value={finderDay} onChange={(e) => setFinderDay(Number(e.target.value))}>
                                {DAY_LABELS.map((d, i) => <option key={i} value={i}>{d}</option>)}
                            </select>
                        </label>
                        <label>
                            Period
                            <select value={finderSlot} onChange={(e) => setFinderSlot(Number(e.target.value))}>
                                {slotTimings.map((st) => (
                                    <option key={st.slot} value={st.slot}>
                                        {st.label} ({st.start}–{st.end})
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label>
                            Type
                            <select value={finderType} onChange={(e) => setFinderType(e.target.value)}>
                                <option value="">Any</option>
                                <option value="lecture">Lecture</option>
                                <option value="lab">Lab</option>
                                <option value="seminar">Seminar</option>
                            </select>
                        </label>
                        <button className="btn btn-primary" onClick={loadFreeRooms} style={{ alignSelf: 'flex-end' }}>
                            <Search size={14} /> Search
                        </button>
                    </div>

                    {freeRoomsData && (
                        <>
                            <p style={{ fontSize: '0.85rem', color: 'var(--gray-600)', marginBottom: '0.6rem' }}>
                                <strong>{freeRoomsData.total_free}</strong> room(s) free on{' '}
                                <strong>{freeRoomsData.day_name}</strong> —{' '}
                                {freeRoomsData.slot_timing?.label} ({freeRoomsData.slot_timing?.start}–{freeRoomsData.slot_timing?.end})
                                {' '}| <span style={{ color: '#dc2626' }}>{freeRoomsData.total_occupied} occupied</span>
                            </p>

                            {freeRoomsData.free_rooms.length === 0 ? (
                                <p style={{ color: 'var(--gray-500)', textAlign: 'center', padding: '1.5rem' }}>
                                    No free rooms for this time slot.
                                </p>
                            ) : (
                                <div className="ra-free-rooms-grid">
                                    {freeRoomsData.free_rooms.map((r) => (
                                        <div className="ra-free-room-chip" key={r.room_id}>
                                            <CheckCircle2 size={16} style={{ color: '#16a34a', flexShrink: 0 }} />
                                            <div>
                                                <div className="room-name">{r.room_name}</div>
                                                <div className="room-meta">
                                                    {r.room_type} · cap {r.capacity}
                                                    {r.is_default_classroom && ' · default'}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
