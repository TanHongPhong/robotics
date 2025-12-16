import { useState, useRef, useEffect } from 'react';
import { io } from 'socket.io-client';
import './ChatInput.css';

const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5000';

export default function ChatInput({ onSendMessage }) {
    const [inputValue, setInputValue] = useState('');
    const [recordingState, setRecordingState] = useState('idle'); // idle, recording, processing
    const socketRef = useRef(null);
    const audioContextRef = useRef(null);
    const processorNodeRef = useRef(null);
    const streamRef = useRef(null);

    useEffect(() => {
        // Initialize Socket.IO connection
        socketRef.current = io(PYTHON_API_URL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
        });

        socketRef.current.on('connected', (data) => {
            console.log('Socket.IO connected:', data.session_id);
        });

        socketRef.current.on('stt_started', () => {
            console.log('STT started');
            setRecordingState('recording');
        });

        socketRef.current.on('stt_stopped', (result) => {
            console.log('STT stopped:', result);
            setRecordingState('idle');

            // Use normalized text if available
            const text = result.normalized || result.raw_full || result.last_interim || '';
            setInputValue(text);
        });

        socketRef.current.on('error', (error) => {
            console.error('Socket.IO error:', error);
            alert(`Error: ${error.message}`);
            setRecordingState('idle');
        });

        return () => {
            if (socketRef.current) {
                socketRef.current.disconnect();
            }
            stopAudioCapture();
        };
    }, []);

    const startRecording = async () => {
        if (!socketRef.current) {
            alert('Socket.IO not connected');
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });
            streamRef.current = stream;

            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });

            const source = audioContextRef.current.createMediaStreamSource(stream);
            const bufferSize = 4096;
            const processor = audioContextRef.current.createScriptProcessor(bufferSize, 1, 1);
            processorNodeRef.current = processor;

            processor.onaudioprocess = (e) => {
                const inputData = e.inputBuffer.getChannelData(0);
                const pcmData = new Int16Array(inputData.length);

                for (let i = 0; i < inputData.length; i++) {
                    const s = Math.max(-1, Math.min(1, inputData[i]));
                    pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }

                const bytes = new Uint8Array(pcmData.buffer);
                const base64 = btoa(String.fromCharCode.apply(null, bytes));

                if (socketRef.current && socketRef.current.connected) {
                    socketRef.current.emit('audio_chunk', { audio: base64 });
                }
            };

            source.connect(processor);
            processor.connect(audioContextRef.current.destination);
            socketRef.current.emit('start_stt', {});

        } catch (error) {
            console.error('Error starting recording:', error);
            alert('Cannot access microphone');
            setRecordingState('idle');
        }
    };

    const stopAudioCapture = () => {
        if (processorNodeRef.current) {
            processorNodeRef.current.disconnect();
            processorNodeRef.current = null;
        }
        if (audioContextRef.current) {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
    };

    const stopRecording = () => {
        if (!socketRef.current) return;
        setRecordingState('processing');
        stopAudioCapture();
        socketRef.current.emit('stop_stt', {});
    };

    const handleSend = () => {
        const text = inputValue.trim();
        if (text.length > 0) {
            onSendMessage(text);
            setInputValue('');
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && inputValue.trim().length > 0) {
            handleSend();
        }
    };

    const handleInputChange = (e) => {
        setInputValue(e.target.value);
    };

    // UI states
    const hasText = inputValue.trim().length > 0;
    const isIdle = recordingState === 'idle';
    const isRecording = recordingState === 'recording';
    const isProcessing = recordingState === 'processing';

    const showMicButton = !hasText && isIdle;
    const showSendButton = hasText && isIdle;
    const showStatusButton = !isIdle;

    return (
        <div className="chat-input-area">
            <div className="input-wrapper">
                <input
                    type="text"
                    value={inputValue}
                    onChange={handleInputChange}
                    onKeyPress={handleKeyPress}
                    placeholder={
                        isRecording ? '🎤 Listening...' :
                            isProcessing ? '⏳ Processing with Qwen...' :
                                'Message RoboDoc...'
                    }
                    autoComplete="off"
                    disabled={isProcessing}
                />
            </div>

            {/* Recording/Processing status button */}
            {showStatusButton && (
                <button
                    className={`btn-status ${isRecording ? 'recording' : 'processing'}`}
                    onClick={stopRecording}
                    disabled={isProcessing}
                    title={isRecording ? 'Stop recording' : 'Processing...'}
                >
                    <i className={`fa-solid ${isRecording ? 'fa-stop' : 'fa-spinner fa-spin'}`}></i>
                </button>
            )}

            {/* Mic button (when no text, like Gemini) */}
            {showMicButton && (
                <button
                    className="btn-mic-round"
                    onClick={startRecording}
                    title="Voice input (Vietnamese)"
                >
                    <i className="fa-solid fa-microphone"></i>
                </button>
            )}

            {/* Send button (when has text, like Gemini) */}
            {showSendButton && (
                <button
                    className="btn-send-round"
                    onClick={handleSend}
                    title="Send message"
                >
                    <i className="fa-solid fa-paper-plane"></i>
                </button>
            )}
        </div>
    );
}
