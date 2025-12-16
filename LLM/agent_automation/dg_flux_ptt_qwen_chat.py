#!/usr/bin/env python3
# dg_flux_ptt_qwen_chat.py
# ENTER start -> ENTER stop -> Deepgram Flux (English) -> send transcript to Ollama(Qwen) -> print answer (with chat history)

import os
import json
import asyncio
from urllib.parse import urlencode
import urllib.request
import urllib.error

import sounddevice as sd
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from dotenv import load_dotenv
load_dotenv()

# =========================
# Deepgram (Flux)
# =========================
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Missing DEEPGRAM_API_KEY in env/.env")

DG_MODEL = os.environ.get("DG_MODEL", "flux-general-en")  # Flux requires flux-general-en
SAMPLE_RATE = int(os.environ.get("DG_SAMPLE_RATE", "16000"))
CHANNELS = 1
DTYPE = "int16"

BLOCK_MS = int(os.environ.get("DG_BLOCK_MS", "80"))  # Flux: 80ms chunks recommended
BLOCK_SAMPLES = int(SAMPLE_RATE * BLOCK_MS / 1000)

EOT_THRESHOLD = float(os.environ.get("DG_EOT_THRESHOLD", "0.80"))
EOT_TIMEOUT_MS = int(os.environ.get("DG_EOT_TIMEOUT_MS", "7000"))

KEYTERMS = [t.strip() for t in os.environ.get("DG_KEYTERMS", "").split(",") if t.strip()]
PRINT_UPDATES = os.environ.get("DG_PRINT_UPDATES", "0").lower() in ("1", "true", "yes", "y")

# =========================
# Ollama / Qwen
# =========================
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b-instruct")

# Tuning (optional)
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.3"))
OLLAMA_TOP_P = float(os.environ.get("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))

def build_flux_url() -> str:
    q = {
        "model": DG_MODEL,
        "encoding": "linear16",
        "sample_rate": str(SAMPLE_RATE),
        "eot_threshold": str(EOT_THRESHOLD),
        "eot_timeout_ms": str(EOT_TIMEOUT_MS),
    }
    if KEYTERMS:
        q["keyterm"] = KEYTERMS  # repeated query param
    return "wss://api.deepgram.com/v2/listen?" + urlencode(q, doseq=True)

def pick_default_input_device():
    try:
        return sd.default.device[0]
    except Exception:
        return None

async def flux_record_once() -> str:
    """
    Record until ENTER, stream to Flux, return combined final transcript for this segment.
    """
    url = build_flux_url()
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    loop = asyncio.get_running_loop()

    audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=800)
    stop_event = asyncio.Event()
    sent_close = asyncio.Event()

    latest_by_turn = {}
    finals: list[str] = []

    def audio_callback(indata, frames, time_info, status):
        if status:
            print("[AUDIO]", status, flush=True)
        b = bytes(indata)
        try:
            loop.call_soon_threadsafe(audio_q.put_nowait, b)
        except Exception:
            pass

    async def sender(ws):
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SAMPLES,
            device=pick_default_input_device(),
            callback=audio_callback,
        ):
            while not stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(audio_q.get(), timeout=0.25)
                    await ws.send(chunk)
                except asyncio.TimeoutError:
                    continue

        try:
            await ws.send(json.dumps({"type": "CloseStream"}).encode())
        finally:
            sent_close.set()

    async def receiver(ws):
        grace_after_close_sec = 1.5
        last_msg_time = loop.time()

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.35)
                last_msg_time = loop.time()
            except asyncio.TimeoutError:
                if sent_close.is_set() and (loop.time() - last_msg_time) > grace_after_close_sec:
                    break
                continue
            except ConnectionClosed:
                break

            try:
                data = json.loads(msg)
            except Exception:
                continue

            t = data.get("type")
            if t == "Error":
                print("❌ Deepgram Error:", data)
                break

            if t == "Connected":
                req_id = data.get("request_id")
                if req_id:
                    print(f"✅ Connected (request_id={req_id})")
                continue

            if t != "TurnInfo":
                continue

            event = data.get("event")
            turn_index = data.get("turn_index")
            transcript = (data.get("transcript") or "").strip()
            eot_conf = data.get("end_of_turn_confidence")

            if transcript and turn_index is not None:
                latest_by_turn[turn_index] = transcript

            if event == "Update":
                if PRINT_UPDATES and transcript:
                    print("…", transcript, flush=True)

            elif event == "EndOfTurn":
                if turn_index is not None:
                    final_text = (latest_by_turn.get(turn_index) or transcript).strip()
                else:
                    final_text = transcript.strip()

                if final_text:
                    finals.append(final_text)
                    if eot_conf is not None:
                        print(f"\n✅ FINAL: {final_text}   (eot_conf={float(eot_conf):.2f})\n")
                    else:
                        print(f"\n✅ FINAL: {final_text}\n")

    async def wait_stop_enter():
        await loop.run_in_executor(None, input)
        stop_event.set()

    print("✅ Deepgram Flux:", url)
    print("🔴 Recording... (press ENTER to stop)\n")

    async with websockets.connect(
        url,
        additional_headers=headers,
        ping_interval=20,
        ping_timeout=20,
        max_size=8_000_000,
    ) as ws:
        await asyncio.gather(sender(ws), receiver(ws), wait_stop_enter())

    combined = " ".join([s.strip() for s in finals if s.strip()]).strip()
    return combined

def ollama_chat_stream(model: str, messages: list[dict], host: str) -> str:
    """
    Stream chat response from Ollama /api/chat (NDJSON).
    Returns full assistant content.
    """
    url = f"{host}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": OLLAMA_TEMPERATURE,
            "top_p": OLLAMA_TOP_P,
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }

    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    full = []
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            for raw in resp:
                if not raw:
                    continue
                try:
                    chunk = json.loads(raw.decode("utf-8"))
                except Exception:
                    continue

                if chunk.get("error"):
                    raise RuntimeError(chunk["error"])

                if chunk.get("done"):
                    break

                token = (chunk.get("message") or {}).get("content") or ""
                if token:
                    print(token, end="", flush=True)
                    full.append(token)

    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host}. Is Ollama running? ({e})")

    return "".join(full).strip()

async def main():
    device = pick_default_input_device()
    if device is None:
        raise RuntimeError("No default input device. Please configure sounddevice input device.")

    # Chat history for Qwen
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. "
                "Respond in Vietnamese by default unless the user clearly speaks English. "
                "Keep answers practical and ask a short follow-up question when needed."
            ),
        }
    ]

    print("🎙️ Mic input device:", device)
    print("📌 Push-to-talk:")
    print("  - Press ENTER to START recording")
    print("  - Press ENTER again to STOP and get transcript")
    print("  - Say/type: 'reset' to clear chat, 'exit' to quit")
    print(f"\n🤖 Ollama: {OLLAMA_HOST} | Model: {OLLAMA_MODEL}\n")

    loop = asyncio.get_running_loop()

    while True:
        try:
            await loop.run_in_executor(None, input, "🎤 Press ENTER to START... ")
            text = await flux_record_once()

            if not text:
                print("⚠️ No transcript received.\n")
                continue

            print(f"🧾 USER SAID:\n{text}\n")

            lower = text.strip().lower()
            if lower in ("exit", "quit", "bye"):
                print("Bye!")
                break
            if lower in ("reset", "clear", "new chat"):
                messages = [messages[0]]  # keep system
                print("🧼 Cleared chat history.\n")
                continue

            # Append user message
            messages.append({"role": "user", "content": text})

            # Call Qwen via Ollama (streaming)
            print("🤖 QWEN:\n", end="", flush=True)
            answer = await asyncio.to_thread(
                ollama_chat_stream, OLLAMA_MODEL, messages, OLLAMA_HOST
            )
            print("\n")  # newline after streaming

            # Append assistant message
            if answer:
                messages.append({"role": "assistant", "content": answer})
            else:
                print("⚠️ Qwen returned empty response.\n")

        except KeyboardInterrupt:
            print("\nBye!")
            break
        except (InvalidStatusCode, ConnectionClosed) as e:
            print("❌ WebSocket error:", e, "\nRetrying...\n")
            await asyncio.sleep(1)
        except Exception as e:
            print("❌ Error:", e, "\nRetrying...\n")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
