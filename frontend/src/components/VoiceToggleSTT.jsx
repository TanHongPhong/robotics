import React, { useEffect, useRef, useState } from "react";
import { io } from "socket.io-client";

// ===== audio helpers =====
function downsampleBuffer(buffer, inputRate, outputRate) {
    if (outputRate === inputRate) return buffer;
    const ratio = inputRate / outputRate;
    const newLength = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLength);

    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
        const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
        let accum = 0;
        let count = 0;
        for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
            accum += buffer[i];
            count++;
        }
        result[offsetResult] = count ? accum / count : 0;
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result;
}

function floatTo16BitPCM(float32Array) {
    const out = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
        let s = Math.max(-1, Math.min(1, float32Array[i]));
        out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
    }
    return out;
}

export default function VoiceToggleSTT({ backendUrl = "http://127.0.0.1:5000" }) {
    const [connected, setConnected] = useState(false);
    const [isRec, setIsRec] = useState(false);
    const [sessionId, setSessionId] = useState(null);

    const [interim, setInterim] = useState("");
    const [finals, setFinals] = useState([]);
    const [rawFull, setRawFull] = useState("");
    const [normalized, setNormalized] = useState("");
    const [assistant, setAssistant] = useState("");
    const [err, setErr] = useState("");

    const socketRef = useRef(null);

    const audioCtxRef = useRef(null);
    const sourceRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);

    const isRecRef = useRef(false);
    useEffect(() => { isRecRef.current = isRec; }, [isRec]);

    async function stopAudioCapture() {
        try {
            if (processorRef.current) {
                processorRef.current.onaudioprocess = null;
                processorRef.current.disconnect();
            }
            if (sourceRef.current) sourceRef.current.disconnect();
            if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
            if (audioCtxRef.current) await audioCtxRef.current.close();
        } catch { }
        processorRef.current = null;
        sourceRef.current = null;
        streamRef.current = null;
        audioCtxRef.current = null;
    }

    async function startAudioCapture() {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false,
            },
        });
        streamRef.current = stream;

        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        const audioCtx = new AudioContextClass();
        audioCtxRef.current = audioCtx;

        const source = audioCtx.createMediaStreamSource(stream);
        sourceRef.current = source;

        // buffer nhỏ -> ít lag hơn (2048 frames)
        const processor = audioCtx.createScriptProcessor(2048, 1, 1);
        processorRef.current = processor;

        const inputRate = audioCtx.sampleRate; // thường 48000
        const targetRate = 16000;

        processor.onaudioprocess = (e) => {
            if (!isRecRef.current) return;
            const socket = socketRef.current;
            if (!socket || !socket.connected) return;

            const input = e.inputBuffer.getChannelData(0);
            const down = downsampleBuffer(input, inputRate, targetRate);
            const pcm16 = floatTo16BitPCM(down);

            // gửi binary lên backend (audio_chunk)
            socket.emit("audio_chunk", { audio: pcm16.buffer });
        };

        source.connect(processor);
        processor.connect(audioCtx.destination);
    }

    useEffect(() => {
        const socket = io(backendUrl, { transports: ["websocket"] });
        socketRef.current = socket;

        socket.on("connect", () => setConnected(true));
        socket.on("disconnect", () => setConnected(false));

        socket.on("connected", (p) => setSessionId(p?.session_id ?? null));
        socket.on("stt_interim", (p) => setInterim(p?.text ?? ""));
        socket.on("stt_final", (p) => setFinals((prev) => [...prev, p?.text ?? ""]));

        socket.on("stt_stopped", async (asrPayload) => {
            // ✅ Backend đã normalize với Qwen rồi, trả về trong asrPayload.normalized
            setRawFull(asrPayload?.raw_full ?? "");
            const norm = asrPayload?.normalized ?? "";
            setNormalized(norm);
            setIsRec(false);

            // Gọi chat LLM với normalized transcript
            try {
                if (norm.trim()) {
                    const r = await fetch(`${backendUrl}/api/chat`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            message: norm,
                            session_id: sessionId ?? "default"
                        }),
                    });
                    const j = await r.json();
                    setAssistant(j?.response ?? "");
                }
            } catch (e) {
                setErr(`Chat error: ${String(e)}`);
            } finally {
                await stopAudioCapture();
            }
        });

        socket.on("error", (p) => setErr(p?.message ?? String(p)));

        return () => {
            socket.removeAllListeners();
            socket.disconnect();
            stopAudioCapture();
        };
    }, [backendUrl]); // Removed sessionId to prevent re-initialization

    async function toggle() {
        setErr("");
        const socket = socketRef.current;
        if (!socket) return;

        if (!isRec) {
            // START
            setInterim("");
            setFinals([]);
            setRawFull("");
            setNormalized("");
            setAssistant("");

            setIsRec(true);
            socket.emit("start_stt", {});
            await startAudioCapture();
        } else {
            // STOP
            setIsRec(false);
            socket.emit("stop_stt", {});
            // audio capture sẽ stop sau khi nhận stt_stopped để không mất tail quá sớm
        }
    }

    return (
        <div style={{ padding: 16, fontFamily: "system-ui", maxWidth: 800 }}>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <button onClick={toggle} disabled={!connected} style={{ padding: "10px 14px" }}>
                    {isRec ? "⏹️ Stop & Suy luận" : "🎙️ Bắt đầu nói"}
                </button>
                <div>
                    <div>Socket: {connected ? "✅ Connected" : "❌ Disconnected"}</div>
                    <div>Session: {sessionId ?? "-"}</div>
                </div>
            </div>

            {err && <div style={{ marginTop: 12, color: "crimson" }}>Error: {err}</div>}

            <div style={{ marginTop: 16 }}>
                <h3>Interim</h3>
                <div style={{ padding: 12, border: "1px solid #3333", minHeight: 40 }}>{interim}</div>
            </div>

            <div style={{ marginTop: 16 }}>
                <h3>Final segments</h3>
                <ul>
                    {finals.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
            </div>

            <div style={{ marginTop: 16 }}>
                <h3>RAW full</h3>
                <pre style={{ padding: 12, border: "1px solid #3333", whiteSpace: "pre-wrap" }}>
                    {rawFull}
                </pre>
            </div>

            <div style={{ marginTop: 16 }}>
                <h3>Qwen normalized</h3>
                <pre style={{ padding: 12, border: "1px solid #3333", whiteSpace: "pre-wrap" }}>
                    {normalized}
                </pre>
            </div>

            <div style={{ marginTop: 16 }}>
                <h3>Assistant (tuỳ chọn /api/chat)</h3>
                <pre style={{ padding: 12, border: "1px solid #3333", whiteSpace: "pre-wrap" }}>
                    {assistant}
                </pre>
            </div>
        </div>
    );
}
