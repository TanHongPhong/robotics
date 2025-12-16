"""
STT Service with Deepgram + Qwen Normalization
Based on dg_vi_hotmic_qwen_toggle.py
"""
import os
import json
import time
import asyncio
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import base64

import websockets
from websockets.exceptions import ConnectionClosed
from dotenv import load_dotenv

load_dotenv()

# Deepgram Configuration
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
SAMPLE_RATE = int(os.environ.get("DG_SAMPLE_RATE", "16000"))
CHANNELS = 1
DG_MODEL = os.environ.get("DG_MODEL", "nova-3-general")
DG_LANGUAGE = os.environ.get("DG_LANGUAGE", "vi")
FLUSH_MS = int(os.environ.get("DG_FLUSH_MS", "1200"))
STOP_GRACE_S = float(os.environ.get("DG_STOP_GRACE_S", "6.0"))
STREAM_LOG_MAX = int(os.environ.get("STREAM_LOG_MAX", "600"))

# Qwen Configuration
OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
QWEN_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b-instruct")


def build_deepgram_url():
    """Build Deepgram WebSocket URL"""
    query = {
        "model": DG_MODEL,
        "language": DG_LANGUAGE,
        "encoding": "linear16",
        "sample_rate": str(SAMPLE_RATE),
        "channels": str(CHANNELS),
        "interim_results": "true",
        "punctuate": "true",
        "smart_format": "true",
        "vad_events": "true",
        "endpointing": "400",
        "utterance_end_ms": "1000",
    }
    return "wss://api.deepgram.com/v1/listen?" + urlencode(query)


def ollama_chat_once(model: str, system: str, user: str, timeout_s: int = 60) -> str:
    """Call Ollama for text normalization"""
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0.2, "top_p": 0.9},
    }
    url = f"{OLLAMA_BASE_URL}/api/chat"
    req = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("message", {}) or {}).get("content", "").strip()
    except (HTTPError, URLError, TimeoutError) as e:
        return f"[QWEN_ERROR] {type(e).__name__}: {e}"
    except Exception as e:
        return f"[QWEN_ERROR] {type(e).__name__}: {e}"


async def normalize_with_qwen(loop: asyncio.AbstractEventLoop, payload: dict) -> str:
    """Normalize transcript using Qwen"""
    system = (
        "Bạn là bộ chuẩn hoá transcript tiếng Việt từ ASR realtime. "
        "Bạn sẽ nhận được LOG streaming (interim + final), đôi khi FINAL bị thiếu chữ. "
        "Hãy dựa vào toàn bộ log để khôi phục câu nói đầy đủ nhất có thể. "
        "Nhiệm vụ: sửa lỗi chính tả/dấu, khôi phục dấu câu, bỏ lặp, làm câu tự nhiên hơn. "
        "KHÔNG bịa thêm thông tin ngoài những chữ đã xuất hiện trong log. "
        "Nếu có nhiều phiên bản khác nhau, ưu tiên phiên bản hợp lý và đầy đủ ý. "
        "Chỉ trả về 1 phiên bản câu đã chuẩn hoá (không giải thích)."
    )
    user = "ASR payload:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    return await loop.run_in_executor(None, ollama_chat_once, QWEN_MODEL, system, user, 60)


class DeepgramSTTController:
    """Deepgram STT Controller for real-time transcription"""
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.audio_q = asyncio.Queue(maxsize=2000)
        self.active = False
        self.stop_event = asyncio.Event()
        self.ws = None
        
        # Transcripts
        self.final_segments = []
        self.last_interim = ""
        self.stream_log = []
        
        # Tasks
        self.sender_task = None
        self.receiver_task = None
    
    async def start_streaming(self):
        """Start streaming to Deepgram"""
        if self.active:
            return
        
        if not DEEPGRAM_API_KEY:
            raise RuntimeError("DEEPGRAM_API_KEY not set")
        
        # Clear previous data
        while not self.audio_q.empty():
            try:
                self.audio_q.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        self.final_segments.clear()
        self.last_interim = ""
        self.stream_log.clear()
        self.stop_event.clear()
        self.active = True
        
        # Connect to Deepgram
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        url = build_deepgram_url()
        
        try:
            self.ws = await websockets.connect(
                url,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                max_size=8_000_000,
            )
        except Exception as e:
            self.active = False
            raise RuntimeError(f"Failed to connect to Deepgram: {e}")
        
        # Start sender and receiver tasks
        self.sender_task = asyncio.create_task(self._sender_loop())
        self.receiver_task = asyncio.create_task(self._receiver_loop())
    
    async def feed_audio(self, audio_base64: str):
        """Feed audio chunk from frontend"""
        if not self.active:
            return
        
        try:
            # Decode base64 to bytes
            audio_bytes = base64.b64decode(audio_base64)
            await self.audio_q.put(audio_bytes)
        except Exception as e:
            print(f"Error feeding audio: {e}")
    
    async def stop_streaming_and_collect(self) -> dict:
        """Stop streaming and collect results"""
        if not self.active:
            return {}
        
        self.stop_event.set()
        
        # Wait for sender to finish
        if self.sender_task:
            try:
                await self.sender_task
            except Exception:
                pass
        
        # Wait for receiver to finish
        if self.receiver_task:
            try:
                await self.receiver_task
            except Exception:
                pass
        
        # Close WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        
        self.ws = None
        self.active = False
        
        # Build result
        raw_full = " ".join(self.final_segments).strip()
        
        # Build spoken trace for Qwen
        lines = []
        for e in self.stream_log[-STREAM_LOG_MAX:]:
            prefix = "FINAL" if e.get("is_final") else "INTERIM"
            lines.append(f"{prefix}: {e.get('text', '')}")
        spoken_trace = "\n".join(lines).strip()
        
        return {
            "raw_full": raw_full,
            "final_segments": list(self.final_segments),
            "last_interim": self.last_interim.strip(),
            "stream_log_tail": list(self.stream_log)[-STREAM_LOG_MAX:],
            "spoken_trace": spoken_trace,
        }
    
    async def _sender_loop(self):
        """Send audio chunks to Deepgram"""
        if not self.ws:
            return
        
        flush_deadline = None
        
        try:
            while True:
                # Check if we should stop
                if self.stop_event.is_set():
                    if flush_deadline is None:
                        flush_deadline = time.monotonic() + (FLUSH_MS / 1000.0)
                    if time.monotonic() > flush_deadline:
                        break
                
                # Get audio chunk
                try:
                    chunk = await asyncio.wait_for(self.audio_q.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                
                # Send to Deepgram
                await self.ws.send(chunk)
            
            # Send close stream message
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
        
        except ConnectionClosed:
            pass
        except Exception as e:
            print(f"Sender error: {e}")
    
    async def _receiver_loop(self):
        """Receive transcripts from Deepgram"""
        if not self.ws:
            return
        
        grace_deadline = None
        
        while True:
            try:
                # Receive message from Deepgram
                msg = await asyncio.wait_for(self.ws.recv(), timeout=0.8)
                data = json.loads(msg)
                
                # Only process Results messages
                if data.get("type") != "Results":
                    continue
                
                # Extract transcript
                ch = data.get("channel") or {}
                alts = ch.get("alternatives") or []
                transcript = (alts[0].get("transcript") if alts else "") or ""
                transcript = transcript.strip()
                
                if not transcript:
                    continue
                
                is_final = bool(data.get("is_final"))
                
                # Log to stream
                self.stream_log.append({
                    "ts": time.time(),
                    "is_final": is_final,
                    "text": transcript,
                })
                
                # Trim log if too large
                if len(self.stream_log) > (STREAM_LOG_MAX * 4):
                    self.stream_log = self.stream_log[-(STREAM_LOG_MAX * 2):]
                
                # Handle transcript
                if is_final:
                    self.final_segments.append(transcript)
                    print(f"✓ FINAL: {transcript}")
                    self.last_interim = ""
                else:
                    self.last_interim = transcript
                    print(f"… INTERIM: {transcript}")
            
            except asyncio.TimeoutError:
                # Check if we should stop
                if self.stop_event.is_set():
                    if grace_deadline is None:
                        grace_deadline = time.monotonic() + STOP_GRACE_S
                    elif time.monotonic() > grace_deadline:
                        break
                continue
            
            except ConnectionClosed:
                break
            
            except Exception as e:
                print(f"Receiver error: {e}")
                if self.stop_event.is_set():
                    break
        
        return {}
