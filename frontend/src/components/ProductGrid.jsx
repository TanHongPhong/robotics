import ProductCard from './ProductCard';
import './ProductGrid.css';

export default function ProductGrid({ items, onTogglePick }) {
    return (
        <div className="product-grid">
            {items.map(item => (
                <ProductCard
                    key={item.cell_id}
                    item={item}
                    onTogglePick={onTogglePick}
                />
            ))}
        </div>
    );
}
