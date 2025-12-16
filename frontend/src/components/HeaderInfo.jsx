import './HeaderInfo.css';

export default function HeaderInfo({ moduleName = "Inventory Module" }) {
    return (
        <div className="header-info">
            <div className="robot-profile">
                <div className="robot-icon">
                    <i className="fa-solid fa-user-doctor"></i>
                </div>
                <div className="robot-details">
                    <h2>RoboDoc AI</h2>
                    <p>{moduleName}</p>
                    <p style={{ color: 'var(--text-secondary)' }}>ID: STORE-09</p>
                </div>
            </div>
            <div className="vision-status">
                <div className="vision-icon">
                    <i className="fa-solid fa-server"></i>
                </div>
                <div>
                    <h2>System</h2>
                    <p>Online</p>
                    <div className="progress-mini">
                        <div className="progress-mini-bar"></div>
                    </div>
                </div>
            </div>
        </div>
    );
}
