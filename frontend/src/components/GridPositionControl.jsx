import './GridPositionControl.css';

export default function GridPositionControl({ onSelectCell, currentCell }) {
    const cells = [1, 2, 3, 4, 5, 6, 7, 8, 9];

    return (
        <div className="grid-position-control">
            <h3>Điều Khiển Theo Vị Trí Ô</h3>
            <p className="grid-description">Nhấn vào ô để di chuyển robot đến vị trí tương ứng</p>

            <div className="position-grid">
                {cells.map(cellId => (
                    <button
                        key={cellId}
                        className={`grid-cell ${currentCell === cellId ? 'active' : ''}`}
                        onClick={() => onSelectCell(cellId)}
                    >
                        <span className="cell-number">{cellId}</span>
                        <i className="fa-solid fa-crosshairs"></i>
                    </button>
                ))}
            </div>
        </div>
    );
}
