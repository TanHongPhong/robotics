#!/usr/bin/env python3
# dg_vi_hotmic_qwen_2stage_pickjson.py
#
# Hot mic always ON. Press ENTER to toggle:
#   - START: connect + stream audio to Deepgram realtime
#   - STOP : flush tail audio, close stream,
#            send the WHOLE streaming trace (interim + final) to Qwen#1 for normalization,
#            then send normalized text + current grid plan to Qwen#2 to produce:
#               (a) a short reply, and (b) a PICK PLAN JSON (schema_version=1.0).
#
# Requirements:
#   pip install sounddevice websockets python-dotenv
#   (Ollama) install Ollama + pull your model(s):
#     ollama pull qwen2.5:1.5b-instruct
#
# Env:
#   DEEPGRAM_API_KEY=...
#   OLLAMA_BASE_URL=http://localhost:11434
#   QWEN_NORM_MODEL=qwen2.5:1.5b-instruct
#   QWEN_TASK_MODEL=qwen2.5:1.5b-instruct
#   PLAN_FILE=pick_plan.json           (grid/product template; also may include web ticks)
#   WEB_TICK_FILE=web_tick.json        (optional; overrides/sets initial picks from web UI)
#   OUT_PLAN_FILE=pick_plan_out.json   (output plan)
#
# Notes:
# - PLAN_FILE should include 9 items with product names mapped to cell_id (1..9).
# - WEB_TICK_FILE can be:
#     * the same schema JSON with "items":[{cell_id,pick},...]
#     * or {"picked_cell_ids":[1,3,5]}
#     * or a simple list [1,3,5]
# - Qwen#2 will adjust picks based on the (normalized) voice command, but will keep the full 9-item list.

import os
import json
import time
import asyncio
import argparse
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

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

# Qwen via Ollama
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
QWEN_NORM_MODEL = os.environ.get("QWEN_NORM_MODEL", os.environ.get("QWEN_MODEL", "qwen2.5:1.5b-instruct")).strip()
QWEN_TASK_MODEL = os.environ.get("QWEN_TASK_MODEL", QWEN_NORM_MODEL).strip()

USE_QWEN_NORM = os.environ.get("USE_QWEN_NORM", os.environ.get("USE_QWEN", "1")).strip() not in ("0", "false", "False")
USE_QWEN_TASK = os.environ.get("USE_QWEN_TASK", "1").strip() not in ("0", "false", "False")

# Plan IO (can be overridden by CLI)
PLAN_FILE = os.environ.get("PLAN_FILE", "pick_plan.json")
WEB_TICK_FILE = os.environ.get("WEB_TICK_FILE", "")
OUT_PLAN_FILE = os.environ.get("OUT_PLAN_FILE", "pick_plan_out.json")


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


def read_json_file(path: str) -> dict | list | None:
    try:
        if not path:
            return None
        p = os.path.abspath(path)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json_file(path: str, obj: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def safe_str(x) -> str:
    return (x if isinstance(x, str) else "").strip()


def extract_first_json(text: str) -> dict | None:
    """
    Best-effort extraction of the first JSON object from model output.
    Handles cases where the model adds extra text.
    """
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None
    # Direct parse
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Find first {...}
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        cand = s[start:end + 1].strip()
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def plan_template_default() -> dict:
    # Fallback template if PLAN_FILE missing.
    return {
        "schema_version": "1.0",
        "grid": {"rows": 3, "cols": 3, "cell_id_range": [1, 9]},
        "items": [{"cell_id": i, "product": f"Ô {i}", "pick": False} for i in range(1, 10)],
        "selection_source": {"mode": "voice_only", "web_tick": False, "voice_llm": True},
    }


def normalize_plan_shape(plan: dict, template: dict) -> dict:
    """
    Ensure plan conforms to:
      schema_version, grid, items[1..9], selection_source
    Keep product names from template whenever possible.
    """
    if not isinstance(plan, dict):
        plan = {}

    out = {
        "schema_version": "1.0",
        "grid": {"rows": 3, "cols": 3, "cell_id_range": [1, 9]},
        "items": [],
        "selection_source": {"mode": "voice_only", "web_tick": False, "voice_llm": True},
    }

    # Grid from template if exists
    grid = template.get("grid") if isinstance(template, dict) else None
    if isinstance(grid, dict):
        out["grid"] = {
            "rows": int(grid.get("rows", 3)),
            "cols": int(grid.get("cols", 3)),
            "cell_id_range": list(grid.get("cell_id_range", [1, 9])),
        }

    # Build cell->product from template first
    t_items = (template.get("items") if isinstance(template, dict) else None) or []
    t_prod = {}
    for it in t_items:
        try:
            cid = int(it.get("cell_id"))
            if 1 <= cid <= 9:
                t_prod[cid] = safe_str(it.get("product")) or f"Ô {cid}"
        except Exception:
            pass

    # Plan items
    p_items = plan.get("items") if isinstance(plan.get("items"), list) else []
    p_pick = {}
    p_prod = {}
    for it in p_items:
        try:
            cid = int(it.get("cell_id"))
            if 1 <= cid <= 9:
                p_pick[cid] = bool(it.get("pick"))
                if safe_str(it.get("product")):
                    p_prod[cid] = safe_str(it.get("product"))
        except Exception:
            pass

    for cid in range(1, 10):
        out["items"].append({
            "cell_id": cid,
            "product": p_prod.get(cid) or t_prod.get(cid) or f"Ô {cid}",
            "pick": bool(p_pick.get(cid, False)),
        })

    # selection_source (filled later by caller)
    return out


def web_tick_to_pick_map(web_obj) -> dict[int, bool]:
    """
    Accepts multiple shapes:
      - {"items":[{cell_id,pick},...]}
      - {"picked_cell_ids":[1,3,5]}
      - [1,3,5]
    Returns: {cell_id: bool}
    """
    picks = {}
    if web_obj is None:
        return picks

    if isinstance(web_obj, dict):
        if isinstance(web_obj.get("items"), list):
            for it in web_obj["items"]:
                try:
                    cid = int(it.get("cell_id"))
                    if 1 <= cid <= 9:
                        picks[cid] = bool(it.get("pick"))
                except Exception:
                    pass
            return picks

        for key in ("picked_cell_ids", "picked", "cells", "cell_ids"):
            if isinstance(web_obj.get(key), list):
                for x in web_obj[key]:
                    try:
                        cid = int(x)
                        if 1 <= cid <= 9:
                            picks[cid] = True
                    except Exception:
                        pass
                return picks

    if isinstance(web_obj, list):
        for x in web_obj:
            try:
                cid = int(x)
                if 1 <= cid <= 9:
                    picks[cid] = True
            except Exception:
                pass
        return picks

    return picks


def apply_web_ticks_to_template(template_plan: dict, web_pick_map: dict[int, bool]) -> dict:
    if not web_pick_map:
        return template_plan
    out = json.loads(json.dumps(template_plan, ensure_ascii=False))
    for it in out.get("items", []):
        try:
            cid = int(it.get("cell_id"))
            if cid in web_pick_map:
                it["pick"] = bool(web_pick_map[cid])
        except Exception:
            pass
    return out


def ollama_chat_once(base_url: str, model: str, system: str, user: str, timeout_s: int = 90) -> str:
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
        return f"[QWEN_ERROR] {type(e).__name__}: {type(e).__name__}: {e}"


async def normalize_with_qwen(loop: asyncio.AbstractEventLoop, payload: dict) -> str:
    """Qwen#1: normalize Vietnamese transcript from streaming trace."""
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
    return await loop.run_in_executor(None, ollama_chat_once, OLLAMA_BASE_URL, QWEN_NORM_MODEL, system, user, 90)


async def plan_with_qwen(loop: asyncio.AbstractEventLoop, normalized_text: str, template_plan: dict) -> tuple[str, dict]:
    """
    Qwen#2: take normalized voice text + current plan template -> (reply, plan_json).
    - It may return either:
        (A) {"reply": "...", "plan": {...schema...}}
        (B) {...schema...}  (plan only)
    We will accept both, then normalize to exact schema.
    """
    system = (
        "Bạn là agent lập kế hoạch chọn đồ để robot lấy trong lưới 3x3 (cell_id 1..9). "
        "Bạn sẽ nhận 2 thứ: (1) câu lệnh tiếng Việt đã được chuẩn hoá, (2) kế hoạch hiện tại (template) gồm 9 ô với tên sản phẩm. "
        "Nhiệm vụ: cập nhật trường pick (true/false) cho TẤT CẢ 9 ô dựa trên câu lệnh. "
        "\n\nQuy tắc:\n"
        "- KHÔNG đổi product/cell_id; chỉ cập nhật pick.\n"
        "- Nếu câu lệnh không nhắc đến một sản phẩm/ô nào đó, GIỮ nguyên pick như template.\n"
        "- Nếu câu lệnh có phủ định rõ ràng (vd: 'không lấy', 'bỏ', 'đừng lấy') thì set pick=false.\n"
        "- Nếu có yêu cầu lấy rõ ràng (vd: 'lấy', 'thêm', 'chọn') thì pick=true.\n"
        "- Nếu có 'lấy tất cả' => tất cả pick=true. Nếu có 'bỏ hết/không lấy gì' => tất cả pick=false.\n"
        "- Nếu người dùng nói tên sản phẩm (gần giống) thì match theo product trong template.\n"
        "\n\nOutput:\n"
        "- Trả về JSON HỢP LỆ (không markdown, không giải thích).\n"
        "- Ưu tiên trả về object có 2 keys: reply (string ngắn) và plan (object theo schema).\n"
    )

    user = json.dumps({
        "normalized_text": normalized_text,
        "template_plan": template_plan,
        "required_schema_example": {
            "schema_version": "1.0",
            "grid": {"rows": 3, "cols": 3, "cell_id_range": [1, 9]},
            "items": [
                {"cell_id": 1, "product": "…", "pick": True},
                {"cell_id": 2, "product": "…", "pick": False}
            ],
            "selection_source": {"mode": "mixed", "web_tick": True, "voice_llm": True}
        }
    }, ensure_ascii=False, indent=2)

    text = await loop.run_in_executor(None, ollama_chat_once, OLLAMA_BASE_URL, QWEN_TASK_MODEL, system, user, 90)
    obj = extract_first_json(text) or {}
    if "plan" in obj and isinstance(obj["plan"], dict):
        reply = safe_str(obj.get("reply")) or "Đã cập nhật danh sách đồ cần lấy."
        plan = obj["plan"]
        return reply, plan
    # Plan-only fallback
    if isinstance(obj, dict) and obj.get("schema_version"):
        return "Đã tạo danh sách đồ cần lấy.", obj
    # If model didn't output JSON, return empty (caller will fallback)
    return "", {}


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
        self.interim_updates: list[str] = []
        self.stream_log: list[dict] = []

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

        # Compact spoken trace for Qwen#1
        lines = []
        for e in self.stream_log[-STREAM_LOG_MAX:]:
            prefix = "FINAL" if e.get("is_final") else "INTERIM"
            lines.append(f"{prefix}: {e.get('text','')}")
        spoken_trace = "\n".join(lines).strip()

        return {
            "raw_full": raw_full,
            "final_segments": list(self.final_segments),
            "last_interim": self.last_interim.strip(),
            "interim_updates": list(self.interim_updates)[-200:],
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
                    self.last_interim = ""
                else:
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
async def run(plan_file: str, web_tick_file: str, out_plan_file: str):
    device = pick_default_input_device()
    if device is None:
        print("Unable to get default mic. Available input devices:")
        for i, name, ch in list_input_devices():
            print(f"  [{i}] {name} (channels={ch})")
        raise RuntimeError("Please set sd.default.device = (input_id, output_id) or choose device manually.")

    loop = asyncio.get_running_loop()
    ctl = HotMicDeepgramController(loop, device=device)
    ctl.start_hot_mic()

    print("✅ Hot mic ON (capture is running continuously)")
    print("🎙️ Mic input device:", device)
    print("✅ Deepgram URL:", DG_URL)
    print(f"⏳ STOP flush tail audio: {FLUSH_MS} ms | grace={STOP_GRACE_S:.1f}s | log_tail_max={STREAM_LOG_MAX}")
    if USE_QWEN_NORM or USE_QWEN_TASK:
        print(f"🤖 Ollama: {OLLAMA_BASE_URL}")
        print(f"   - Qwen#1 (normalize): {QWEN_NORM_MODEL} | enabled={USE_QWEN_NORM}")
        print(f"   - Qwen#2 (task/pick): {QWEN_TASK_MODEL} | enabled={USE_QWEN_TASK}")
    else:
        print("🤖 Qwen: OFF")

    print("\n📦 PLAN I/O:")
    print(f"  - PLAN_FILE: {plan_file}")
    print(f"  - WEB_TICK_FILE: {web_tick_file or '(none)'}")
    print(f"  - OUT_PLAN_FILE: {out_plan_file}")

    print("\n📌 INSTRUCTIONS:")
    print("  - Press ENTER to START streaming to Deepgram")
    print("  - Press ENTER again to STOP -> normalize -> build pick JSON")
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

                raw_full = safe_str(asr.get("raw_full"))
                last_interim = safe_str(asr.get("last_interim"))

                print("\n====================")
                print("📝 Deepgram RAW (final-only):")
                print(raw_full if raw_full else "(no final transcript)")
                if last_interim:
                    print("--------------------")
                    print("… Last interim (may contain missing words):")
                    print(last_interim)
                print("====================\n")

                # ----------------------
                # Qwen#1: normalization
                # ----------------------
                normalized = ""
                if USE_QWEN_NORM and safe_str(asr.get("spoken_trace")):
                    payload = {
                        "spoken_trace": asr.get("spoken_trace", ""),
                        "stream_log_tail": asr.get("stream_log_tail", []),
                        "final_segments": asr.get("final_segments", []),
                        "raw_full": raw_full,
                        "last_interim": last_interim,
                    }
                    normalized = safe_str(await normalize_with_qwen(loop, payload))
                    print("✨ QWEN#1 NORMALIZED:")
                    print(normalized or "(empty)")
                    print()
                else:
                    normalized = raw_full or last_interim
                    print("ℹ️ Qwen#1 skipped -> using raw transcript.\n")

                # ----------------------
                # Load plan template + web ticks
                # ----------------------
                template = read_json_file(plan_file)
                if not isinstance(template, dict):
                    print(f"⚠️ PLAN_FILE not found/invalid -> using default template. (file={plan_file})")
                    template = plan_template_default()

                web_obj = read_json_file(web_tick_file) if web_tick_file else None
                web_pick_map = web_tick_to_pick_map(web_obj)
                template_with_web = apply_web_ticks_to_template(template, web_pick_map)

                base_plan = normalize_plan_shape(template_with_web, template_with_web)

                # ----------------------
                # Qwen#2: build pick plan JSON
                # ----------------------
                reply = ""
                plan_out = {}
                if USE_QWEN_TASK and normalized:
                    reply, plan_out = await plan_with_qwen(loop, normalized, base_plan)

                # Fallback if Qwen#2 failed
                if not plan_out:
                    plan_out = base_plan
                    reply = reply or "Mình đã tạo kế hoạch (giữ nguyên trạng thái hiện tại)."

                # Normalize output plan to strict shape and set selection_source
                plan_out = normalize_plan_shape(plan_out, base_plan)

                has_web = bool(web_pick_map) or bool(web_tick_file)
                plan_out["selection_source"] = {
                    "mode": "mixed" if has_web else "voice_only",
                    "web_tick": bool(has_web),
                    "voice_llm": True,
                }

                # Print + save
                print("🤖 QWEN#2 REPLY:")
                print(reply)
                print("\n📦 PICK PLAN JSON:")
                print(json.dumps(plan_out, ensure_ascii=False, indent=2))

                try:
                    write_json_file(out_plan_file, plan_out)
                    print(f"\n💾 Saved: {os.path.abspath(out_plan_file)}\n")
                except Exception as e:
                    print(f"\n⚠️ Failed to save OUT_PLAN_FILE: {e}\n")

        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except (ConnectionClosed, InvalidStatusCode) as e:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=PLAN_FILE, help="Path to plan template JSON (3x3 grid items).")
    ap.add_argument("--web", default=WEB_TICK_FILE, help="Optional web tick JSON file.")
    ap.add_argument("--out", default=OUT_PLAN_FILE, help="Output plan JSON file.")
    args = ap.parse_args()
    asyncio.run(run(args.plan, args.web, args.out))


if __name__ == "__main__":
    main()
