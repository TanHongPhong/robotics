import './StatsBadge.css';

export default function StatsBadge({ value, label }) {
    return (
        <div className="stat-badge">
            <h3>{value}</h3>
            <p>{label}</p>
        </div>
    );
}
