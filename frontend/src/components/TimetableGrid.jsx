/**
 * Timetable Grid Component
 * Displays a weekly timetable in grid format
 */
import { Clock, User, MapPin, BookOpen, AlertTriangle } from 'lucide-react';
import './TimetableGrid.css';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
const TIME_SLOTS = [
    '9:00 - 9:50',
    '10:00 - 10:50',
    '11:00 - 11:50',
    '12:00 - 12:50',
    '2:00 - 2:50',
    '3:00 - 3:50',
    '4:00 - 4:50',
    '5:00 - 5:50',
];

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
                <Calendar size={48} />
                <h3>No Timetable Data</h3>
                <p>Generate a timetable to see it here.</p>
            </div>
        );
    }

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
                        {TIME_SLOTS.map((time, slotIdx) => (
                            <tr key={slotIdx}>
                                <td className="time-cell">
                                    <span className="slot-number">Period {slotIdx + 1}</span>
                                    <span className="slot-time">{time}</span>
                                </td>
                                {timetable.days.map((day, dayIdx) => {
                                    const slot = day.slots[slotIdx];
                                    const isEmpty = !slot || !slot.subject_name;
                                    const isLab = slot?.is_lab;
                                    const isSubstituted = slot?.is_substituted;

                                    return (
                                        <td
                                            key={dayIdx}
                                            className={`slot-cell ${isEmpty ? 'empty' : ''} ${isLab ? 'lab' : ''} ${isSubstituted ? 'substituted' : ''}`}
                                            style={!isEmpty ? {
                                                '--slot-color': getSubjectColor(slot.subject_code),
                                                borderLeftColor: getSubjectColor(slot.subject_code)
                                            } : {}}
                                        >
                                            {!isEmpty && (
                                                <div className="slot-content">
                                                    <div className="slot-subject">
                                                        <BookOpen size={14} />
                                                        <span>{slot.subject_name}</span>
                                                        {slot.subject_code && (
                                                            <span className="slot-code">{slot.subject_code}</span>
                                                        )}
                                                    </div>

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

                                                    {isLab && (
                                                        <span className="slot-badge lab-badge">LAB</span>
                                                    )}

                                                    {isSubstituted && (
                                                        <span className="slot-badge sub-badge">
                                                            <AlertTriangle size={10} />
                                                            SUB
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                            {isEmpty && (
                                                <span className="empty-slot">Free</span>
                                            )}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="timetable-legend">
                <div className="legend-item">
                    <span className="legend-color lab-color"></span>
                    <span>Lab Session</span>
                </div>
                <div className="legend-item">
                    <span className="legend-color sub-color"></span>
                    <span>Substituted Class</span>
                </div>
            </div>
        </div>
    );
}
