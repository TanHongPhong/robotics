import { useState, useEffect } from 'react';
import qwenAPI from '../services/qwenAPI';
import HeaderInfo from '../components/HeaderInfo';
import RobotControlPanel from '../components/RobotControlPanel';
import GridPositionControl from '../components/GridPositionControl';
import DeltaSettings from '../components/DeltaSettings';
import ChatResetPanel from '../components/ChatResetPanel';
import Camera from '../components/Camera';
import './SettingsPage.css';

export default function SettingsPage() {
    const [settings, setSettings] = useState(null);
    const [currentCell, setCurrentCell] = useState(null);
    const [robotPosition, setRobotPosition] = useState({ x: 0, y: 0, z: 0 });
    const [commandLog, setCommandLog] = useState([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            const response = await fetch('/data/settings.json');
            const data = await response.json();
            setSettings(data.robot_settings);
            setRobotPosition(data.robot_settings.home_position);
            setIsLoading(false);
        } catch (error) {
            console.error('Error loading settings:', error);
            // Fallback settings
            setSettings({
                home_position: { x: 0, y: 0, z: 0 },
                delta_adjustments: { delta_x: 10, delta_y: 10, delta_z: 5 },
                grid_positions: {}
            });
            setIsLoading(false);
        }
    };

    const addLog = (message) => {
        const timestamp = new Date().toLocaleTimeString('vi-VN');
        setCommandLog(prev => [{
            time: timestamp,
            message
        }, ...prev].slice(0, 10)); // Keep last 10 logs
    };

    const handleResetData = async () => {
        if (!confirm('⚠️ Bạn có chắc muốn reset toàn bộ dữ liệu?\n\n- Inventory sẽ bị xóa trống\n- Settings sẽ về mặc định\n\nThao tác này KHÔNG THỂ HOÀN TÁC!')) {
            return;
        }

        try {
            addLog('🔄 Đang reset dữ liệu...');

            // Reset both inventory and settings
            await Promise.all([
                qwenAPI.resetInventory(),
                qwenAPI.resetSettings()
            ]);

            addLog('✅ Reset thành công! Đang tải lại trang...');

            // Reload page after 1 second
            setTimeout(() => {
                window.location.reload();
            }, 1000);

        } catch (error) {
            console.error('Reset failed:', error);
            addLog('❌ Reset thất bại: ' + error.message);
            alert('Không thể reset dữ liệu. Vui lòng thử lại.');
        }
    };

    const handleRobotCommand = (command, params = {}) => {
        switch (command) {
            case 'move':
                const { axis, direction } = params;
                const delta = settings.delta_adjustments[`delta_${axis}`] || 10;
                const newPos = { ...robotPosition };
                newPos[axis] += direction * delta;

                setRobotPosition(newPos);
                addLog(`Di chuyển ${axis.toUpperCase()}${direction > 0 ? '+' : ''}${direction * delta}mm → (${newPos.x}, ${newPos.y}, ${newPos.z})`);

                // TODO: Send to robot controller
                console.log('Robot move:', { axis, value: direction * delta, newPosition: newPos });
                break;

            case 'home':
                const homePos = settings.home_position;
                setRobotPosition(homePos);
                setCurrentCell(null);
                addLog(`Robot về Home → (${homePos.x}, ${homePos.y}, ${homePos.z})`);

                // TODO: Send to robot controller
                console.log('Robot home:', homePos);
                break;

            case 'reset':
                const resetPos = settings.home_position;
                setRobotPosition(resetPos);
                setCurrentCell(null);
                addLog('🔄 RESET: Robot đã được khởi động lại');

                // TODO: Send reset command to robot
                console.log('Robot reset');
                break;

            default:
                addLog(`⚠️ Unknown command: ${command}`);
        }
    };

    const handleSelectCell = (cellId) => {
        const cellKey = `cell_${cellId}`;
        const targetPos = settings.grid_positions[cellKey];

        if (targetPos) {
            setRobotPosition(targetPos);
            setCurrentCell(cellId);
            addLog(`Đi đến Ô ${cellId} → (${targetPos.x}, ${targetPos.y}, ${targetPos.z})`);

            // TODO: Send to robot controller
            console.log('Robot move to cell:', cellId, targetPos);
        }
    };

    const handleSaveDelta = async (newDeltas) => {
        try {
            // Update local state
            setSettings({
                ...settings,
                delta_adjustments: newDeltas
            });

            // Save to file (this would need a backend endpoint)
            const updatedSettings = {
                robot_settings: {
                    ...settings,
                    delta_adjustments: newDeltas
                },
                last_updated: new Date().toISOString()
            };

            addLog(`✅ Đã lưu Delta: X=${newDeltas.delta_x}, Y=${newDeltas.delta_y}, Z=${newDeltas.delta_z}mm`);

            // TODO: Send to backend to save settings.json
            console.log('Save settings:', updatedSettings);

            // For now, save to localStorage as backup
            localStorage.setItem('robot-settings', JSON.stringify(updatedSettings));

        } catch (error) {
            console.error('Error saving settings:', error);
            addLog('❌ Lỗi khi lưu cài đặt');
        }
    };

    const handleResetChat = () => {
        localStorage.removeItem('robodoc-chat-messages');
        addLog('✅ Đã xóa lịch sử chat');
        alert('✅ Đã xóa lịch sử chat thành công!\n\nVui lòng vào trang Chat để thấy thay đổi.');
    };

    if (isLoading) {
        return <div className="loading">Loading robot settings...</div>;
    }

    return (
        <>
            <div className="col-left">
                <HeaderInfo moduleName="Robot Control" />

                <div className="section-header-group">
                    <div>
                        <h2 className="main-title">Điều Khiển Robot</h2>
                        <span className="section-title">MANUAL CONTROL INTERFACE</span>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                        <div className="robot-status">
                            <span className="status-label">Position:</span>
                            <span className="status-value">
                                X: {robotPosition.x.toFixed(1)} |
                                Y: {robotPosition.y.toFixed(1)} |
                                Z: {robotPosition.z.toFixed(1)} mm
                            </span>
                        </div>
                    </div>
                </div>

                <div className="settings-content">
                    <GridPositionControl
                        onSelectCell={handleSelectCell}
                        currentCell={currentCell}
                    />
                    <RobotControlPanel onCommand={handleRobotCommand} />
                    <ChatResetPanel onResetChat={handleResetChat} />
                    <DeltaSettings
                        settings={settings.delta_adjustments}
                        onSave={handleSaveDelta}
                    />
                </div>
            </div>

            <div className="col-right">
                <div className="log-panel">
                    <h3>
                        <i className="fa-solid fa-list"></i>
                        Command Log
                    </h3>
                    <div className="log-entries">
                        {commandLog.length === 0 ? (
                            <div className="log-empty">Chưa có lệnh nào được thực hiện</div>
                        ) : (
                            commandLog.map((log, index) => (
                                <div key={index} className="log-entry">
                                    <span className="log-time">{log.time}</span>
                                    <span className="log-message">{log.message}</span>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                <div className="camera-panel">
                    <Camera />
                </div>
            </div>
        </>
    );
}
