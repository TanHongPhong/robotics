import os
import json
import time
import threading
from datetime import datetime

import cv2
import serial
from ultralytics import YOLO

# ===================== CONFIG =====================
PORT = "COM4"   # <<< SỬA >>>
BAUD = 115200
CAM_INDEX = 0
MODEL_PATH = "best.pt"

JSON_PATH = "scan_results.json"
CAP_DIR = "captures"
# =================================================


# ================= GLOBAL STATE ==================
lock = threading.Lock()

state = {
    "mode": 1,
    "selected_ids": set(),
    "scan": {},
    "running": True,
    "mode2_scanning": False,
}
# =================================================


# ================= UTILS =========================
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_cap_dir():
    os.makedirs(CAP_DIR, exist_ok=True)


def reset_scan_file():
    if os.path.exists(JSON_PATH):
        os.remove(JSON_PATH)


def reset_scan_ram_and_file():
    with lock:
        state["scan"] = {}
    reset_scan_file()
    print("[PY] MODE2 SCAN RESET (delete old JSON)")


def save_json(scan_dict):
    data = {
        "time": now(),
        "scan": scan_dict,
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json_scan():
    if not os.path.exists(JSON_PATH):
        return {}
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("scan", {}) or {}
    except Exception:
        return {}


def send_line(ser, s):
    ser.write((s.strip() + "\n").encode("utf-8"))
# =================================================


# ================= YOLO ==========================
def infer_best(model, frame):
    res = model.predict(frame, verbose=False)[0]
    if not res.boxes:
        return -1, "none", 0.0
    confs = res.boxes.conf.cpu().numpy()
    idx = confs.argmax()
    cid = int(res.boxes.cls.cpu().numpy()[idx])
    return cid, model.names[cid], float(confs[idx])
# =================================================


# ================= CAMERA ========================
def capture_and_detect(cap, model, p):
    ok, frame = cap.read()
    if not ok or frame is None:
        return -1, "none", 0.0, None

    ensure_cap_dir()
    path = os.path.join(CAP_DIR, f"{p}.jpg")
    cv2.imwrite(path, frame)

    cid, cname, conf = infer_best(model, frame)
    return cid, cname, conf, path
# =================================================


# ================= MODE2 LIST ====================
def build_list_from_scan(scan, selected_ids):
    out = []
    for i in range(1, 10):
        p = f"P{i}"
        if p in scan and scan[p].get("id", -1) in selected_ids:
            out.append(p)
    return "LIST " + " ".join(out) if out else "LIST"
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
                if len(buf) > 600:
                    buf = buf[-600:]
                continue

            line = buf.strip()
            buf = ""
            if not line:
                continue

            print("[ARDUINO]", line)

            # EVT ARRIVED Px
            if line.startswith("EVT ARRIVED P"):
                p = line.split()[-1]  # Px

                with lock:
                    mode = state["mode"]
                    scanning = state["mode2_scanning"]
                    selected = set(state["selected_ids"])

                cid, cname, conf, img = capture_and_detect(cap, model, p)

                # MODE2 SCAN: always save + always SKIP
                if mode == 2 and scanning:
                    with lock:
                        state["scan"][p] = {
                            "id": cid,
                            "name": cname,
                            "conf": round(conf, 4),
                            "time": now(),
                            "img": img,
                        }
                        snap = dict(state["scan"])

                    save_json(snap)
                    send_line(ser, "DEC SKIP")  # Arduino ignores in mode2 (safe to still send)
                    print(f"[MODE2 SCAN] {p} -> {cid}:{cname} ({conf:.2f})")
                    continue

                # MODE1: live decision, NO JSON
                if mode == 1:
                    if cid in selected:
                        send_line(ser, "DEC PICK")
                        print(f"[MODE1] PICK {p} -> {cid}:{cname} ({conf:.2f})")
                    else:
                        send_line(ser, "DEC SKIP")
                        print(f"[MODE1] SKIP {p} -> {cid}:{cname} ({conf:.2f})")
                    continue

                # other modes: default safe
                send_line(ser, "DEC SKIP")

            # SCAN_DONE (mode2 scan finished)
            if line == "SCAN_DONE":
                with lock:
                    state["mode2_scanning"] = False
                print("[PY] MODE2 SCAN DONE (JSON saved). Robot should be HOME+IDLE now.")

        except Exception as e:
            print("[PY] SERIAL ERROR:", e)
            break
# =================================================


def parse_ids(s):
    return {int(x) for x in s.replace(",", " ").split() if x.isdigit()}


def mode3_loop(ser):
    print("\n[MODE3] Nhập P (vd P3) | quit để thoát")
    while True:
        s = input("P> ").strip().upper()
        if s == "QUIT":
            print("[MODE3] Thoát")
            return
        if len(s) == 2 and s[0] == "P" and s[1].isdigit():
            send_line(ser, f"GOTO {s}")
            time.sleep(0.1)
            send_line(ser, "PICKNOW")
            print(f"[MODE3] PICK {s}")
        else:
            print("[MODE3] Sai định dạng")


# ================= MAIN ==========================
def main():
    print("[PY] Loading YOLO:", MODEL_PATH)
    model = YOLO(MODEL_PATH)

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print("[PY][ERR] Cannot open camera")
        return

    print("[PY] Opening serial:", PORT)
    ser = serial.Serial(PORT, BAUD, timeout=0.05)
    time.sleep(2)

    # preload scan into RAM (optional)
    with lock:
        state["scan"] = load_json_scan()

    threading.Thread(target=reader_thread, args=(ser, cap, model), daemon=True).start()

    print("\n=== TERMINAL ROBOT CONTROL ===")
    print("Flow:")
    print("  H0")
    print("  <class ids>   (vd: 3 4 11)")
    print("  MODE 1/2/3")
    print("  MODE1: START")
    print("  MODE2: SCAN (tạo JSON mới) | START (dùng JSON hiện có để pick)")
    print("Commands: H0 | MODE n | START | SCAN | STOP | UNSTOP | quit\n")

    while True:
        s = input(">> ").strip()
        if not s:
            continue

        if s.lower() in ("quit", "exit"):
            break

        if s.upper() == "H0":
            send_line(ser, "H0")
            continue

        # input class ids
        if all(ch.isdigit() or ch in " ,-" for ch in s) and any(ch.isdigit() for ch in s):
            ids = parse_ids(s)
            with lock:
                state["selected_ids"] = ids
            print("[PY] selected_class_ids =", sorted(ids))
            continue

        # MODE n
        if s.upper().startswith("MODE"):
            try:
                m = int(s.split()[-1])
            except Exception:
                print("[PY][ERR] Use: MODE 1|2|3")
                continue

            with lock:
                state["mode"] = m
                state["mode2_scanning"] = False

            send_line(ser, f"MODE {m}")
            print(f"[PY] MODE {m}")

            if m == 3:
                mode3_loop(ser)
                with lock:
                    state["mode"] = 1
                print("[PY] Quay lại chọn class / mode")
            continue

        # MODE2 SCAN (explicit only)
        if s.upper() == "SCAN":
            with lock:
                if state["mode"] != 2:
                    print("[PY][ERR] SCAN chỉ dùng trong MODE 2")
                    continue
                state["mode2_scanning"] = True
                state["scan"] = {}

            reset_scan_ram_and_file()

            # This triggers Arduino MODE2 scan-only run
            send_line(ser, "START")
            print("[PY] MODE2 SCAN started (Arduino START).")
            continue

        # START
        if s.upper() == "START":
            with lock:
                m = state["mode"]
                selected = set(state["selected_ids"])

            if m == 1:
                send_line(ser, "START")
                continue

            if m == 2:
                scan = load_json_scan()
                if not scan:
                    print('[PY][ERR] No scan data, please SCAN first')
                    continue
                cmd = build_list_from_scan(scan, selected)
                send_line(ser, cmd)  # ✅ this triggers MODE2 pick directly (Arduino does NOT scan)
                print("[MODE2 PICK] ->", cmd)
                continue

            if m == 3:
                print("[PY] MODE3: dùng menu mode3 (P>), không dùng START.")
                continue

        # passthrough
        send_line(ser, s)

    state["running"] = False
    ser.close()
    cap.release()
    print("[PY] EXIT")


if __name__ == "__main__":
    main()