import './ChatResetPanel.css';

export default function ChatResetPanel({ onResetChat }) {
    const handleResetChat = () => {
        if (window.confirm(
            '⚠️ Xóa Lịch Sử Chat\n\n' +
            'Bạn có chắc muốn xóa toàn bộ lịch sử chat?\n\n' +
            '• Tất cả tin nhắn với AI sẽ bị xóa vĩnh viễn\n' +
            '• Không thể khôi phục sau khi xóa\n' +
            '• Inventory và Settings không bị ảnh hưởng\n\n' +
            'Thao tác này KHÔNG THỂ HOÀN TÁC!'
        )) {
            onResetChat();
        }
    };

    return (
        <div className="chat-reset-panel">
            <h3>Quản Lý Chat</h3>

            <div className="reset-info">
                <p className="reset-description">
                    <i className="fa-solid fa-info-circle"></i>
                    Xóa toàn bộ lịch sử chat với AI assistant. Thao tác này sẽ xóa tất cả tin nhắn đã lưu.
                </p>
            </div>

            <div className="reset-actions">
                <button className="btn-reset-chat" onClick={handleResetChat}>
                    <i className="fa-solid fa-rotate-right"></i>
                    Reset Chat History
                </button>
            </div>
        </div>
    );
}
