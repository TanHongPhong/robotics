import './PickedItemsList.css';

export default function PickedItemsList({ items, onToggleDone }) {
    const pickedItems = items.filter(item => item.pick && item.product && item.product.trim() !== "");

    return (
        <div className="picked-section">
            <div className="horizontal-grid">
                {pickedItems.map(item => {
                    const statusText = item.done ? 'DONE' : 'PICKING...';
                    const percentText = item.done ? '100%' : '50%';
                    const textClass = item.done ? 'status-text-done' : 'status-text-picking';
                    const barClass = item.done ? 'done' : 'picking';

                    return (
                        <div
                            key={item.cell_id}
                            className="category-card"
                            onClick={() => onToggleDone && onToggleDone(item.cell_id)}
                        >
                            <div className="cat-title">{item.product}</div>
                            <div className="cat-info">
                                <div className={`cat-status-row ${textClass}`}>
                                    <span>{statusText}</span>
                                    <span>{percentText}</span>
                                </div>
                                <div className="cat-progress-bg">
                                    <div
                                        className={`cat-fill ${barClass}`}
                                        style={{ width: item.done ? '100%' : '50%' }}
                                    ></div>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
