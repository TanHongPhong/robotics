import './ChatMessage.css';

export default function ChatMessage({ message, type }) {
    if (type === 'user') {
        return (
            <div className="message user">
                <div className="content">{message}</div>
            </div>
        );
    }

    if (type === 'typing') {
        return (
            <div className="message ai">
                <div className="avatar">
                    <i className="fa-solid fa-robot"></i>
                </div>
                <div className="content">
                    {message ? (
                        <span style={{ fontStyle: 'italic', color: 'var(--text-secondary)' }}>
                            {message}
                        </span>
                    ) : (
                        <div className="typing-indicator">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    if (type === 'interim') {
        // message is an object with { text, isFinal } from ChatPage
        const messageText = typeof message === 'string' ? message : message.text;
        const messageIsFinal = typeof message === 'object' ? message.isFinal : false;

        const prefix = messageIsFinal ? '✓' : '…';
        const style = {
            fontStyle: 'italic',
            color: messageIsFinal ? 'var(--text-primary)' : 'var(--text-secondary)',
            opacity: messageIsFinal ? 1 : 0.8
        };

        return (
            <div className="message user" style={{ opacity: messageIsFinal ? 1 : 0.7 }}>
                <div className="content" style={style}>
                    <span style={{ marginRight: '5px' }}>{prefix}</span>
                    {messageText}
                </div>
            </div>
        );
    }

    return (
        <div className="message ai">
            <div className="avatar">
                <i className="fa-solid fa-robot"></i>
            </div>
            <div className="content">{message}</div>
        </div>
    );
}
