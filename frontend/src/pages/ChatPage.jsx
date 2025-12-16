import { useState, useEffect } from 'react';
import { useInventory } from '../context/InventoryContext';
import qwenAPI from '../services/qwenAPI';
import HeaderInfo from '../components/HeaderInfo';
import ChatHistory from '../components/ChatHistory';
import ChatInput from '../components/ChatInput';
import RightPanel from '../components/RightPanel';
import './ChatPage.css';

export default function ChatPage() {
    const { items, toggleDone, isLoading } = useInventory();

    // Load chat messages from localStorage (UI state only)
    const [messages, setMessages] = useState(() => {
        const saved = localStorage.getItem('robodoc-chat-messages');
        if (saved) {
            try {
                return JSON.parse(saved);
            } catch (e) {
                console.error('Failed to parse saved messages:', e);
            }
        }
        // Default greeting
        return [{
            type: 'ai',
            text: 'Hello! I am RoboDoc AI powered by Qwen. I can help you verify inventory, suggest picking routes, or check system status. How can I help you today?'
        }];
    });

    const [isTyping, setIsTyping] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [transcribingStatus, setTranscribingStatus] = useState('');
    const [interimTranscripts, setInterimTranscripts] = useState([]);
    const [sessionId] = useState(() => `session_${Date.now()}`);
    const [ollamaStatus, setOllamaStatus] = useState(null);

    // Save messages to localStorage whenever they change
    useEffect(() => {
        localStorage.setItem('robodoc-chat-messages', JSON.stringify(messages));
    }, [messages]);

    // Check Ollama status on mount
    useEffect(() => {
        checkOllamaConnection();
    }, []);

    const checkOllamaConnection = async () => {
        const status = await qwenAPI.checkOllamaStatus();
        setOllamaStatus(status);

        if (status.status !== 'connected') {
            setMessages(prev => [...prev, {
                type: 'ai',
                text: '⚠️ Warning: Cannot connect to Ollama/Qwen. Please make sure Ollama is running and the model is loaded.'
            }]);
        }
    };

    const handleSendMessage = async (text) => {
        // Add user message to UI
        setMessages(prev => [...prev, { type: 'user', text }]);
        setIsTyping(true);

        try {
            // Check for robot commands
            const lowerText = text.toLowerCase().trim();
            let robotCommandExecuted = false;

            if (lowerText === 'start' || lowerText === 'bắt đầu') {
                try {
                    const response = await qwenAPI.robotCommand('start');
                    setIsTyping(false);
                    setMessages(prev => [...prev, {
                        type: 'ai',
                        text: `✅ ${response.message}\n\nRobot đang bắt đầu lấy các sản phẩm đã đánh dấu (pick=true).`
                    }]);
                    return;
                } catch (error) {
                    robotCommandExecuted = true;
                }
            } else if (lowerText === 'stop' || lowerText === 'dừng' || lowerText === 'dừng lại') {
                try {
                    const response = await qwenAPI.robotCommand('stop');
                    setIsTyping(false);
                    setMessages(prev => [...prev, {
                        type: 'ai',
                        text: `🛑 ${response.message}\n\nRobot đã dừng lại.`
                    }]);
                    return;
                } catch (error) {
                    robotCommandExecuted = true;
                }
            } else if (lowerText === 'reset' || lowerText === 'khởi động lại') {
                try {
                    const response = await qwenAPI.robotCommand('reset');
                    setIsTyping(false);
                    setMessages(prev => [...prev, {
                        type: 'ai',
                        text: `🔄 ${response.message}\n\nInventory đã được reset về trạng thái rỗng. Settings không bị ảnh hưởng.`
                    }]);
                    // Clear chat history when resetting
                    localStorage.removeItem('robodoc-chat-messages');
                    // Reload page to refresh inventory
                    setTimeout(() => window.location.reload(), 1500);
                    return;
                } catch (error) {
                    robotCommandExecuted = true;
                }
            }

            // Prepare chat history for API (exclude initial greeting)
            const chatHistory = messages
                .slice(1)  // Skip initial greeting
                .map(msg => ({
                    role: msg.type === 'user' ? 'user' : 'assistant',
                    content: msg.text
                }));

            // Prepare inventory context
            const inventoryContext = {
                items: items,
                total: items.length,
                picked: items.filter(item => item.pick).length,
                done: items.filter(item => item.done).length
            };

            // Send to Qwen API
            const response = await qwenAPI.sendMessage(
                text,
                sessionId,
                chatHistory,
                inventoryContext
            );

            setIsTyping(false);

            // Add AI response to UI
            setMessages(prev => [...prev, {
                type: 'ai',
                text: response.response
            }]);

            // Check if inventory was updated
            if (response.inventory_updated && response.updated_inventory) {
                console.log('✅ Inventory updated via natural language');
                // Refetch inventory from backend instead of reload
                window.location.reload(); // This will trigger InventoryContext to fetch from backend
            }

        } catch (error) {
            setIsTyping(false);

            // Fallback to simple responses if API fails
            const fallbackResponse = generateFallbackResponse(text);
            setMessages(prev => [...prev, {
                type: 'ai',
                text: `⚠️ ${fallbackResponse}\n\n(Note: Unable to connect to Qwen. ${error.message})`
            }]);
        }
    };

    const handleClearChat = () => {
        localStorage.removeItem('robodoc-chat-messages');
        setMessages([{
            type: 'ai',
            text: 'Hello! I am RoboDoc AI powered by Qwen. How can I help you today?'
        }]);
    };

    const generateFallbackResponse = (userInput) => {
        const lower = userInput.toLowerCase();
        const pickedCount = items.filter(item => item.pick).length;
        const doneCount = items.filter(item => item.done).length;

        if (lower.includes('hello') || lower.includes('hi') || lower.includes('xin chào')) {
            return "Hello! I'm having trouble connecting to the AI service. Please make sure Ollama is running.";
        }
        if (lower.includes('inventory') || lower.includes('stock') || lower.includes('kho')) {
            return `Current inventory: ${items.length} items total. ${pickedCount} items are being picked, and ${doneCount} items are done.`;
        }
        if (lower.includes('picked') || lower.includes('done') || lower.includes('hoàn thành')) {
            return `There are ${pickedCount} picked items and ${doneCount} completed items right now.`;
        }
        return "I've noted your message, but I'm having trouble connecting to the AI service.";
    };

    const handleTranscribing = (isActive, status) => {
        setIsTranscribing(isActive);
        setTranscribingStatus(status);
    };

    const handleInterimTranscript = (transcript) => {
        if (transcript.isFinal) {
            setInterimTranscripts(prev => [...prev, { text: transcript.text, isFinal: true }]);
        } else {
            setInterimTranscripts(prev => {
                const newList = [...prev];
                if (newList.length > 0 && !newList[newList.length - 1].isFinal) {
                    newList.pop();
                }
                newList.push({ text: transcript.text, isFinal: false });
                return newList;
            });
        }
    };

    const exportChat = () => {
        const chatData = {
            timestamp: new Date().toISOString(),
            session_id: sessionId,
            messages: messages,
            ollama_status: ollamaStatus
        };
        const dataStr = "data:text/json;charset=utf-8," +
            encodeURIComponent(JSON.stringify(chatData, null, 2));
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute("href", dataStr);
        downloadAnchor.setAttribute("download", "chat_history.json");
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
    };

    if (isLoading) {
        return (
            <div className="loading">
                <div>Loading chat interface...</div>
                {ollamaStatus && ollamaStatus.status === 'connected' && (
                    <div style={{ fontSize: '12px', marginTop: '10px', color: 'var(--accent-green)' }}>
                        ✅ Qwen Connected: {ollamaStatus.current_model}
                    </div>
                )}
            </div>
        );
    }

    return (
        <>
            <div className="col-left">
                <HeaderInfo moduleName="Assistant Module" />

                <div className="section-header-group">
                    <div>
                        <h2 className="main-title">AI Assistant (Qwen)</h2>
                        <span className="section-title">
                            CONVERSATIONAL INTERFACE
                            {ollamaStatus && (
                                <span style={{
                                    marginLeft: '10px',
                                    color: ollamaStatus.status === 'connected' ? 'var(--accent-green)' : '#ff4757'
                                }}>
                                    {ollamaStatus.status === 'connected' ? '● Connected' : '● Disconnected'}
                                </span>
                            )}
                        </span>
                    </div>
                    <button className="btn-save" onClick={exportChat}>
                        <i className="fa-solid fa-file-export"></i> Export Chat
                    </button>
                </div>

                <div className="chat-fill-container">
                    <ChatHistory
                        messages={[...messages, ...interimTranscripts.map(t => ({
                            type: 'interim',
                            text: t.text,
                            isFinal: t.isFinal
                        }))]}
                        isTyping={isTyping || isTranscribing}
                        typingMessage={isTranscribing ? transcribingStatus : undefined}
                    />
                    <ChatInput
                        onSendMessage={handleSendMessage}
                        onInterimTranscript={handleInterimTranscript}
                    />
                </div>
            </div>

            <RightPanel items={items} onToggleDone={toggleDone} />
        </>
    );
}
