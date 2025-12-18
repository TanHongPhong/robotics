import os
import json
import time
import threading
from datetime import datetime

import cv2
import serial
from serial.tools import list_ports
from ultralytics import YOLO
from flask import Flask, request, jsonify
from flask_cors import CORS

# ===================== CONFIG =====================
PORT = "COM4"                 # AUTO = tự động tìm, hoặc "COMx" (Windows) / "/dev/ttyUSBx" (Linux)
BAUD = 115200
CAM_INDEX = 0
MODEL_PATH = r"C:\AI_Robotics\runs\robotics_detector\weights\best.pt"

JSON_PATH = "scan_results.json"
CAP_DIR = "captures"
# =================================================


# ================= GLOBAL STATE ==================
lock = threading.Lock()

state = {
    "mode": 1,
    "selected_ids": set(),
    "scan": {},                 # {"P1": {"id":..}}
    "running": True,
    "scan_session_ts": None,
}
# =================================================


# ================= UTILS =========================
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_cap_dir():
    os.makedirs(CAP_DIR, exist_ok=True)


def save_json():
    with lock:
        data = {
            "time": now(),
            "mode": state["mode"],
            "selected_class_ids": sorted(list(state["selected_ids"])),
            "scan": state["scan"],
        }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json():
    if not os.path.exists(JSON_PATH):
        return False
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        with lock:
            state["scan"] = data.get("scan", {}) or {}
        return True
    except Exception:
        return False


def reset_json():
    with lock:
        state["scan"] = {}
    if os.path.exists(JSON_PATH):
        os.remove(JSON_PATH)
    print("[PY] JSON RESET")


def has_full_9_points(scan_dict):
    # need P1..P9 present
    for i in range(1, 10):
        if f"P{i}" not in scan_dict:
            return False
    return True


def send_line(ser, s):
    if ser:
        ser.write((s.strip() + "\n").encode("utf-8"))
# =================================================


# ================= AUTO DETECT PORT ==============
def auto_detect_port():
    """Tự động tìm cổng serial của Arduino"""
    ports = list(list_ports.comports())
    if not ports:
        return None
    
    print("\n📡 Các cổng serial khả dụng:")
    for i, p in enumerate(ports):
        print(f"  {i+1}. {p.device} - {p.description}")
    
    # Ưu tiên các từ khóa Arduino
    keywords = ["arduino", "ch340", "usb serial", "wch", "silicon labs", "cp210"]
    for p in ports:
        desc = f"{p.device} {p.description}".lower()
        if any(k in desc for k in keywords):
            print(f"✅ Tự động chọn: {p.device}")
            return p.device
    
    # Nếu không tìm thấy, trả về port đầu tiên
    if ports:
        print(f"⚠️ Không tìm thấy Arduino, chọn: {ports[0].device}")
        return ports[0].device
    
    return None
# =================================================


# ================= YOLO ==========================
def print_class_table(model):
    print("\n===== YOLO CLASS TABLE =====")
    for k in sorted(model.names.keys()):
        print(f"{k:>2}: {model.names[k]}")
    print("============================\n")


def infer_best(model, frame):
    res = model.predict(frame, verbose=False)[0]
    if not res.boxes or len(res.boxes) == 0:
        return -1, "none", 0.0

    confs = res.boxes.conf.cpu().numpy()
    idx = confs.argmax()

    cid = int(res.boxes.cls.cpu().numpy()[idx])
    return cid, model.names[cid], float(confs[idx])
# =================================================


# ================= CAMERA ========================
def capture_and_detect(cap, model, p_label):
    ok, frame = cap.read()
    if not ok or frame is None:
        return -1, "none", 0.0, None

    ensure_cap_dir()
    img_path = os.path.join(CAP_DIR, f"{p_label}.jpg")
    cv2.imwrite(img_path, frame)

    cid, cname, conf = infer_best(model, frame)
    return cid, cname, conf, img_path
# =================================================


# ================= MODE2 LIST BUILDER =============
def build_list_command():
    with lock:
        selected = set(state["selected_ids"])
        scan = dict(state["scan"])

    targets = []
    for i in range(1, 10):
        p = f"P{i}"
        if p in scan and scan[p].get("id", -1) in selected:
            targets.append(p)

    cmd = "LIST " + " ".join(targets) if targets else "LIST"
    return cmd
# =================================================


# ================= SERIAL THREAD =================
def reader_thread(ser, cap, model):
    buf = ""
    while state["running"]:
        try:
            c = ser.read(1)
            if not c:
                continue
            ch = c.decode(errors="ignore")

            if ch != "\n":
                buf += ch
                if len(buf) > 400:
                    buf = buf[-400:]
                continue

            line = buf.strip()
            buf = ""
            if not line:
                continue

            print("[ARDUINO]", line)

            # EVT ARRIVED Pn
            if line.startswith("EVT ARRIVED P"):
                p = line.split()[-1]  # "P3"

                with lock:
                    mode = state["mode"]
                    selected = set(state["selected_ids"])

                if mode == 3:
                    # mode3 no AI decisions, but in case:
                    send_line(ser, "DEC SKIP")
                    continue

                cid, cname, conf, img = capture_and_detect(cap, model, p)

                with lock:
                    state["scan"][p] = {
                        "id": cid,
                        "name": cname,
                        "conf": round(conf, 4),
                        "time": now(),
                        "img": img
                    }
                save_json()

                if mode == 1:
                    if cid in selected:
                        send_line(ser, "DEC PICK")
                        print(f"[PY] DEC PICK {p} -> {cid}:{cname} ({conf:.2f})")
                    else:
                        send_line(ser, "DEC SKIP")
                        print(f"[PY] DEC SKIP {p} -> {cid}:{cname} ({conf:.2f})")

                elif mode == 2:
                    # scan phase: always skip
                    send_line(ser, "DEC SKIP")
                    print(f"[PY] MODE2 SCAN {p} -> {cid}:{cname} ({conf:.2f})")

            # SCAN_DONE: mode2 only
            if line == "SCAN_DONE":
                cmd = build_list_command()
                send_line(ser, cmd)
                print("[PY] ->", cmd)

        except Exception as e:
            print("[PY] SERIAL ERROR:", e)
            break
# =================================================


# ================= TERMINAL HELPERS ==============
def parse_ids(s):
    return {int(x) for x in s.replace(",", " ").split() if x.isdigit()}
# =================================================


def interactive_offset(ser):
    axis = input("Chọn trục offset (x/y): ").strip().lower()
    if axis not in ("x", "y"):
        print("[PY] Trục không hợp lệ.")
        return
    val_str = input("Nhập mm (vd 5 hoặc -3): ").strip()
    try:
        val = float(val_str)
    except:
        print("[PY] mm không hợp lệ.")
        return

    dx, dy = (val, 0.0) if axis == "x" else (0.0, val)
    send_line(ser, f"OFFSET {dx} {dy}")
    print(f"[PY] Sent OFFSET dx={dx} dy={dy}")


def mode2_maybe_skip_scan_and_send_list(ser):
    # called right after user types START in mode2
    load_json()
    with lock:
        full = has_full_9_points(state["scan"])

    if full:
        cmd = build_list_command()
        print("[PY] JSON đã đủ P1..P9 -> skip scan, gửi LIST ngay")
        send_line(ser, cmd)
        print("[PY] ->", cmd)
        return True
    return False


def mode1_prepare_new_scan():
    # Mode1 always re-scan: clear old scan and json
    reset_json()
# =================================================


def main():
    print("[PY] Loading YOLO...")
    model = YOLO(MODEL_PATH)
    print_class_table(model)

    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print("❌ Cannot open camera")
        return

    # Auto-detect serial port nếu PORT rỗng
    port = PORT.strip()
    if not port or port.upper() == "AUTO":
        port = auto_detect_port()
    
    ser = None
    if port:
        try:
            print(f"\n[PY] Opening serial: {port}")
            ser = serial.Serial(port, BAUD, timeout=0.05)
            time.sleep(2)
            print("✅ Serial port opened successfully")
        except serial.SerialException as e:
            print(f"⚠️ Không thể mở cổng {port}: {e}")
            print("⚠️ Chạy ở TEST MODE (không có Arduino)")
            ser = None
    else:
        print("⚠️ Không tìm thấy cổng serial. Chạy ở TEST MODE")

    load_json()

    if ser:
        t = threading.Thread(target=reader_thread, args=(ser, cap, model), daemon=True)
        t.start()
    else:
        print("ℹ️ Serial reader thread không được khởi động (TEST MODE)")

    print("=== PYTHON ROBOT TERMINAL (event-based) ===")
    if not ser:
        print("⚠️ TEST MODE - Không kết nối Arduino")
    print("Flow: H0 -> (class ids) -> MODE n -> START")
    print("Commands:")
    print("  reset            : xóa JSON")
    print("  offset           : nhập offset x/y mm (gửi OFFSET dx dy)")
    print("  show             : xem scan RAM")
    print("  class list       : vd 3 4 11")
    print("  MODE 1/2/3        ")
    print("  START / H0 / STOP / UNSTOP")
    print("  exit\n")

    while True:
        s = input(">> ").strip()
        if not s:
            continue

        if s.lower() in ("exit", "quit"):
            break

        if s.lower() == "reset":
            reset_json()
            continue

        if s.lower() == "show":
            with lock:
                print(json.dumps(state["scan"], ensure_ascii=False, indent=2))
            continue

        if s.lower() == "offset":
            interactive_offset(ser)
            continue

        # class list: only numbers/space/comma
        if all(ch.isdigit() or ch in " ,-" for ch in s) and any(ch.isdigit() for ch in s):
            ids = parse_ids(s)
            with lock:
                state["selected_ids"] = ids
            save_json()
            print("[PY] selected_class_ids =", sorted(ids))
            continue

        # MODE n
        if s.upper().startswith("MODE"):
            try:
                m = int(s.split()[-1])
                with lock:
                    state["mode"] = m
            except:
                pass
            send_line(ser, s)
            continue

        # START
        if s.upper() == "START":
            with lock:
                m = state["mode"]

            if m == 1:
                # mode1 always reset old scan/json and rescan realtime
                mode1_prepare_new_scan()
                send_line(ser, "START")
                continue

            if m == 2:
                # if already have full json, skip scan and send LIST immediately
                skipped = mode2_maybe_skip_scan_and_send_list(ser)
                if skipped:
                    # No need to start scan on Arduino. We can either:
                    # - keep Arduino idle and user can send manual GOTO/PICK, OR
                    # - start mode2 anyway (it will scan again). We DON'T want that.
                    # So we DO NOT send START when skipped.
                    print("[PY] (Mode2) Không gửi START, Arduino không scan lại.")
                else:
                    send_line(ser, "START")
                continue

            if m == 3:
                send_line(ser, "START")
                continue

        # default: forward to Arduino
        send_line(ser, s)

    state["running"] = False
    if ser:
        ser.close()
    cap.release()
    print("[PY] EXIT")


if __name__ == "__main__":
    main()