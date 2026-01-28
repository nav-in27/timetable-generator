/**
 * Rooms Management Page
 * CRUD operations for rooms
 */
import { useEffect, useState } from 'react';
import { Plus, Edit2, Trash2, X, Building2, Users, AlertCircle } from 'lucide-react';
import { roomsApi } from '../services/api';
import './CrudPage.css';

export default function RoomsPage() {
    const [rooms, setRooms] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingRoom, setEditingRoom] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        capacity: 60,
        room_type: 'lecture',
        is_available: true,
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const res = await roomsApi.getAll();
            setRooms(res.data);
        } catch (err) {
            setError('Failed to load rooms');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const openModal = (room = null) => {
        if (room) {
            setEditingRoom(room);
            setFormData({
                name: room.name,
                capacity: room.capacity,
                room_type: room.room_type,
                is_available: room.is_available,
            });
        } else {
            setEditingRoom(null);
            setFormData({
                name: '',
                capacity: 60,
                room_type: 'lecture',
                is_available: true,
            });
        }
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingRoom(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            if (editingRoom) {
                await roomsApi.update(editingRoom.id, formData);
            } else {
                await roomsApi.create(formData);
            }
            fetchData();
            closeModal();
        } catch (err) {
            setError('Failed to save room');
            console.error(err);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Are you sure you want to delete this room?')) return;
        try {
            await roomsApi.delete(id);
            fetchData();
        } catch (err) {
            setError('Failed to delete room');
            console.error(err);
        }
    };

    if (loading) {
        return <div className="loading"><div className="spinner"></div></div>;
    }

    return (
        <div className="crud-page">
            <div className="page-header">
                <div>
                    <h1>Rooms</h1>
                    <p>Manage classrooms and labs</p>
                </div>
                <button className="btn btn-primary" onClick={() => openModal()}>
                    <Plus size={18} />
                    Add Room
                </button>
            </div>

            {error && (
                <div className="alert alert-error">
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            <div className="crud-grid">
                {rooms.map((room) => (
                    <div key={room.id} className={`crud-item ${!room.is_available ? 'inactive' : ''}`}>
                        <div className="crud-item-header">
                            <div>
                                <h3 className="crud-item-title">{room.name}</h3>
                                {!room.is_available && <span className="badge badge-error">Unavailable</span>}
                            </div>
                            <div className="crud-item-actions">
                                <button className="btn btn-sm btn-secondary" onClick={() => openModal(room)}>
                                    <Edit2 size={14} />
                                </button>
                                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(room.id)}>
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </div>
                        <div className="crud-item-details">
                            <span className={`badge badge-${room.room_type}`}>
                                {room.room_type}
                            </span>
                            <span className="crud-item-detail">
                                <Users size={14} /> Capacity: {room.capacity}
                            </span>
                        </div>
                    </div>
                ))}
            </div>

            {rooms.length === 0 && (
                <div className="empty-state">
                    <Building2 size={48} />
                    <h3>No Rooms Yet</h3>
                    <p>Add your first room to get started</p>
                    <button className="btn btn-primary" onClick={() => openModal()}>
                        <Plus size={18} />
                        Add Room
                    </button>
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>{editingRoom ? 'Edit Room' : 'Add Room'}</h2>
                            <button className="modal-close" onClick={closeModal}>
                                <X size={20} />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div className="form-group">
                                <label className="form-label">Room Name *</label>
                                <input
                                    type="text"
                                    className="form-input"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    required
                                    placeholder="e.g., LH-101"
                                />
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="form-label">Capacity</label>
                                    <input
                                        type="number"
                                        className="form-input"
                                        value={formData.capacity}
                                        onChange={(e) => setFormData({ ...formData, capacity: parseInt(e.target.value) })}
                                        min={1}
                                        max={500}
                                    />
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Type</label>
                                    <select
                                        className="form-select"
                                        value={formData.room_type}
                                        onChange={(e) => setFormData({ ...formData, room_type: e.target.value })}
                                    >
                                        <option value="lecture">Lecture Hall</option>
                                        <option value="lab">Laboratory</option>
                                        <option value="seminar">Seminar Room</option>
                                    </select>
                                </div>
                            </div>
                            <div className="form-group">
                                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <input
                                        type="checkbox"
                                        checked={formData.is_available}
                                        onChange={(e) => setFormData({ ...formData, is_available: e.target.checked })}
                                    />
                                    Available for scheduling
                                </label>
                            </div>
                            <div className="modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={closeModal}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    {editingRoom ? 'Update' : 'Create'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
