/**
 * Dashboard Page
 * Displays statistics and quick actions
 */
import { useEffect, useState } from 'react';
import {
    Users,
    BookOpen,
    GraduationCap,
    Building2,
    Calendar,
    UserCheck,
    AlertCircle,
    ArrowRight,
    RefreshCw,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { dashboardApi, substitutionApi } from '../services/api';
import './Dashboard.css';

export default function Dashboard() {
    const [stats, setStats] = useState(null);
    const [recentSubs, setRecentSubs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
            const [statsRes, subsRes] = await Promise.all([
                dashboardApi.getStats(),
                dashboardApi.getRecentSubstitutions(),
            ]);
            setStats(statsRes.data);
            setRecentSubs(subsRes.data);
        } catch (err) {
            console.error('Error fetching dashboard data:', err);
            setError('Failed to load dashboard data. Make sure the backend is running.');
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="loading">
                <div className="spinner"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="alert alert-error">
                <AlertCircle size={20} />
                <span>{error}</span>
            </div>
        );
    }

    const statCards = [
        {
            label: 'Total Teachers',
            value: stats?.total_teachers || 0,
            icon: Users,
            color: 'primary',
            link: '/teachers',
        },
        {
            label: 'Total Subjects',
            value: stats?.total_subjects || 0,
            icon: BookOpen,
            color: 'success',
            link: '/subjects',
        },
        {
            label: 'Classes',
            value: stats?.total_semesters || 0,
            icon: GraduationCap,
            color: 'purple',
            link: '/semesters',
        },
        {
            label: 'Rooms',
            value: stats?.total_rooms || 0,
            icon: Building2,
            color: 'warning',
            link: '/rooms',
        },
        {
            label: 'Total Allocations',
            value: stats?.total_allocations || 0,
            icon: Calendar,
            color: 'primary',
            link: '/timetable',
        },
        {
            label: 'Active Substitutions',
            value: stats?.active_substitutions || 0,
            icon: UserCheck,
            color: stats?.active_substitutions > 0 ? 'warning' : 'success',
            link: '/substitution',
        },
    ];

    return (
        <div className="dashboard">
            <div className="page-header">
                <div>
                    <h1>Dashboard</h1>
                    <p>Welcome to the KR Timetable Generator</p>
                </div>
                <button className="btn btn-secondary" onClick={fetchData}>
                    <RefreshCw size={16} />
                    Refresh
                </button>
            </div>

            {/* Stats Grid */}
            <div className="stats-grid">
                {statCards.map((stat, idx) => (
                    <Link to={stat.link} key={idx} className="stat-card">
                        <div className={`stat-icon ${stat.color}`}>
                            <stat.icon size={24} />
                        </div>
                        <div className="stat-content">
                            <h3>{stat.value}</h3>
                            <p>{stat.label}</p>
                        </div>
                    </Link>
                ))}
            </div>

            {/* Quick Actions */}
            <div className="dashboard-grid">
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Quick Actions</h3>
                    </div>
                    <div className="quick-actions">
                        <Link to="/generate" className="quick-action-btn">
                            <RefreshCw size={20} />
                            <span>Generate Timetable</span>
                            <ArrowRight size={16} />
                        </Link>
                        <Link to="/substitution" className="quick-action-btn">
                            <UserCheck size={20} />
                            <span>Manage Substitution</span>
                            <ArrowRight size={16} />
                        </Link>
                        <Link to="/timetable" className="quick-action-btn">
                            <Calendar size={20} />
                            <span>View Timetable</span>
                            <ArrowRight size={16} />
                        </Link>
                    </div>
                </div>

                {/* Recent Substitutions */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Recent Substitutions</h3>
                        <Link to="/substitution" className="btn btn-sm btn-secondary">
                            View All
                        </Link>
                    </div>
                    {recentSubs.length === 0 ? (
                        <div className="empty-state">
                            <UserCheck size={32} />
                            <p>No recent substitutions</p>
                        </div>
                    ) : (
                        <div className="recent-list">
                            {recentSubs.map((sub, idx) => (
                                <div key={idx} className="recent-item">
                                    <div className="recent-item-icon">
                                        <UserCheck size={16} />
                                    </div>
                                    <div className="recent-item-content">
                                        <p className="recent-item-title">
                                            {sub.substitute_teacher} covering {sub.subject}
                                        </p>
                                        <p className="recent-item-meta">
                                            For {sub.original_teacher} on {sub.date}
                                        </p>
                                    </div>
                                    <span className={`badge badge-${sub.status === 'assigned' ? 'success' : 'warning'}`}>
                                        {sub.status}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Today's Alert */}
            {stats?.teachers_absent_today > 0 && (
                <div className="alert alert-warning" style={{ marginTop: '1.5rem' }}>
                    <AlertCircle size={20} />
                    <span>
                        <strong>{stats.teachers_absent_today} teacher(s)</strong> marked absent today.
                        <Link to="/substitution" style={{ marginLeft: '0.5rem' }}>
                            Manage substitutions →
                        </Link>
                    </span>
                </div>
            )}
        </div>
    );
}
