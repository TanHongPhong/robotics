import { useState } from 'react';
import { useInventory } from '../context/InventoryContext';
import HeaderInfo from '../components/HeaderInfo';
import ProductCard from '../components/ProductCard';
import RightPanel from '../components/RightPanel';
import './InventoryPage.css';

export default function InventoryPage() {
    const { items, isLoading, togglePick, toggleDone } = useInventory();
    const [mode, setMode] = useState(1); // 1 or 2
    const [isRunning, setIsRunning] = useState(false);
    const [scanStatus, setScanStatus] = useState('');

    const handleCellClick = (cellId) => {
        if (isRunning) {
            alert('Robot đang chạy! Vui lòng dừng lại trước khi thay đổi.');
            return;
        }
        togglePick(cellId);
    };

    const handleStart = async () => {
        try {
            const selectedItems = items.filter(item => item.pick);

            if (selectedItems.length === 0) {
                alert('Vui lòng chọn ít nhất một sản phẩm để lấy!');
                return;
            }

            const selectedClassIds = selectedItems.map(item => item.class_id);
            console.log(`[MODE ${mode}] Starting with selected class IDs:`, selectedClassIds);

            const response = await fetch('http://127.0.0.1:5001/api/robot/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mode: mode,
                    class_ids: selectedClassIds
                })
            });

            const data = await response.json();

            if (data.status === 'success') {
                setIsRunning(true);
                console.log(`[MODE ${mode}] Robot started:`, data.message);
            } else {
                alert(`Lỗi: ${data.message || 'Không thể khởi động robot'}`);
            }
        } catch (error) {
            console.error('Error starting robot:', error);
            alert('Lỗi kết nối đến backend!');
        }
    };

    const handleStop = async () => {
        try {
            const response = await fetch('http://127.0.0.1:5001/api/robot/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json();

            if (data.status === 'success') {
                setIsRunning(false);
                console.log('Robot stopped');
            }
        } catch (error) {
            console.error('Error stopping robot:', error);
            alert('Lỗi kết nối đến backend!');
        }
    };

    const handleHome = async () => {
        try {
            const response = await fetch('http://127.0.0.1:5001/api/robot/home', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json();

            if (data.status === 'success') {
                console.log('Robot homing');
            }
        } catch (error) {
            console.error('Error homing robot:', error);
            alert('Lỗi kết nối đến backend!');
        }
    };

    const handleModeToggle = () => {
        if (isRunning) {
            alert('Robot đang chạy! Vui lòng dừng lại trước khi chuyển mode.');
            return;
        }

        const newMode = mode === 1 ? 2 : 1;
        setMode(newMode);
        setScanStatus('');
        console.log(`Switched to MODE ${newMode}`);
    };

    const handleScan = async () => {
        if (mode !== 2) {
            alert('Chức năng SCAN chỉ hoạt động ở Mode 2!');
            return;
        }

        if (isRunning) {
            alert('Robot đang chạy! Vui lòng dừng lại trước.');
            return;
        }

        try {
            setScanStatus('Đang scan kệ...');

            const response = await fetch('http://127.0.0.1:5001/api/robot/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json();

            if (data.status === 'success') {
                setScanStatus('✅ Scan hoàn tất! Dữ liệu đã lưu.');
                console.log('Scan completed:', data);

                if (data.scan_data) {
                    console.log('Scan data received:', data.scan_data);
                }
            } else {
                setScanStatus(`❌ Lỗi: ${data.message}`);
            }
        } catch (error) {
            console.error('Error scanning:', error);
            setScanStatus('❌ Lỗi kết nối đến backend!');
        }
    };

    // Calculate statistics
    const totalItems = items?.length || 0;
    const selectedItems = items?.filter(item => item.pick).length || 0;
    const completedItems = items?.filter(item => item.done).length || 0;

    if (isLoading) {
        return (
            <div className="loading">
                <div>Đang tải...</div>
            </div>
        );
    }

    return (
        <>
            <div className="col-left">
                <HeaderInfo moduleName="Inventory Module" />

                <div className="section-header-group">
                    <div>
                        <h2 className="main-title">Shelf Inventory</h2>
                        <span className="section-title" style={{ fontSize: '9px' }}>
                            {mode === 1 ? 'Mode 1: Live Pick' : 'Mode 2: Scan then Pick'}
                            {scanStatus && <span style={{ marginLeft: '10px', color: 'var(--accent-green)' }}>{scanStatus}</span>}
                        </span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        {/* Mode Toggle */}
                        <button
                            className="btn-save"
                            onClick={handleModeToggle}
                            disabled={isRunning}
                            title={`Switch to Mode ${mode === 1 ? 2 : 1}`}
                            style={{
                                backgroundColor: mode === 2 ? '#f093fb' : '#667eea',
                                color: 'white'
                            }}
                        >
                            Mode {mode}
                        </button>

                        {/* Scan Button (Mode 2 only) */}
                        {mode === 2 && (
                            <button
                                className="btn-save"
                                onClick={handleScan}
                                disabled={isRunning}
                                title="Scan entire shelf"
                                style={{ backgroundColor: '#4facfe', color: 'white' }}
                            >
                                Scan
                            </button>
                        )}

                        {/* Home Button */}
                        <button
                            className="btn-save"
                            onClick={handleHome}
                            disabled={isRunning}
                            style={{ backgroundColor: '#f39c12' }}
                        >
                            Home
                        </button>

                        {/* Start/Stop */}
                        {!isRunning ? (
                            <button
                                className="btn-save"
                                onClick={handleStart}
                                style={{ backgroundColor: 'var(--accent-blue)' }}
                            >
                                Start
                            </button>
                        ) : (
                            <button
                                className="btn-save"
                                onClick={handleStop}
                                style={{ backgroundColor: '#ff4757' }}
                            >
                                Stop
                            </button>
                        )}
                    </div>
                </div>

                <div className="grid-fill-container">
                    <div className="product-grid">
                        {items?.map(item => (
                            <ProductCard
                                key={item.cell_id}
                                item={item}
                                onClick={() => handleCellClick(item.cell_id)}
                                disabled={isRunning}
                            />
                        ))}
                    </div>
                </div>
            </div>

            <RightPanel items={items} onToggleDone={toggleDone} />
        </>
    );
}
