import { useEffect, useRef } from 'react';
import ChatMessage from './ChatMessage';
import './ChatHistory.css';

export default function ChatHistory({ messages, isTyping, typingMessage }) {
    const historyRef = useRef(null);

    useEffect(() => {
        if (historyRef.current) {
            historyRef.current.scrollTop = historyRef.current.scrollHeight;
        }
    }, [messages, isTyping]);

    return (
        <div className="chat-history" ref={historyRef}>
            {messages.map((msg, index) => (
                <ChatMessage key={index} message={msg.text} type={msg.type} />
            ))}
            {isTyping && <ChatMessage type="typing" message={typingMessage} />}
        </div>
    );
}
