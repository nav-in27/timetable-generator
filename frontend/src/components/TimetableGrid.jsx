/**
 * Timetable Grid Component
 * Displays a weekly timetable in grid format with college timings
 * 
 * COLLEGE TIME STRUCTURE:
 * 1st Period  : 08:45 – 09:45
 * 2nd Period  : 09:45 – 10:45
 * BREAK       : 10:45 – 11:00
 * 3rd Period  : 11:00 – 12:00
 * LUNCH       : 12:00 – 01:00
 * 4th Period  : 01:00 – 02:00
 * 5th Period  : 02:00 – 02:50
 * BREAK       : 02:50 – 03:05
 * 6th Period  : 03:05 – 03:55
 * 7th Period  : 03:55 – 04:45
 */
import { Clock, User, MapPin, BookOpen, AlertTriangle, Coffee, UtensilsCrossed } from 'lucide-react';
import './TimetableGrid.css';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

// Exactly 7 periods with college timings
const PERIODS = [
    { period: 1, time: '08:45 - 09:45', label: '1st Period' },
    { period: 2, time: '09:45 - 10:45', label: '2nd Period' },
    { type: 'break', time: '10:45 - 11:00', label: 'Break' },
    { period: 3, time: '11:00 - 12:00', label: '3rd Period' },
    { type: 'lunch', time: '12:00 - 01:00', label: 'Lunch' },
    { period: 4, time: '01:00 - 02:00', label: '4th Period' },
    { period: 5, time: '02:00 - 02:50', label: '5th Period' },
    { type: 'break', time: '02:50 - 03:05', label: 'Break' },
    { period: 6, time: '03:05 - 03:55', label: '6th Period' },
    { period: 7, time: '03:55 - 04:45', label: '7th Period' },
];

// Map slot index (0-6) to period index in PERIODS array
const SLOT_TO_PERIOD_INDEX = {
    0: 0,   // Slot 0 -> Period 1 (index 0)
    1: 1,   // Slot 1 -> Period 2 (index 1)
    2: 3,   // Slot 2 -> Period 3 (index 3, after break)
    3: 5,   // Slot 3 -> Period 4 (index 5, after lunch)
    4: 6,   // Slot 4 -> Period 5 (index 6)
    5: 8,   // Slot 5 -> Period 6 (index 8, after break)
    6: 9,   // Slot 6 -> Period 7 (index 9)
};

// Subject colors based on hash of subject code
function getSubjectColor(code) {
    if (!code) return 'var(--gray-100)';

    let hash = 0;
    for (let i = 0; i < code.length; i++) {
        hash = code.charCodeAt(i) + ((hash << 5) - hash);
    }
    const colorIndex = Math.abs(hash % 10) + 1;
    return `var(--subject-${colorIndex})`;
}

export default function TimetableGrid({ timetable, viewType = 'semester' }) {
    if (!timetable || !timetable.days) {
        return (
            <div className="empty-state">
                <Clock size={48} />
                <h3>No Timetable Data</h3>
                <p>Generate a timetable to see it here.</p>
            </div>
        );
    }

    // Function to get slot data for a specific period
    const getSlotData = (day, periodIndex) => {
        // Find which slot index corresponds to this period
        for (const [slotIdx, pIdx] of Object.entries(SLOT_TO_PERIOD_INDEX)) {
            if (pIdx === periodIndex) {
                return day.slots[parseInt(slotIdx)];
            }
        }
        return null;
    };

    return (
        <div className="timetable-container">
            <div className="timetable-header-info">
                <h2>{timetable.entity_name}</h2>
                <span className="badge badge-info">{timetable.entity_type}</span>
            </div>

            <div className="timetable-grid-wrapper">
                <table className="timetable-grid">
                    <thead>
                        <tr>
                            <th className="time-header">
                                <Clock size={16} />
                                <span>Time</span>
                            </th>
                            {DAYS.map((day, idx) => (
                                <th key={idx} className="day-header">
                                    {day}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {PERIODS.map((periodInfo, periodIdx) => {
                            // Check if this is a break or lunch row
                            if (periodInfo.type === 'break') {
                                return (
                                    <tr key={`break-${periodIdx}`} className="break-row">
                                        <td className="time-cell break-cell">
                                            <Coffee size={14} />
                                            <span className="slot-time">{periodInfo.time}</span>
                                        </td>
                                        <td colSpan={5} className="break-content">
                                            <Coffee size={16} />
                                            <span>{periodInfo.label}</span>
                                        </td>
                                    </tr>
                                );
                            }

                            if (periodInfo.type === 'lunch') {
                                return (
                                    <tr key={`lunch-${periodIdx}`} className="lunch-row">
                                        <td className="time-cell lunch-cell">
                                            <UtensilsCrossed size={14} />
                                            <span className="slot-time">{periodInfo.time}</span>
                                        </td>
                                        <td colSpan={5} className="lunch-content">
                                            <UtensilsCrossed size={16} />
                                            <span>{periodInfo.label}</span>
                                        </td>
                                    </tr>
                                );
                            }

                            // Regular period row
                            return (
                                <tr key={periodIdx}>
                                    <td className="time-cell">
                                        <span className="slot-number">{periodInfo.label}</span>
                                        <span className="slot-time">{periodInfo.time}</span>
                                    </td>
                                    {timetable.days.map((day, dayIdx) => {
                                        const slot = getSlotData(day, periodIdx);
                                        const isEmpty = !slot || !slot.subject_name;
                                        const isLab = slot?.is_lab || slot?.component_type === 'lab';
                                        const isTutorial = slot?.component_type === 'tutorial';
                                        const isElective = slot?.is_elective;
                                        const isSubstituted = slot?.is_substituted;

                                        // Determine cell type class for color coding
                                        let typeClass = '';
                                        if (isEmpty) typeClass = 'free';
                                        else if (isLab) typeClass = 'lab';
                                        else if (isTutorial) typeClass = 'tutorial';
                                        else if (isElective) typeClass = 'elective';
                                        else typeClass = 'theory';

                                        return (
                                            <td
                                                key={dayIdx}
                                                className={`slot-cell ${typeClass} ${isSubstituted ? 'substituted' : ''}`}
                                            >
                                                {!isEmpty && (
                                                    <div className="slot-content">
                                                        <div className="slot-subject">
                                                            <BookOpen size={14} />
                                                            <span>{slot.subject_name}</span>
                                                        </div>
                                                        {slot.subject_code && (
                                                            <span className="slot-code">{slot.subject_code}</span>
                                                        )}

                                                        {viewType === 'semester' && slot.teacher_name && (
                                                            <div className="slot-teacher">
                                                                <User size={12} />
                                                                <span>
                                                                    {isSubstituted ? (
                                                                        <>
                                                                            <span className="original-teacher">{slot.teacher_name}</span>
                                                                            <span className="substitute-teacher">
                                                                                → {slot.substitute_teacher_name}
                                                                            </span>
                                                                        </>
                                                                    ) : (
                                                                        slot.teacher_name
                                                                    )}
                                                                </span>
                                                            </div>
                                                        )}

                                                        {slot.room_name && (
                                                            <div className="slot-room">
                                                                <MapPin size={12} />
                                                                <span>{slot.room_name}</span>
                                                            </div>
                                                        )}

                                                        <div className="slot-badges">
                                                            {isLab && (
                                                                <span className="slot-badge lab-badge">LAB</span>
                                                            )}
                                                            {isTutorial && (
                                                                <span className="slot-badge tutorial-badge">TUT</span>
                                                            )}
                                                            {isElective && (
                                                                <span className="slot-badge elective-badge">ELECTIVE</span>
                                                            )}
                                                            {isSubstituted && (
                                                                <span className="slot-badge sub-badge">
                                                                    <AlertTriangle size={10} />
                                                                    SUB
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                                {isEmpty && (
                                                    <span className="empty-slot">Free Period</span>
                                                )}
                                            </td>
                                        );
                                    })}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            <div className="timetable-legend">
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
                    <span className="legend-color free-color"></span>
                    <span>Free Period</span>
                </div>
                <div className="legend-item">
                    <span className="legend-color sub-color"></span>
                    <span>Substituted</span>
                </div>
            </div>
        </div>
    );
}
