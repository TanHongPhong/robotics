import './ProductCard.css';

export default function ProductCard({ item, onTogglePick }) {
    const getIconClass = (product) => {
        if (product.includes('Nước') || product.includes('Sữa') || product.includes('Trà') || product.includes('Cà phê')) {
            return 'fa-bottle-water';
        }
        if (product.includes('Bánh') || product.includes('Snack') || product.includes('Kẹo')) {
            return 'fa-cookie-bite';
        }
        return 'fa-box-open';
    };

    return (
        <div
            className={`product-card ${item.pick ? 'picked' : ''}`}
            onClick={() => onTogglePick(item.cell_id)}
        >
            <div className="check-mark">
                <i className="fa-solid fa-check"></i>
            </div>
            <div className="icon-box">
                <i className={`fa-solid ${getIconClass(item.product)}`}></i>
            </div>
            <h4>{item.product}</h4>
            <span>ID: {item.cell_id}</span>
        </div>
    );
}
