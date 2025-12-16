#!/usr/bin/env python3
# dg_vi_hotmic_qwen_toggle.py
# Hot mic always ON. Press ENTER to toggle:
#   - START: connect + stream audio to Deepgram realtime
#   - STOP : flush tail audio, close stream,
#            send the WHOLE streaming trace (interim + final) to Qwen for normalization.
#
# This version REMOVES the "best" heuristic. Goal: speed + fidelity.
# We just pass the raw streaming process to Qwen so it can reconstruct missing words.
#
# Requirements:
#   pip install sounddevice websockets python-dotenv
#   (Optional for Qwen via Ollama) install Ollama + `ollama pull qwen2.5:1.5b-instruct`
#
# Env:
#   DEEPGRAM_API_KEY=...
#   OLLAMA_BASE_URL=http://localhost:11434
#   QWEN_MODEL=qwen2.5:1.5b-instruct

import os
import json
import time
import asyncio
import threading
import queue
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import sounddevice as sd
import websockets
from websockets.exceptions import ConnectionClosed

# Try importing pyttsx3 for TTS support (optional)
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

from dotenv import load_dotenv
load_dotenv()

# ======================
# Config
# ======================
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
if not DEEPGRAM_API_KEY:
    raise RuntimeError("DEEPGRAM_API_KEY not set in environment/.env")

SAMPLE_RATE = int(os.environ.get("DG_SAMPLE_RATE", "16000"))
CHANNELS = int(os.environ.get("DG_CHANNELS", "1"))
DTYPE = os.environ.get("DG_DTYPE", "int16")   # raw PCM 16-bit
BLOCK_MS = int(os.environ.get("DG_BLOCK_MS", "50"))
BLOCK_SAMPLES = int(SAMPLE_RATE * BLOCK_MS / 1000)

PRINT_INTERIM = os.environ.get("DG_PRINT_INTERIM", "1").strip() not in ("0", "false", "False")

# Flush tail audio on STOP (helps avoid missing trailing words)
FLUSH_MS = int(os.environ.get("DG_FLUSH_MS", "1200"))  # 1.2s default
STOP_GRACE_S = float(os.environ.get("DG_STOP_GRACE_S", "6.0"))  # wait for finalization after stop

# Keep last N streaming events to limit payload size
STREAM_LOG_MAX = int(os.environ.get("DG_STREAM_LOG_MAX", "600"))

DG_QUERY = {
    "model": os.environ.get("DG_MODEL", "nova-3-general"),
    "language": os.environ.get("DG_LANGUAGE", "vi"),
    "encoding": "linear16",
    "sample_rate": str(SAMPLE_RATE),
    "channels": str(CHANNELS),
    "interim_results": "true",
    "punctuate": "true",
    "smart_format": "true",
    "vad_events": "true",
    "endpointing": os.environ.get("DG_ENDPOINTING", "400"),
    "utterance_end_ms": os.environ.get("DG_UTTERANCE_END_MS", "1000"),
}
DG_URL = "wss://api.deepgram.com/v1/listen?" + urlencode(DG_QUERY)

# Qwen (Ollama)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen2.5:1.5b-instruct").strip()
# Two-stage Qwen (optional):
#  - Stage 1: normalize/clean transcript
#  - Stage 2: answer the user (TTS-friendly)
QWEN_NORM_MODEL = os.environ.get("QWEN_NORM_MODEL", QWEN_MODEL).strip()
QWEN_ANS_MODEL  = os.environ.get("QWEN_ANS_MODEL",  QWEN_MODEL).strip()
USE_QWEN_NORM = os.environ.get("USE_QWEN_NORM", "1").strip() not in ("0", "false", "False")
USE_QWEN_ANS  = os.environ.get("USE_QWEN_ANS",  "1").strip() not in ("0", "false", "False")
USE_QWEN = USE_QWEN_NORM or USE_QWEN_ANS  # backward-compatible flag for prints

# Text-to-speech (speaker) output
USE_TTS = os.environ.get("USE_TTS", "1").strip() not in ("0", "false", "False")
TTS_RATE = int(os.environ.get("TTS_RATE", "175"))  # speech rate (pyttsx3)
TTS_VOICE_HINT = os.environ.get("TTS_VOICE_HINT", "vi")  # try match: "vi", "Vietnam", etc.


# ======================
# Helpers
# ======================
def pick_default_input_device():
    try:
        return sd.default.device[0]  # input
    except Exception:
        return None


def list_input_devices():
    devices = sd.query_devices()
    inputs = []
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            inputs.append((i, d["name"], d["max_input_channels"]))
    return inputs


def drain_queue(q: asyncio.Queue):
    """Drain queue quickly (best effort)."""
    try:
        while True:
            q.get_nowait()
    except asyncio.QueueEmpty:
        return


def ollama_chat_once(base_url: str, model: str, system: str, user: str, timeout_s: int = 60) -> str:
    """Sync call to Ollama /api/chat (no extra deps)."""
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0.2, "top_p": 0.9},
    }
    url = f"{base_url}/api/chat"
    req = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return (data.get("message", {}) or {}).get("content", "").strip()
    except (HTTPError, URLError, TimeoutError) as e:
        return f"[QWEN_ERROR] {type(e).__name__}: {e}"
    except Exception as e:
        return f"[QWEN_ERROR] {type(e).__name__}: {e}"


async def normalize_with_qwen(loop: asyncio.AbstractEventLoop, payload: dict) -> str:
    """Run Ollama call in executor to avoid blocking the event loop."""
    system = (
        "Bạn là bộ chuẩn hoá transcript tiếng Việt từ ASR realtime. "
        "Bạn sẽ nhận được LOG streaming (interim + final), đôi khi FINAL bị thiếu chữ. "
        "Hãy dựa vào toàn bộ log để khôi phục câu nói đầy đủ nhất có thể. "
        "Nhiệm vụ: sửa lỗi chính tả/dấu, khôi phục dấu câu, bỏ lặp, làm câu tự nhiên hơn. "
        "KHÔNG bịa thêm thông tin ngoài những chữ đã xuất hiện trong log. "
        "Nếu có nhiều phiên bản khác nhau, ưu tiên phiên bản hợp lý và đầy đủ ý, ưu tiên các phiên bản cuối cùng. "
        "Chỉ trả về 1 phiên bản câu đã chuẩn hoá (không giải thích)."
    )
    user = "ASR payload:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    return await loop.run_in_executor(None, ollama_chat_once, OLLAMA_BASE_URL, QWEN_NORM_MODEL, system, user, 60)




async def answer_with_qwen(loop: asyncio.AbstractEventLoop, normalized_text: str) -> str:
    """Stage-2 Qwen: produce a TTS-friendly answer."""
    system = (
        "Bạn là trợ lý hội thoại tiếng Việt. "
        "Bạn sẽ nhận được câu nói người dùng đã được chuẩn hoá từ ASR. "
        "Hãy trả lời đúng ý người dùng, ngắn gọn, tự nhiên, dễ đọc ra loa. "
        "Không dùng markdown, không liệt kê dài dòng. "
        "Nếu người dùng ra lệnh mà thiếu thông tin (ví dụ không rõ vật gì/bao nhiêu), "
        "hãy hỏi lại đúng 1 câu để làm rõ."
    )
    user = "Câu người dùng (đã chuẩn hoá):\n" + (normalized_text or "")
    return await loop.run_in_executor(None, ollama_chat_once, OLLAMA_BASE_URL, QWEN_ANS_MODEL, system, user, 60)

class TTSWorker:
    """Non-blocking TTS playback via a background thread.

    - Uses pyttsx3 (offline) if available.
    - Queue-based so your asyncio loop stays responsive.
    """

    def __init__(self, voice_hint: str = "vi", rate: int = 175):
        self.voice_hint = (voice_hint or "").lower().strip()
        self.rate = rate
        self.q: "queue.Queue[str|None]" = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _pick_voice(self, engine):
        try:
            voices = engine.getProperty("voices") or []
        except Exception:
            return
        if not voices:
            print("⚠️ Không tìm thấy giọng nói nào trong hệ thống")
            return

        hint = self.voice_hint
        if not hint:
            return

        def score(v):
            blob = " ".join(
                [str(getattr(v, "id", "")), str(getattr(v, "name", "")), str(getattr(v, "languages", ""))]
            ).lower()
            s = 0
            # Ưu tiên giọng tiếng Việt
            if "vi" in hint or "viet" in hint:
                if "vietnam" in blob:
                    s += 10
                if "vi-vn" in blob:
                    s += 8
                if "vietnamese" in blob:
                    s += 7
                if "vi" in blob:
                    s += 5
                if "viet" in blob:
                    s += 4
            if hint in blob:
                s += 3
            return s

        best = max(voices, key=score)
        best_score = score(best)
        
        # In thông tin về giọng đã chọn
        print(f"🔊 Đang sử dụng giọng TTS: {getattr(best, 'name', 'Unknown')}")
        if best_score == 0:
            print("⚠️ Không tìm thấy giọng tiếng Việt, sử dụng giọng mặc định")
            print("💡 Để cài giọng tiếng Việt: Settings → Time & Language → Speech → Add Vietnamese")
        
        if best_score > 0:
            try:
                engine.setProperty("voice", best.id)
            except Exception:
                pass

    def _worker(self):
        if pyttsx3 is None:
            # TTS not available; just drain queue
            while True:
                item = self.q.get()
                if item is None:
                    break
            return

        try:
            engine = pyttsx3.init()
            try:
                engine.setProperty("rate", self.rate)
            except Exception:
                pass
            self._pick_voice(engine)

            while True:
                text = self.q.get()
                if text is None:
                    break
                text = (text or "").strip()
                if not text:
                    continue
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception:
                    # If engine glitches, re-init once
                    try:
                        engine.stop()
                    except Exception:
                        pass
                    try:
                        engine = pyttsx3.init()
                        engine.setProperty("rate", self.rate)
                        self._pick_voice(engine)
                        engine.say(text)
                        engine.runAndWait()
                    except Exception:
                        pass
        except Exception:
            # Can't init engine; just drain queue
            while True:
                item = self.q.get()
                if item is None:
                    break

    def speak(self, text: str):
        self.q.put(text)

    def close(self):
        self.q.put(None)
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass


class HotMicDeepgramController:
    def __init__(self, loop: asyncio.AbstractEventLoop, device: int):
        self.loop = loop
        self.device = device

        # hot mic capture queue (50ms blocks -> 20 blocks/sec)
        self.audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2000)
        self.stream: sd.RawInputStream | None = None

        # streaming state
        self.active = False
        self.stop_event = asyncio.Event()
        self.ws = None

        # tasks
        self.sender_task: asyncio.Task | None = None
        self.receiver_task: asyncio.Task | None = None

        # transcripts
        self.final_segments: list[str] = []
        self.last_interim: str = ""
        self.interim_updates: list[str] = []  # unique interim updates (for quick view)
        self.stream_log: list[dict] = []       # full trace (tail)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print("[AUDIO]", status, flush=True)
        b = bytes(indata)
        try:
            self.audio_q.put_nowait(b)
        except asyncio.QueueFull:
            # drop oldest then add new (best effort)
            try:
                _ = self.audio_q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.audio_q.put_nowait(b)
            except Exception:
                pass

    def start_hot_mic(self):
        if self.stream is not None:
            return
        self.stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SAMPLES,
            device=self.device,
            callback=self._audio_callback,
        )
        self.stream.start()

    async def start_streaming(self):
        if self.active:
            return

        drain_queue(self.audio_q)
        self.final_segments.clear()
        self.last_interim = ""
        self.interim_updates.clear()
        self.stream_log.clear()

        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        self.stop_event.clear()
        self.active = True

        try:
            self.ws = await websockets.connect(
                DG_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                max_size=8_000_000,
            )
        except Exception:
            self.active = False
            raise

        self.sender_task = asyncio.create_task(self._sender_loop(), name="dg_sender")
        self.receiver_task = asyncio.create_task(self._receiver_loop(), name="dg_receiver")

    async def stop_streaming_and_collect(self) -> dict:
        if not self.active:
            return {}

        self.stop_event.set()

        if self.sender_task:
            try:
                await self.sender_task
            except Exception:
                pass

        receiver_out = {}
        if self.receiver_task:
            try:
                receiver_out = await self.receiver_task
            except Exception:
                receiver_out = {}

        try:
            if self.ws is not None:
                await self.ws.close()
        except Exception:
            pass

        self.ws = None
        self.active = False

        raw_full = " ".join(self.final_segments).strip()

        # Build a compact "spoken trace" string from stream_log_tail
        # (helps Qwen read quickly without parsing big JSON only)
        lines = []
        for e in self.stream_log[-STREAM_LOG_MAX:]:
            prefix = "FINAL" if e.get("is_final") else "INTERIM"
            lines.append(f"{prefix}: {e.get('text','')}")
        spoken_trace = "\n".join(lines).strip()

        return {
            "raw_full": raw_full,
            "final_segments": list(self.final_segments),
            "last_interim": self.last_interim.strip(),
            "interim_updates": list(self.interim_updates)[-200:],  # keep last 200 updates
            "stream_log_tail": list(self.stream_log)[-STREAM_LOG_MAX:],
            "spoken_trace": spoken_trace,
            "receiver_out": receiver_out,
            "dg_query": DG_QUERY,
        }

    async def _sender_loop(self):
        assert self.ws is not None
        flush_deadline = None
        try:
            while True:
                if self.stop_event.is_set():
                    if flush_deadline is None:
                        flush_deadline = time.monotonic() + (FLUSH_MS / 1000.0)
                    if time.monotonic() > flush_deadline:
                        break

                try:
                    chunk = await asyncio.wait_for(self.audio_q.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                await self.ws.send(chunk)

            # CloseStream as TEXT frame
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
        except ConnectionClosed:
            pass

    async def _receiver_loop(self) -> dict:
        assert self.ws is not None
        grace_deadline = None
        while True:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=0.8)
                data = json.loads(msg)

                if data.get("type") != "Results":
                    continue

                ch = data.get("channel") or {}
                alts = ch.get("alternatives") or []
                transcript = (alts[0].get("transcript") if alts else "") or ""
                transcript = transcript.strip()
                if not transcript:
                    continue

                is_final = bool(data.get("is_final"))

                # stream trace
                self.stream_log.append({
                    "ts": time.time(),
                    "is_final": is_final,
                    "text": transcript,
                })
                if len(self.stream_log) > (STREAM_LOG_MAX * 4):
                    self.stream_log = self.stream_log[-(STREAM_LOG_MAX * 2):]

                if is_final:
                    self.final_segments.append(transcript)
                    if PRINT_INTERIM:
                        print("✓", transcript, flush=True)
                    # reset last interim between segments
                    self.last_interim = ""
                else:
                    # track last interim + unique updates
                    if transcript != self.last_interim:
                        self.interim_updates.append(transcript)
                        if len(self.interim_updates) > 800:
                            self.interim_updates = self.interim_updates[-400:]
                        self.last_interim = transcript
                        if PRINT_INTERIM:
                            print("…", transcript, flush=True)

            except asyncio.TimeoutError:
                if self.stop_event.is_set():
                    if grace_deadline is None:
                        grace_deadline = time.monotonic() + STOP_GRACE_S
                    elif time.monotonic() > grace_deadline:
                        break
                continue
            except ConnectionClosed:
                break
            except Exception:
                if self.stop_event.is_set():
                    break

        return {"final_count": len(self.final_segments), "log_tail": len(self.stream_log[-STREAM_LOG_MAX:])}


# ======================
# Main
# ======================
async def run():
    device = pick_default_input_device()
    if device is None:
        print("Unable to get default mic. Available input devices:")
        for i, name, ch in list_input_devices():
            print(f"  [{i}] {name} (channels={ch})")
        raise RuntimeError("Please set sd.default.device = (input_id, output_id) or choose device manually.")

    loop = asyncio.get_running_loop()
    ctl = HotMicDeepgramController(loop, device=device)
    ctl.start_hot_mic()

    # ===== TTS init (speaker output) =====
    tts = None
    if USE_TTS:
        if pyttsx3 is None:
            print("⚠️ TTS disabled: missing pyttsx3. Install: pip install pyttsx3 pywin32")
        else:
            tts = TTSWorker(voice_hint=TTS_VOICE_HINT, rate=TTS_RATE)


    print("✅ Hot mic ON (capture is running continuously)")
    print("🎙️ Mic input device:", device)
    print("✅ Deepgram URL:", DG_URL)
    print(f"⏳ STOP flush tail audio: {FLUSH_MS} ms | grace={STOP_GRACE_S:.1f}s | log_tail_max={STREAM_LOG_MAX}")
    if USE_QWEN:
        print(f"🤖 Qwen normalize via Ollama: {OLLAMA_BASE_URL}  |  model={QWEN_MODEL}")
    else:
        print("🤖 Qwen normalize: OFF (set USE_QWEN=1 to enable)")

    print("\n📌 INSTRUCTIONS:")
    print("  - Press ENTER to START streaming to Deepgram")
    print("  - Press ENTER again to STOP, then get transcript + normalized text")
    print("  - Ctrl+C to exit\n")

    while True:
        try:
            if not ctl.active:
                await loop.run_in_executor(None, input, "⏯️ ENTER = START (Deepgram) ... ")
                print("🟢 STREAMING to Deepgram... (ENTER to stop)\n")
                await ctl.start_streaming()
            else:
                await loop.run_in_executor(None, input, "⏹️ ENTER = STOP ... ")
                print("🟠 Stopping... flushing tail audio + waiting for final results...\n")
                asr = await ctl.stop_streaming_and_collect()

                raw_full = (asr.get("raw_full") or "").strip()
                last_interim = (asr.get("last_interim") or "").strip()

                print("\n====================")
                print("📝 Deepgram RAW (final-only):")
                print(raw_full if raw_full else "(no final transcript)")
                if last_interim:
                    print("--------------------")
                    print("… Last interim (may contain missing words):")
                    print(last_interim)
                print("====================\n")

                # ===== 2-stage Qwen: normalize -> answer -> TTS =====
                # Stage 1: normalize
                norm = ''
                if USE_QWEN_NORM and (asr.get('spoken_trace') or '').strip():
                    payload = {
                        'spoken_trace': asr.get('spoken_trace', ''),
                        'stream_log_tail': asr.get('stream_log_tail', []),
                        'final_segments': asr.get('final_segments', []),
                        'raw_full': raw_full,
                        'last_interim': last_interim,
                    }
                    norm = (await normalize_with_qwen(loop, payload)).strip()
                    print('✨ QWEN#1 NORMALIZED:')
                    print(norm)
                    print()
                else:
                    # fallback to Deepgram final
                    norm = raw_full or last_interim
                
                # Stage 2: answer
                if USE_QWEN_ANS and (norm or '').strip():
                    ans = (await answer_with_qwen(loop, norm)).strip()
                    print('🔊 QWEN#2 ANSWER:')
                    print(ans)
                    print()
                    if tts is not None and ans and not ans.startswith('[QWEN_ERROR]'):
                        tts.speak(ans)
                else:
                    print('ℹ️ Qwen#2 skipped (USE_QWEN_ANS=0 or empty text).\n')
                    pass

        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except ConnectionClosed as e:
            print(f"\n❌ WebSocket error: {e}\n")
            try:
                await ctl.stop_streaming_and_collect()
            except Exception:
                pass
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            try:
                await ctl.stop_streaming_and_collect()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nBye!")