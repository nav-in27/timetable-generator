/**
 * Sidebar Navigation Component
 * Modern sidebar with navigation links and branding
 */
import { NavLink, useLocation } from 'react-router-dom';
import {
    LayoutDashboard,
    Users,
    BookOpen,
    GraduationCap,
    Building2,
    Calendar,
    Lock,
    UserCheck,
    RefreshCw,
    Menu,
    X,
    Layers,
} from 'lucide-react';
import { useState } from 'react';
import './Sidebar.css';
import logo from '../assets/logo.png';

const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/teachers', label: 'Teachers', icon: Users },
    { path: '/subjects', label: 'Subjects', icon: BookOpen },
    { path: '/electives', label: 'Elective Baskets', icon: Layers },
    { path: '/semesters', label: 'Classes', icon: GraduationCap },
    { path: '/rooms', label: 'Rooms', icon: Building2 },
    { path: '/timetable', label: 'View Timetable', icon: Calendar },
    { path: '/manage-timetable', label: 'Manage Slots', icon: Lock },
    { path: '/substitution', label: 'Substitution', icon: UserCheck },
    { path: '/generate', label: 'Generate', icon: RefreshCw },
];

export default function Sidebar() {
    const [mobileOpen, setMobileOpen] = useState(false);
    const location = useLocation();

    return (
        <>
            {/* Mobile Menu Button */}
            <button
                className="mobile-menu-btn"
                onClick={() => setMobileOpen(!mobileOpen)}
                aria-label="Toggle menu"
            >
                {mobileOpen ? <X size={24} /> : <Menu size={24} />}
            </button>

            {/* Overlay for mobile */}
            {mobileOpen && (
                <div
                    className="sidebar-overlay"
                    onClick={() => setMobileOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
                <div className="sidebar-header">
                    <div className="logo">
                        <div className="logo-icon">
                            <img src={logo} alt="KR Logo" className="logo-image" />
                        </div>
                        <div className="logo-text">
                            <span className="logo-title">KR Timetable</span>
                            <span className="logo-subtitle">Generator</span>
                        </div>
                    </div>
                </div>

                <nav className="sidebar-nav">
                    <ul>
                        {navItems.map((item) => (
                            <li key={item.path}>
                                <NavLink
                                    to={item.path}
                                    className={({ isActive }) =>
                                        `nav-link ${isActive ? 'active' : ''}`
                                    }
                                    onClick={() => setMobileOpen(false)}
                                >
                                    <item.icon size={20} />
                                    <span>{item.label}</span>
                                </NavLink>
                            </li>
                        ))}
                    </ul>
                </nav>

                <div className="sidebar-footer">
                    <div className="sidebar-footer-content">
                        <p>KR Department</p>
                        <p className="text-xs text-muted">v1.0.0</p>
                    </div>
                </div>
            </aside>
        </>
    );
}
