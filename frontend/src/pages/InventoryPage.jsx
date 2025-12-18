import { useState, useEffect } from 'react';
import { useInventory } from '../context/InventoryContext';
import qwenAPI from '../services/qwenAPI';
import HeaderInfo from '../components/HeaderInfo';
import ProductGrid from '../components/ProductGrid';
import RightPanel from '../components/RightPanel';
import './InventoryPage.css';

export default function InventoryPage() {
    const { items, togglePick, toggleDone, isLoading } = useInventory();
    const [robotStatus, setRobotStatus] = useState('idle'); // idle, running, stopped

    const handleHomeRobot = async () => {
        try {
            const response = await qwenAPI.robotCommand('home');
            setRobotStatus('idle');
            console.log('✅ Robot homed:', response.message);
        } catch (error) {
            console.error('❌ Failed to home robot:', error);
            alert('Không thể home robot. Vui lòng thử lại.');
        }
    };

    const handleStartRobot = async () => {
        try {
            // Lấy danh sách class_id của các ô đã chọn
            const selectedClassIds = items
                .filter(item => item.pick)
                .map(item => item.class_id)
                .filter(id => id !== undefined);

            console.log('📦 Selected class IDs:', selectedClassIds);

            // Gửi command start với class_ids
            const response = await qwenAPI.robotCommand('start', {
                class_ids: selectedClassIds
            });

            setRobotStatus('running');
            console.log('✅ Robot started:', response.message);
        } catch (error) {
            console.error('❌ Failed to start robot:', error);
            alert('Không thể khởi động robot. Vui lòng thử lại.');
        }
    };

    const handleStopRobot = async () => {
        try {
            const response = await qwenAPI.robotCommand('stop');
            setRobotStatus('stopped');
            console.log('✅ Robot stopped:', response.message);
        } catch (error) {
            console.error('❌ Failed to stop robot:', error);
            alert('Không thể dừng robot. Vui lòng thử lại.');
        }
    };

    if (isLoading) {
        return <div className="loading">Loading inventory data...</div>;
    }

    return (
        <>
            <div className="col-left">
                <HeaderInfo moduleName="Inventory Module" />

                <div className="section-header-group">
                    <div>
                        <h2 className="main-title">Warehouse Inventory (4x4)</h2>
                        <span className="section-title">
                            YOLO CLASS DETECTION
                            <span style={{
                                marginLeft: '10px',
                                color: robotStatus === 'running' ? 'var(--accent-green)' :
                                    robotStatus === 'stopped' ? '#ff4757' : '#888'
                            }}>
                                ● {robotStatus === 'running' ? 'Running' :
                                    robotStatus === 'stopped' ? 'Stopped' : 'Idle'}
                            </span>
                        </span>
                    </div>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        <button
                            className="btn-save"
                            onClick={handleHomeRobot}
                            style={{ backgroundColor: '#f39c12' }}
                        >
                            <i className="fa-solid fa-home"></i> Home
                        </button>
                        <button
                            className="btn-save"
                            onClick={handleStartRobot}
                            disabled={robotStatus === 'running'}
                            style={{ backgroundColor: 'var(--accent-blue)' }}
                        >
                            <i className="fa-solid fa-play"></i> Start
                        </button>
                        <button
                            className="btn-save"
                            onClick={handleStopRobot}
                            disabled={robotStatus === 'idle' || robotStatus === 'stopped'}
                            style={{ backgroundColor: '#ff4757' }}
                        >
                            <i className="fa-solid fa-stop"></i> Stop
                        </button>
                    </div>
                </div>

                <div className="grid-fill-container">
                    <ProductGrid items={items} onTogglePick={togglePick} />
                </div>
            </div>

            <RightPanel items={items} onToggleDone={toggleDone} />
        </>
    );
}
