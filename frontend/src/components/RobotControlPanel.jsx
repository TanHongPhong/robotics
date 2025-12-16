import './RobotControlPanel.css';

export default function RobotControlPanel({ onCommand }) {
    const handleMove = (axis, direction) => {
        onCommand('move', { axis, direction });
    };

    const handleHome = () => {
        onCommand('home');
    };

    const handleReset = () => {
        if (window.confirm('Bạn có chắc muốn reset robot? Thao tác này sẽ đưa robot về vị trí ban đầu.')) {
            onCommand('reset');
        }
    };

    return (
        <div className="robot-control-panel">
            <h3>Điều Khiển Thủ Công</h3>

            {/* XYZ Controls */}
            <div className="axis-controls">
                {/* X Axis */}
                <div className="axis-group">
                    <label>X Axis</label>
                    <div className="control-buttons">
                        <button
                            className="btn-control btn-left"
                            onClick={() => handleMove('x', -1)}
                            title="Move X-"
                        >
                            <i className="fa-solid fa-arrow-left"></i>
                        </button>
                        <span className="axis-label">X</span>
                        <button
                            className="btn-control btn-right"
                            onClick={() => handleMove('x', 1)}
                            title="Move X+"
                        >
                            <i className="fa-solid fa-arrow-right"></i>
                        </button>
                    </div>
                </div>

                {/* Y Axis */}
                <div className="axis-group">
                    <label>Y Axis</label>
                    <div className="control-buttons">
                        <button
                            className="btn-control btn-up"
                            onClick={() => handleMove('y', 1)}
                            title="Move Y+"
                        >
                            <i className="fa-solid fa-arrow-up"></i>
                        </button>
                        <span className="axis-label">Y</span>
                        <button
                            className="btn-control btn-down"
                            onClick={() => handleMove('y', -1)}
                            title="Move Y-"
                        >
                            <i className="fa-solid fa-arrow-down"></i>
                        </button>
                    </div>
                </div>

                {/* Z Axis */}
                <div className="axis-group">
                    <label>Z Axis</label>
                    <div className="control-buttons">
                        <button
                            className="btn-control btn-up"
                            onClick={() => handleMove('z', 1)}
                            title="Move Z+"
                        >
                            <i className="fa-solid fa-arrow-up"></i>
                        </button>
                        <span className="axis-label">Z</span>
                        <button
                            className="btn-control btn-down"
                            onClick={() => handleMove('z', -1)}
                            title="Move Z-"
                        >
                            <i className="fa-solid fa-arrow-down"></i>
                        </button>
                    </div>
                </div>
            </div>

            {/* Action Buttons */}
            <div className="action-buttons">
                <button className="btn-action btn-home" onClick={handleHome}>
                    <i className="fa-solid fa-home"></i>
                    Về Home
                </button>
                <button className="btn-action btn-reset" onClick={handleReset}>
                    <i className="fa-solid fa-rotate-right"></i>
                    Reset Robot
                </button>
            </div>
        </div>
    );
}
