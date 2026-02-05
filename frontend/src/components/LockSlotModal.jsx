/**
 * Lock Slot Modal Component
 * 
 * Modal dialog for manually locking a subject+teacher into a specific time slot.
 * Used for pre-filling timetable slots BEFORE automatic generation.
 */
import { useState, useEffect } from 'react';
import { Lock, X, Calendar, Clock, BookOpen, User, AlertTriangle, CheckCircle } from 'lucide-react';
import { fixedSlotsApi, subjectsApi, teachersApi } from '../services/api';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

const PERIODS = [
    { label: 'Period 1', time: '8:30-9:20' },
    { label: 'Period 2', time: '9:20-10:10' },
    { label: 'Period 3', time: '10:30-11:20' },
    { label: 'Period 4', time: '11:20-12:10' },
    { label: 'Period 5', time: '1:00-1:50' },
    { label: 'Period 6', time: '1:50-2:40' },
    { label: 'Period 7', time: '2:50-3:40' },
];

export default function LockSlotModal({
    isOpen,
    onClose,
    semesterId,
    semesterName,
    day,
    slot,
    onSlotLocked,
    existingTeachers = [],  // Teachers already teaching this class
    classSubjects = [],     // Subjects assigned to this class
}) {
    const [subjects, setSubjects] = useState([]);
    const [teachers, setTeachers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [validating, setValidating] = useState(false);
    const [error, setError] = useState(null);
    const [validation, setValidation] = useState(null);

    // Form state
    const [selectedSubjectId, setSelectedSubjectId] = useState('');
    const [selectedTeacherId, setSelectedTeacherId] = useState('');
    const [componentType, setComponentType] = useState('theory');
    const [lockReason, setLockReason] = useState('');

    useEffect(() => {
        if (isOpen) {
            fetchData();
            resetForm();
        }
    }, [isOpen, semesterId]);

    const fetchData = async () => {
        try {
            setLoading(true);
            const [subjectsRes, teachersRes] = await Promise.all([
                subjectsApi.getAll(),
                teachersApi.getAll(),
            ]);

            // Filter subjects to only show those assigned to this class
            const allSubjects = subjectsRes.data || [];
            const filteredSubjects = allSubjects.filter(s =>
                s.semesters?.some(sem => sem.id === semesterId)
            );

            setSubjects(filteredSubjects.length > 0 ? filteredSubjects : allSubjects);
            setTeachers(teachersRes.data || []);
        } catch (err) {
            console.error('Failed to load data:', err);
            setError('Failed to load subjects and teachers');
        } finally {
            setLoading(false);
        }
    };

    const resetForm = () => {
        setSelectedSubjectId('');
        setSelectedTeacherId('');
        setComponentType('theory');
        setLockReason('');
        setValidation(null);
        setError(null);
    };

    // Filter teachers based on selected subject
    const getAvailableTeachers = () => {
        if (!selectedSubjectId) return teachers;

        // Get the selected subject
        const subject = subjects.find(s => s.id === parseInt(selectedSubjectId));
        if (!subject) return teachers;

        // Filter teachers who teach this subject
        const teachersForSubject = teachers.filter(t => {
            const teacherSubjects = t.subjects || [];
            return teacherSubjects.some(ts => ts.id === subject.id);
        });

        return teachersForSubject.length > 0 ? teachersForSubject : teachers;
    };

    const handleSubjectChange = (e) => {
        setSelectedSubjectId(e.target.value);
        setSelectedTeacherId(''); // Reset teacher when subject changes
        setValidation(null);
    };

    const handleTeacherChange = (e) => {
        setSelectedTeacherId(e.target.value);
        setValidation(null);
    };

    const handleValidate = async () => {
        if (!selectedSubjectId || !selectedTeacherId) {
            setError('Please select both a subject and a teacher');
            return;
        }

        try {
            setValidating(true);
            setError(null);

            const res = await fixedSlotsApi.validate({
                semester_id: semesterId,
                day: day,
                slot: slot,
                subject_id: parseInt(selectedSubjectId),
                teacher_id: parseInt(selectedTeacherId),
                component_type: componentType,
            });

            setValidation(res.data);
        } catch (err) {
            console.error('Validation failed:', err);
            setError(err.response?.data?.detail?.message || 'Validation failed');
        } finally {
            setValidating(false);
        }
    };

    const handleLockSlot = async () => {
        if (!selectedSubjectId || !selectedTeacherId) {
            setError('Please select both a subject and a teacher');
            return;
        }

        try {
            setLoading(true);
            setError(null);

            await fixedSlotsApi.create({
                semester_id: semesterId,
                day: day,
                slot: slot,
                subject_id: parseInt(selectedSubjectId),
                teacher_id: parseInt(selectedTeacherId),
                component_type: componentType,
                lock_reason: lockReason || null,
                locked_by: 'admin',
            });

            onSlotLocked && onSlotLocked();
            onClose();
        } catch (err) {
            console.error('Failed to lock slot:', err);
            const detail = err.response?.data?.detail;
            if (detail?.errors) {
                setError(detail.errors.join(', '));
            } else if (detail?.message) {
                setError(detail.message);
            } else {
                setError('Failed to lock slot. Please try again.');
            }
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const availableTeachers = getAvailableTeachers();
    const canLock = selectedSubjectId && selectedTeacherId && (!validation || validation.is_valid);

    return (
        <div className="lock-slot-modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="lock-slot-modal">
                <div className="lock-slot-modal-header">
                    <h3>
                        <Lock size={20} />
                        Lock Time Slot
                    </h3>
                    <button className="lock-slot-modal-close" onClick={onClose}>
                        <X size={20} />
                    </button>
                </div>

                <div className="lock-slot-modal-body">
                    {/* Slot Information */}
                    <div className="lock-slot-info">
                        <div className="lock-slot-info-item">
                            <BookOpen size={14} />
                            <strong>{semesterName}</strong>
                        </div>
                        <div className="lock-slot-info-item">
                            <Calendar size={14} />
                            <span>{DAY_NAMES[day]}</span>
                        </div>
                        <div className="lock-slot-info-item">
                            <Clock size={14} />
                            <span>{PERIODS[slot]?.label} ({PERIODS[slot]?.time})</span>
                        </div>
                    </div>

                    {error && (
                        <div className="lock-slot-validation errors">
                            <strong>⚠️ Error:</strong> {error}
                        </div>
                    )}

                    {loading ? (
                        <div className="loading">
                            <div className="spinner"></div>
                        </div>
                    ) : (
                        <>
                            {/* Subject Selection */}
                            <div className="lock-slot-form-group">
                                <label>Select Subject</label>
                                <select
                                    value={selectedSubjectId}
                                    onChange={handleSubjectChange}
                                >
                                    <option value="">-- Choose a subject --</option>
                                    {subjects.map(subject => (
                                        <option key={subject.id} value={subject.id}>
                                            {subject.name} ({subject.code})
                                            {subject.is_elective && ' 🎯 Elective'}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {/* Teacher Selection */}
                            <div className="lock-slot-form-group">
                                <label>Select Teacher</label>
                                <select
                                    value={selectedTeacherId}
                                    onChange={handleTeacherChange}
                                    disabled={!selectedSubjectId}
                                >
                                    <option value="">-- Choose a teacher --</option>
                                    {availableTeachers.map(teacher => (
                                        <option key={teacher.id} value={teacher.id}>
                                            {teacher.name}
                                        </option>
                                    ))}
                                </select>
                                {selectedSubjectId && availableTeachers.length === 0 && (
                                    <p style={{ color: 'var(--warning)', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                                        No teachers are assigned to this subject.
                                    </p>
                                )}
                            </div>

                            {/* Component Type */}
                            <div className="lock-slot-form-group">
                                <label>Component Type</label>
                                <select
                                    value={componentType}
                                    onChange={(e) => setComponentType(e.target.value)}
                                >
                                    <option value="theory">Theory</option>
                                    <option value="lab">Lab</option>
                                    <option value="tutorial">Tutorial</option>
                                </select>
                            </div>

                            {/* Lock Reason (Optional) */}
                            <div className="lock-slot-form-group">
                                <label>Reason (Optional)</label>
                                <textarea
                                    value={lockReason}
                                    onChange={(e) => setLockReason(e.target.value)}
                                    placeholder="e.g., Teacher's preferred time slot"
                                    rows={2}
                                />
                            </div>

                            {/* Validation Results */}
                            {validation && (
                                <div className={`lock-slot-validation ${validation.is_valid ? 'warnings' : 'errors'}`}>
                                    {validation.is_valid ? (
                                        <>
                                            <strong><CheckCircle size={14} style={{ display: 'inline', verticalAlign: 'middle' }} /> Valid</strong>
                                            {validation.warnings?.length > 0 && (
                                                <>
                                                    <span> - With warnings:</span>
                                                    <ul>
                                                        {validation.warnings.map((warn, idx) => (
                                                            <li key={idx}>{warn}</li>
                                                        ))}
                                                    </ul>
                                                </>
                                            )}
                                        </>
                                    ) : (
                                        <>
                                            <strong><AlertTriangle size={14} style={{ display: 'inline', verticalAlign: 'middle' }} /> Cannot Lock</strong>
                                            <ul>
                                                {validation.errors?.map((err, idx) => (
                                                    <li key={idx}>{err}</li>
                                                ))}
                                            </ul>
                                        </>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>

                <div className="lock-slot-modal-footer">
                    <button className="lock-slot-cancel-btn" onClick={onClose}>
                        Cancel
                    </button>
                    {selectedSubjectId && selectedTeacherId && !validation && (
                        <button
                            className="lock-slot-confirm-btn"
                            onClick={handleValidate}
                            disabled={validating}
                            style={{ background: 'var(--primary-600)', borderColor: 'var(--primary-600)' }}
                        >
                            {validating ? 'Checking...' : 'Validate'}
                        </button>
                    )}
                    <button
                        className="lock-slot-confirm-btn"
                        onClick={handleLockSlot}
                        disabled={!canLock || loading}
                    >
                        <Lock size={16} />
                        {loading ? 'Locking...' : 'Lock Slot'}
                    </button>
                </div>
            </div>
        </div>
    );
}
