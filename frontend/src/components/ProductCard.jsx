import './ProductCard.css';

export default function ProductCard({ item, onClick, disabled }) {
    const getIconClass = (product) => {
        if (product.includes('coca') || product.includes('pepsi') || product.includes('sprite') || product.includes('fanta')) {
            return 'fa-bottle-water';
        }
        if (product.includes('mi') || product.includes('haohao') || product.includes('omachi')) {
            return 'fa-bowl-food';
        }
        return 'fa-box-open';
    };

    const handleClick = () => {
        if (!disabled && onClick) {
            onClick();
        }
    };

    return (
        <div
            className={`product-card ${item.pick ? 'picked' : ''} ${item.done ? 'done' : ''} ${disabled ? 'disabled' : ''}`}
            onClick={handleClick}
        >
            <div className="check-mark">
                <i className="fa-solid fa-check"></i>
            </div>
            <div className="icon-box">
                <i className={`fa-solid ${getIconClass(item.product)}`}></i>
            </div>
            <h4>{item.product}</h4>
            <span>Ô {item.cell_id}</span>
            {item.done && <div className="done-badge">✓ Xong</div>}
        </div>
    );
}
