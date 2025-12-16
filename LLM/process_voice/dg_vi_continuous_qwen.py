import os
import json
import asyncio
from urllib.parse import urlencode
from typing import List

import numpy as np
import sounddevice as sd
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode
import requests

from dotenv import load_dotenv
load_dotenv()

# ======================
# Config
# ======================
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
if not DEEPGRAM_API_KEY:
    raise RuntimeError("DEEPGRAM_API_KEY not set in environment.")

# Ollama/Qwen configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").strip()
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen2.5:latest").strip()

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
# Qwen Normalization
# ======================
def normalize_with_qwen(raw_text: str, interim_words: List[str]) -> str:
    """
    Send the raw transcription and interim words to Qwen for normalization.
    Returns the normalized/corrected text.
    """
    if not raw_text.strip():
        return raw_text
    
    # Create a prompt for Qwen to normalize the Vietnamese text
    prompt = f"""Bạn là một trợ lý chuyên về chuẩn hóa văn bản tiếng Việt. 
Nhiệm vụ của bạn là sửa lỗi và chuẩn hóa câu văn từ kết quả nhận diện giọng nói.

Các từ đã được nhận diện trong quá trình ghi âm:
{', '.join(interim_words) if interim_words else 'Không có'}

Kết quả cuối cùng từ Deepgram:
{raw_text}

Hãy chuẩn hóa câu văn trên, sửa các lỗi chính tả, ngữ pháp và đảm bảo câu văn có ý nghĩa rõ ràng.
CHỈ TRẢ VỀ CÂU VĂN ĐÃ CHUẨN HÓA, KHÔNG GHI CHÚ GÌ THÊM."""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": QWEN_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower temperature for more consistent corrections
                    "top_p": 0.9,
                }
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            normalized = result.get("response", "").strip()
            return normalized if normalized else raw_text
        else:
            print(f"❌ Qwen API error: {response.status_code}")
            return raw_text
            
    except requests.exceptions.Timeout:
        print("⚠️ Qwen timeout - using raw text")
        return raw_text
    except Exception as e:
        print(f"⚠️ Qwen error: {e} - using raw text")
        return raw_text


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
# Main - Continuous Microphone with Push-to-Transcribe
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
    print("✅ Qwen Model Ready:", QWEN_MODEL)
    print("🎙️ Mic input device:", device)
    print("\n📌 INSTRUCTIONS:")
    print("  - Microphone is CONTINUOUSLY active")
    print("  - Press ENTER to START TRANSMITTING to Deepgram")
    print("  - Press ENTER again to STOP and get normalized results")
    print("  - Ctrl+C to exit\n")

    loop = asyncio.get_running_loop()
    
    # Continuous microphone buffer - always recording
    continuous_audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1000)
    mic_running = True
    
    def continuous_audio_callback(indata, frames, time_info, status):
        """Continuous recording callback - always active"""
        if status:
            print("[AUDIO]", status, flush=True)
        try:
            audio_bytes = bytes(indata)
            loop.call_soon_threadsafe(continuous_audio_q.put_nowait, audio_bytes)
        except asyncio.QueueFull:
            # Drop oldest data if queue is full
            try:
                continuous_audio_q.get_nowait()
                continuous_audio_q.put_nowait(audio_bytes)
            except:
                pass
        except Exception as e:
            print(f"[AUDIO ERROR] {e}")
    
    # Start continuous microphone stream
    mic_stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=BLOCK_SAMPLES,
        device=device,
        callback=continuous_audio_callback,
    )
    mic_stream.start()
    print("🎤 Microphone is now ACTIVE and continuously recording...\n")
    
    try:
        while True:
            try:
                # Wait for user to press Enter to start sending to Deepgram
                await loop.run_in_executor(None, input, "📡 Press ENTER to start transmitting to Deepgram... ")
                print("🔴 TRANSMITTING TO DEEPGRAM... (press ENTER to stop)\n")
                
                transmit_audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
                stop_transmitting = asyncio.Event()
                interim_words: List[str] = []
                
                async with websockets.connect(
                    DG_URL,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=8_000_000,
                ) as ws:

                    async def audio_forwarder():
                        """Forward audio from continuous mic to Deepgram"""
                        while not stop_transmitting.is_set():
                            try:
                                chunk = await asyncio.wait_for(continuous_audio_q.get(), timeout=0.1)
                                await ws.send(chunk)
                            except asyncio.TimeoutError:
                                continue
                            except Exception as e:
                                break
                        
                        # Send end signal
                        await ws.send(json.dumps({"type": "CloseStream"}).encode())

                    async def receiver():
                        """Receive and process Deepgram results"""
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
                                        # Collect interim words for Qwen context
                                        interim_words.append(transcript.strip())

                                    if is_final and transcript.strip():
                                        transcripts.append(transcript.strip())
                                
                                except asyncio.TimeoutError:
                                    # If already stopped and timeout, exit
                                    if stop_transmitting.is_set():
                                        break
                                    continue
                                except ConnectionClosed:
                                    break
                        except Exception:
                            pass
                        
                        return transcripts

                    async def wait_for_stop():
                        """Wait for user to press Enter to stop"""
                        await loop.run_in_executor(None, input)
                        stop_transmitting.set()

                    # Run concurrently: forward audio, receive results, and wait for user to press Enter
                    results = await asyncio.gather(
                        audio_forwarder(),
                        receiver(),
                        wait_for_stop(),
                        return_exceptions=True
                    )
                    
                    # receiver() at index 1, returns list of transcripts
                    transcripts = results[1] if len(results) > 1 else []
                    
                    # Process results
                    if isinstance(transcripts, list) and transcripts:
                        raw_result = " ".join(transcripts).strip()
                        print(f"\n📝 RAW DEEPGRAM: {raw_result}")
                        
                        # Normalize with Qwen
                        print("🤖 Normalizing with Qwen...")
                        normalized_result = normalize_with_qwen(raw_result, interim_words)
                        print(f"✅ NORMALIZED RESULT: {normalized_result}\n")
                    else:
                        print("\n⚠️ No results received from Deepgram.\n")

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
    
    finally:
        # Stop continuous microphone
        mic_stream.stop()
        mic_stream.close()
        print("🎤 Microphone stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nBye!")
