#!/usr/bin/env python3
# dg_flux_push_to_talk_en_hiac.py
# ENTER start -> ENTER stop -> Deepgram Flux (English) -> FINAL + combined transcript
# Tuned for high reliability + less "missing last words"

import os
import json
import asyncio
from urllib.parse import urlencode
import time

import sounddevice as sd
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode
from dotenv import load_dotenv
load_dotenv()

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Missing DEEPGRAM_API_KEY in env/.env")

# Flux requires model=flux-general-en on /v2/listen :contentReference[oaicite:4]{index=4}
DG_MODEL = os.environ.get("DG_MODEL", "flux-general-en")

# Flux supports 8000/16000/24000/44100/48000 for raw audio :contentReference[oaicite:5]{index=5}
SAMPLE_RATE = int(os.environ.get("DG_SAMPLE_RATE", "16000"))
CHANNELS = 1
DTYPE = "int16"

# Deepgram recommends ~80ms chunks for optimal Flux performance :contentReference[oaicite:6]{index=6}
BLOCK_MS = int(os.environ.get("DG_BLOCK_MS", "80"))
BLOCK_SAMPLES = int(SAMPLE_RATE * BLOCK_MS / 1000)

# High-reliability turn detection (fewer false EndOfTurn) :contentReference[oaicite:7]{index=7}
EOT_THRESHOLD = float(os.environ.get("DG_EOT_THRESHOLD", "0.88"))    # 0.5–0.9 :contentReference[oaicite:8]{index=8}
EOT_TIMEOUT_MS = int(os.environ.get("DG_EOT_TIMEOUT_MS", "9000"))    # 500–10000 :contentReference[oaicite:9]{index=9}

# Optional: keyterm prompting for special words (Flux supports keyterm) :contentReference[oaicite:10]{index=10}
KEYTERMS = [t.strip() for t in os.environ.get("DG_KEYTERMS", "").split(",") if t.strip()]

PRINT_UPDATES = os.environ.get("DG_PRINT_UPDATES", "0").lower() in ("1", "true", "yes", "y")
SHOW_LEVEL_METER = os.environ.get("DG_LEVEL_METER", "1").lower() in ("1", "true", "yes", "y")

def build_flux_url() -> str:
    q = {
        "model": DG_MODEL,
        "encoding": "linear16",
        "sample_rate": str(SAMPLE_RATE),
        "eot_threshold": str(EOT_THRESHOLD),
        "eot_timeout_ms": str(EOT_TIMEOUT_MS),
    }
    if KEYTERMS:
        q["keyterm"] = KEYTERMS  # repeat param
    return "wss://api.deepgram.com/v2/listen?" + urlencode(q, doseq=True)

def pick_default_input_device():
    try:
        return sd.default.device[0]
    except Exception:
        return None

def list_input_devices():
    devs = sd.query_devices()
    out = []
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            out.append((i, d.get("name"), d.get("default_samplerate")))
    return out

async def flux_record_once(device: int) -> str:
    url = build_flux_url()
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    loop = asyncio.get_running_loop()

    audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1200)
    stop_event = asyncio.Event()
    sent_close = asyncio.Event()

    latest_by_turn = {}
    finals: list[str] = []

    # simple level meter
    peak = 0.0
    last_peak_ts = time.time()

    def audio_callback(indata, frames, time_info, status):
        nonlocal peak, last_peak_ts
        if status:
            print("[AUDIO]", status, flush=True)

        b = bytes(indata)

        # Update peak (int16)
        # indata is raw bytes; compute quick peak by sampling a few points to reduce CPU
        now = time.time()
        if now - last_peak_ts > 0.10:
            # cheap peak estimate
            import array
            arr = array.array("h", b)
            if arr:
                m = max(abs(arr[0]), abs(arr[len(arr)//2]), abs(arr[-1]))
                peak = max(peak, m / 32768.0)
            last_peak_ts = now

        try:
            loop.call_soon_threadsafe(audio_q.put_nowait, b)
        except Exception:
            pass

    async def level_meter_task():
        nonlocal peak
        while not stop_event.is_set():
            await asyncio.sleep(0.6)
            p = peak
            peak = 0.0
            if not SHOW_LEVEL_METER:
                continue
            # heuristics:
            # - too low: < 0.02  (very quiet mic)
            # - clipping: > 0.98
            if p < 0.02:
                print("⚠️ Mic level VERY LOW (increase input gain / get closer to mic).", flush=True)
            elif p > 0.98:
                print("⚠️ Mic CLIPPING (reduce input gain).", flush=True)

    async def sender(ws):
        # record until stop_event set
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SAMPLES,
            device=device,
            callback=audio_callback,
        ):
            while not stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(audio_q.get(), timeout=0.25)
                    await ws.send(chunk)
                except asyncio.TimeoutError:
                    continue

        # Drain remaining queued audio for a short grace window (prevents missing last syllables)
        drain_until = loop.time() + 0.5
        while loop.time() < drain_until:
            try:
                chunk = audio_q.get_nowait()
                await ws.send(chunk)
            except asyncio.QueueEmpty:
                break
            except Exception:
                break

        # CloseStream flush :contentReference[oaicite:11]{index=11}
        try:
            await ws.send(json.dumps({"type": "CloseStream"}).encode())
        finally:
            sent_close.set()

    async def receiver(ws):
        grace_after_close_sec = 2.2  # slightly longer to catch last EndOfTurn
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
                    final_text = transcript

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
        await asyncio.gather(sender(ws), receiver(ws), wait_stop_enter(), level_meter_task())

    combined = " ".join([s.strip() for s in finals if s.strip()]).strip()
    return combined

async def main():
    device = pick_default_input_device()
    if device is None:
        print("No default mic. Available input devices:")
        for i, name, sr in list_input_devices():
            print(f"  [{i}] {name} (default_sr={sr})")
        raise RuntimeError("Please set sd.default.device or choose a device.")

    print("🎙️ Mic input device:", device)
    print(f"🎚️ Using sample_rate={SAMPLE_RATE}, block={BLOCK_MS}ms, mono")
    print("📌 Push-to-talk:")
    print("  - Press ENTER to START recording")
    print("  - Press ENTER again to STOP and get transcript")
    print("  - Ctrl+C to exit\n")

    loop = asyncio.get_running_loop()

    while True:
        try:
            await loop.run_in_executor(None, input, "🎤 Press ENTER to START... ")
            text = await flux_record_once(device)

            if text:
                print(f"🧾 COMBINED TRANSCRIPT:\n{text}\n")
            else:
                print("⚠️ No transcript received.\n")

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
