import { useState, useEffect } from 'react';
import { useInventory } from '../context/InventoryContext';
import qwenAPI from '../services/qwenAPI';
import HeaderInfo from '../components/HeaderInfo';
import ChatHistory from '../components/ChatHistory';
import ChatInput from '../components/ChatInput';
import RightPanel from '../components/RightPanel';
import './ChatPage.css';

export default function ChatPage() {
    const { items, toggleDone, isLoading, reloadInventory } = useInventory();

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
            text: 'Hello! I am RoboDoc AI powered by DeepSeek R1. I can help you verify inventory, suggest picking routes, or check system status. How can I help you today?'
        }];
    });

    const [isTyping, setIsTyping] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [transcribingStatus, setTranscribingStatus] = useState('');
    const [interimTranscripts, setInterimTranscripts] = useState([]);
    const [sessionId] = useState(() => `session_${Date.now()}`);
    const [ollamaStatus, setOllamaStatus] = useState(null);
    const [robotStatus, setRobotStatus] = useState('idle'); // idle, running, stopped

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
                text: '⚠️ Warning: Cannot connect to Ollama/DeepSeek R1. Please make sure Ollama is running and the model is loaded.'
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
                    // Lấy danh sách class_id của các ô đã chọn
                    const selectedClassIds = items
                        .filter(item => item.pick)
                        .map(item => item.class_id)
                        .filter(id => id !== undefined);

                    const response = await qwenAPI.robotCommand('start', {
                        class_ids: selectedClassIds
                    });

                    setRobotStatus('running');
                    setIsTyping(false);
                    setMessages(prev => [...prev, {
                        type: 'ai',
                        text: `✅ ${response.message}\n\nRobot đang bắt đầu lấy các sản phẩm đã đánh dấu (pick=true).\nClass IDs: [${selectedClassIds.join(', ')}]`
                    }]);
                    return;
                } catch (error) {
                    robotCommandExecuted = true;
                }
            } else if (lowerText === 'stop' || lowerText === 'dừng' || lowerText === 'dừng lại') {
                try {
                    const response = await qwenAPI.robotCommand('stop');
                    setRobotStatus('stopped');
                    setIsTyping(false);
                    setMessages(prev => [...prev, {
                        type: 'ai',
                        text: `🛑 ${response.message}\n\nRobot đã dừng lại.`
                    }]);
                    return;
                } catch (error) {
                    robotCommandExecuted = true;
                }
            } else if (lowerText === 'home' || lowerText === 'về nhà') {
                try {
                    const response = await qwenAPI.robotCommand('home');
                    setRobotStatus('idle');
                    setIsTyping(false);
                    setMessages(prev => [...prev, {
                        type: 'ai',
                        text: `✅ ${response.message}\n\nRobot đã về vị trí home.`
                    }]);
                    return;
                } catch (error) {
                    robotCommandExecuted = true;
                }
            } else if (lowerText === 'reset' || lowerText === 'khởi động lại') {
                try {
                    const response = await qwenAPI.robotCommand('reset');
                    setRobotStatus('idle');
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
                // Refetch inventory from backend without page reload
                await reloadInventory();
            }

        } catch (error) {
            setIsTyping(false);

            // Fallback to simple responses if API fails
            const fallbackResponse = generateFallbackResponse(text);
            setMessages(prev => [...prev, {
                type: 'ai',
                text: `⚠️ ${fallbackResponse}\n\n(Note: Unable to connect to DeepSeek R1. ${error.message})`
            }]);
        }
    };

    const handleClearChat = () => {
        localStorage.removeItem('robodoc-chat-messages');
        setMessages([{
            type: 'ai',
            text: 'Hello! I am RoboDoc AI powered by DeepSeek R1. How can I help you today?'
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
                        ✅ DeepSeek R1 Connected: {ollamaStatus.current_model}
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
                        <h2 className="main-title">AI Assistant (DeepSeek R1)</h2>
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
                            <span style={{
                                marginLeft: '10px',
                                color: robotStatus === 'running' ? 'var(--accent-green)' :
                                    robotStatus === 'stopped' ? '#ff4757' : '#888'
                            }}>
                                ● Robot: {robotStatus === 'running' ? 'Running' :
                                    robotStatus === 'stopped' ? 'Stopped' : 'Idle'}
                            </span>
                        </span>
                    </div>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        <button
                            className="btn-save"
                            onClick={async () => {
                                try {
                                    const response = await qwenAPI.robotCommand('home');
                                    setRobotStatus('idle');
                                    setMessages(prev => [...prev, {
                                        type: 'ai',
                                        text: `✅ ${response.message}\n\nRobot đã về vị trí home.`
                                    }]);
                                    console.log('✅ Robot homed:', response.message);
                                } catch (error) {
                                    console.error('❌ Failed to home robot:', error);
                                    setMessages(prev => [...prev, {
                                        type: 'ai',
                                        text: `❌ Không thể home robot: ${error.message}`
                                    }]);
                                }
                            }}
                            style={{ backgroundColor: '#f39c12' }}
                        >
                            <i className="fa-solid fa-home"></i> Home
                        </button>
                        <button
                            className="btn-save"
                            onClick={async () => {
                                try {
                                    // Lấy danh sách class_id của các ô đã chọn
                                    const selectedClassIds = items
                                        .filter(item => item.pick)
                                        .map(item => item.class_id)
                                        .filter(id => id !== undefined);

                                    console.log('📦 Selected class IDs:', selectedClassIds);

                                    // Gửi command start với class_ids
                                    const response = await qwenAPI.robotCommand('start', {
                                        class_ids: selectedClassIds
                                    });

                                    setRobotStatus('running');
                                    setMessages(prev => [...prev, {
                                        type: 'ai',
                                        text: `✅ ${response.message}\n\nRobot đang bắt đầu lấy các sản phẩm đã đánh dấu (pick=true).\nClass IDs: [${selectedClassIds.join(', ')}]`
                                    }]);
                                    console.log('✅ Robot started:', response.message);
                                } catch (error) {
                                    console.error('❌ Failed to start robot:', error);
                                    setMessages(prev => [...prev, {
                                        type: 'ai',
                                        text: `❌ Không thể khởi động robot: ${error.message}`
                                    }]);
                                }
                            }}
                            disabled={robotStatus === 'running'}
                            style={{ backgroundColor: 'var(--accent-blue)' }}
                        >
                            <i className="fa-solid fa-play"></i> Start
                        </button>
                        <button
                            className="btn-save"
                            onClick={async () => {
                                try {
                                    const response = await qwenAPI.robotCommand('stop');
                                    setRobotStatus('stopped');
                                    setMessages(prev => [...prev, {
                                        type: 'ai',
                                        text: `🛑 ${response.message}\n\nRobot đã dừng lại.`
                                    }]);
                                    console.log('✅ Robot stopped:', response.message);
                                } catch (error) {
                                    console.error('❌ Failed to stop robot:', error);
                                    setMessages(prev => [...prev, {
                                        type: 'ai',
                                        text: `❌ Không thể dừng robot: ${error.message}`
                                    }]);
                                }
                            }}
                            disabled={robotStatus === 'idle' || robotStatus === 'stopped'}
                            style={{ backgroundColor: '#ff4757' }}
                        >
                            <i className="fa-solid fa-stop"></i> Stop
                        </button>
                    </div>
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
