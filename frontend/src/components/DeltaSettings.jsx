import { useState, useEffect } from 'react';
import './DeltaSettings.css';

export default function DeltaSettings({ settings, onSave }) {
    const [deltaX, setDeltaX] = useState(settings?.delta_x || 10.0);
    const [deltaY, setDeltaY] = useState(settings?.delta_y || 10.0);
    const [deltaZ, setDeltaZ] = useState(settings?.delta_z || 5.0);
    const [hasChanges, setHasChanges] = useState(false);

    useEffect(() => {
        if (settings) {
            setDeltaX(settings.delta_x);
            setDeltaY(settings.delta_y);
            setDeltaZ(settings.delta_z);
        }
    }, [settings]);

    const handleChange = (setter) => (e) => {
        setter(parseFloat(e.target.value) || 0);
        setHasChanges(true);
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter') {
            handleSave();
        }
    };

    const handleSave = () => {
        onSave({
            delta_x: deltaX,
            delta_y: deltaY,
            delta_z: deltaZ
        });
        setHasChanges(false);
    };

    return (
        <div className="delta-settings">
            <h3>Cài Đặt Delta (Bước Di Chuyển)</h3>
            <p className="delta-description">
                Điều chỉnh khoảng cách di chuyển cho mỗi lần nhấn nút. Nhấn Enter để lưu.
            </p>

            <div className="delta-inputs">
                <div className="delta-input-group">
                    <label>
                        <i className="fa-solid fa-arrows-left-right"></i>
                        Delta X (mm)
                    </label>
                    <input
                        type="number"
                        value={deltaX}
                        onChange={handleChange(setDeltaX)}
                        onKeyPress={handleKeyPress}
                        step="0.1"
                        min="0.1"
                        max="100"
                    />
                </div>

                <div className="delta-input-group">
                    <label>
                        <i className="fa-solid fa-arrows-up-down"></i>
                        Delta Y (mm)
                    </label>
                    <input
                        type="number"
                        value={deltaY}
                        onChange={handleChange(setDeltaY)}
                        onKeyPress={handleKeyPress}
                        step="0.1"
                        min="0.1"
                        max="100"
                    />
                </div>

                <div className="delta-input-group">
                    <label>
                        <i className="fa-solid fa-up-down"></i>
                        Delta Z (mm)
                    </label>
                    <input
                        type="number"
                        value={deltaZ}
                        onChange={handleChange(setDeltaZ)}
                        onKeyPress={handleKeyPress}
                        step="0.1"
                        min="0.1"
                        max="100"
                    />
                </div>
            </div>

            {hasChanges && (
                <button className="btn-save-delta" onClick={handleSave}>
                    <i className="fa-solid fa-floppy-disk"></i>
                    Lưu Cài Đặt
                </button>
            )}
        </div>
    );
}
