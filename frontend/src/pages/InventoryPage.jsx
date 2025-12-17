import { useState, useEffect } from 'react';
import { useInventory } from '../context/InventoryContext';
import qwenAPI from '../services/qwenAPI';
import HeaderInfo from '../components/HeaderInfo';
import ProductGrid from '../components/ProductGrid';
import RightPanel from '../components/RightPanel';
import './InventoryPage.css';

export default function InventoryPage() {
    const { items, togglePick, toggleDone, saveToBackend, isLoading } = useInventory();
    const [robotStatus, setRobotStatus] = useState('idle'); // idle, running, stopped

    // Auto-save to backend when items change
    useEffect(() => {
        if (!isLoading && items.length > 0) {
            saveToBackend();
        }
    }, [items]);

    const handleStartRobot = async () => {
        try {
            const response = await qwenAPI.robotCommand('start');
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

    const handleConfirmPick = async () => {
        const pickedItems = items.filter(item => item.pick && !item.done);
        if (pickedItems.length === 0) {
            alert('Không có sản phẩm nào được chọn để lấy!');
            return;
        }

        // Confirm and start robot
        if (confirm(`Xác nhận lấy ${pickedItems.length} sản phẩm?\n\nRobot sẽ bắt đầu lấy hàng.`)) {
            try {
                const response = await qwenAPI.robotCommand('start');
                setRobotStatus('running');
                alert(`✅ ${response.message}\n\nRobot đang lấy ${pickedItems.length} sản phẩm.`);
            } catch (error) {
                console.error('❌ Failed to start robot:', error);
                alert('Không thể khởi động robot. Vui lòng thử lại.');
            }
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
                        <h2 className="main-title">Warehouse Inventory</h2>
                        <span className="section-title">
                            REAL-TIME TRACKING
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
