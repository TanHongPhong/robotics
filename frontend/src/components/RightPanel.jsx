import { useState } from 'react';
import StatsBadge from './StatsBadge';
import PickedItemsList from './PickedItemsList';
import Camera from './Camera';
import './RightPanel.css';

export default function RightPanel({ items, onToggleDone }) {
    // Calculate stats from items
    const totalItems = items.length;
    const pickedCount = items.filter(item => item.pick).length;
    const doneCount = items.filter(item => item.done).length;

    return (
        <div className="col-right">
            <div className="right-header-row">
                <div>
                    <span className="section-title" style={{ margin: 0, fontSize: '12px', color: 'var(--text-primary)' }}>
                        Active Picked Items
                    </span>
                    <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                        {pickedCount} Active
                    </span>
                </div>

                <div className="stats-grid-compact">
                    <StatsBadge value={totalItems} label="Total" />
                    <StatsBadge value={pickedCount} label="Pick" />
                    <StatsBadge value={doneCount} label="Done" />
                    <StatsBadge value="Mix" label="Mode" />
                </div>
            </div>

            <PickedItemsList items={items} onToggleDone={onToggleDone} />
            <Camera />
        </div>
    );
}
