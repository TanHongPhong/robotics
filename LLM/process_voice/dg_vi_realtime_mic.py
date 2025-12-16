import os
import json
import asyncio
from urllib.parse import urlencode

import numpy as np
import sounddevice as sd
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from dotenv import load_dotenv
load_dotenv()

# ======================
# Config
# ======================
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
if not DEEPGRAM_API_KEY:
    raise RuntimeError("DEEPGRAM_API_KEY not set in environment.")

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"          # raw PCM 16-bit
BLOCK_MS = 50            # 20ms-100ms đều được; 50ms ổn định
BLOCK_SAMPLES = int(SAMPLE_RATE * BLOCK_MS / 1000)

PRINT_INTERIM = True    # True if you want to see interim_results realtime

DG_QUERY = {
    "model": "nova-3-general",   # you can change to "nova-3"
    "language": "vi",
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

DG_URL = "wss://api.deepgram.com/v1/listen?" + urlencode(DG_QUERY)


# ======================
# Helpers
# ======================
def pick_default_input_device():
    """Return default input device id; None if error."""
    try:
        dev = sd.default.device[0]  # input
        return dev
    except Exception:
        return None


def list_input_devices():
    devices = sd.query_devices()
    inputs = []
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            inputs.append((i, d["name"], d["max_input_channels"]))
    return inputs


# ======================
# Main - Push-to-Talk Mode
# ======================
async def run():
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    device = pick_default_input_device()
    if device is None:
        print("Unable to get default mic. Available input devices:")
        for i, name, ch in list_input_devices():
            print(f"  [{i}] {name} (channels={ch})")
        raise RuntimeError("Please set sd.default.device = (input_id, output_id) or choose device manually.")

    print("✅ Deepgram API Ready")
    print("🎙️ Mic input device:", device)
    print("\n📌 INSTRUCTIONS:")
    print("  - Press ENTER to START RECORDING")
    print("  - Press ENTER again to STOP RECORDING and get results")
    print("  - Ctrl+C to exit\n")

    loop = asyncio.get_running_loop()
    
    while True:
        try:
            # Wait for user to press Enter to start
            await loop.run_in_executor(None, input, "🎤 Press ENTER to start recording... ")
            print("🔴 RECORDING... (press ENTER to stop)\n")
            
            audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
            stop_recording = asyncio.Event()
            
            def audio_callback(indata, frames, time_info, status):
                if status:
                    print("[AUDIO]", status, flush=True)
                try:
                    audio_bytes = bytes(indata)
                    loop.call_soon_threadsafe(audio_q.put_nowait, audio_bytes)
                except Exception:
                    pass

            async with websockets.connect(
                DG_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                max_size=8_000_000,
            ) as ws:

                async def sender():
                    with sd.RawInputStream(
                        samplerate=SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype=DTYPE,
                        blocksize=BLOCK_SAMPLES,
                        device=device,
                        callback=audio_callback,
                    ):
                        while not stop_recording.is_set():
                            try:
                                chunk = await asyncio.wait_for(audio_q.get(), timeout=0.1)
                                await ws.send(chunk)
                            except asyncio.TimeoutError:
                                continue
                    
                    # Send end signal
                    await ws.send(json.dumps({"type": "CloseStream"}).encode())

                async def receiver():
                    transcripts = []
                    try:
                        while True:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                                data = json.loads(msg)

                                t = data.get("type")
                                
                                if t != "Results":
                                    continue

                                ch = data.get("channel") or {}
                                alts = ch.get("alternatives") or []
                                transcript = (alts[0].get("transcript") if alts else "") or ""

                                is_final = bool(data.get("is_final"))

                                if PRINT_INTERIM and transcript.strip() and not is_final:
                                    print("…", transcript.strip(), flush=True)

                                if is_final and transcript.strip():
                                    transcripts.append(transcript.strip())
                            
                            except asyncio.TimeoutError:
                                # If already stopped and timeout, exit
                                if stop_recording.is_set():
                                    break
                                continue
                            except ConnectionClosed:
                                break
                    except Exception:
                        pass
                    
                    return transcripts

                async def wait_for_stop():
                    await loop.run_in_executor(None, input)
                    stop_recording.set()

                # Run concurrently: record, receive results, and wait for user to press Enter
                results = await asyncio.gather(
                    sender(),
                    receiver(),
                    wait_for_stop(),
                    return_exceptions=True
                )
                
                # receiver() at index 1, returns list of transcripts
                transcripts = results[1] if len(results) > 1 else []
                
                # Process results
                if isinstance(transcripts, list) and transcripts:
                    full = " ".join(transcripts).strip()
                    print(f"\n✅ RESULT: {full}\n")
                else:
                    print("\n⚠️ No results received.\n")

        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except (ConnectionClosed, InvalidStatusCode) as e:
            print(f"\n❌ WebSocket connection error: {e}")
            print("Retrying...\n")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Retrying...\n")
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nBye!")
