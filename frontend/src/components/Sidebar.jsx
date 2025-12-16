import { Link, useLocation } from 'react-router-dom';
import { useTheme } from '../context/ThemeContext';
import './Sidebar.css';

export default function Sidebar() {
    const location = useLocation();
    const { theme, toggleTheme } = useTheme();

    return (
        <nav className="sidebar">
            <div className="logo">R</div>

            <Link to="/chat" className={`nav-item ${location.pathname === '/chat' ? 'active' : ''}`}>
                <i className="fa-solid fa-robot"></i>
            </Link>

            <Link to="/" className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}>
                <i className="fa-solid fa-basket-shopping"></i>
            </Link>

            <Link to="/settings" className={`nav-item ${location.pathname === '/settings' ? 'active' : ''}`}>
                <i className="fa-solid fa-sliders"></i>
            </Link>

            <div className="nav-item bottom-nav" onClick={toggleTheme}>
                <i className={`fa-solid ${theme === 'dark' ? 'fa-moon' : 'fa-sun'}`}></i>
            </div>
        </nav>
    );
}
