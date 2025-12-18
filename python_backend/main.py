import os, json, time, threading
from datetime import datetime
import cv2
import numpy as np
import serial
from serial.tools import list_ports
from ultralytics import YOLO
from flask import Flask, request, jsonify
from flask_cors import CORS

# Config
PORT = "COM4"
BAUD = 115200
MODEL_PATH = r"C:\AI_Robotics\runs\robotics_detector\weights\best.pt"

# Global
state = {"mode": 1, "selected_ids": set(), "scan": {}, "running": True}
lock = threading.Lock()
ser, cap, model = None, None, None

# Flask
app = Flask(__name__)
CORS(app)

# Utils
def send_line(s):
    if ser: ser.write((s + "\n").encode())

def save_json():
    with lock:
        with open("scan_results.json", "w") as f:
            json.dump({"selected_ids": list(state["selected_ids"]), "scan": state["scan"]}, f)

# YOLO helpers
def crop_frame(frame):
    """Crop frame to reduce height by 20%, focus on upper region"""
    h, w = frame.shape[:2]
    crop_h = int(h * 0.2)  # Total amount to remove (20%)
    
    # Shift center upward MORE: remove very little from top, most from bottom
    top_crop = int(crop_h * 0.15)  # Remove only 15% of crop from top (3% of original height)
    bottom_crop = h - (crop_h - top_crop)  # Remove 85% of crop from bottom (17% of original height)
    
    return frame[top_crop:bottom_crop, :]

def sharpen_frame(frame):
    """Apply sharpening filter to enhance image quality"""
    # Create sharpening kernel
    kernel = np.array([
        [-1, -1, -1],
        [-1,  9, -1],
        [-1, -1, -1]
    ])
    # Apply kernel
    sharpened = cv2.filter2D(frame, -1, kernel)
    return sharpened

def infer_best(frame):
    # Crop frame before inference
    cropped = crop_frame(frame)
    # Sharpen for better quality
    sharpened = sharpen_frame(cropped)
    # iou=0.0: no overlap tolerance
    # agnostic_nms=True: NMS across all classes (prevent multi-class overlap)
    # conf=0.5: minimum confidence threshold (matching test.py)
    res = model.predict(sharpened, verbose=False, iou=0.0, agnostic_nms=True, conf=0.5)[0]
    if not res.boxes or len(res.boxes) == 0:
        return -1, "none", 0.0
    
    # Get image center
    img_h, img_w = sharpened.shape[:2]
    img_center_x = img_w / 2
    img_center_y = img_h / 2
    
    # Find box with center closest to image center
    boxes = res.boxes.xyxy.cpu().numpy()
    confs = res.boxes.conf.cpu().numpy()
    classes = res.boxes.cls.cpu().numpy()
    
    min_dist = float('inf')
    best_idx = 0
    
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box
        # Calculate box center
        box_center_x = (x1 + x2) / 2
        box_center_y = (y1 + y2) / 2
        # Calculate distance to image center
        dist = np.sqrt((box_center_x - img_center_x)**2 + (box_center_y - img_center_y)**2)
        
        if dist < min_dist:
            min_dist = dist
            best_idx = i
    
    # Return the object closest to center
    cid = int(classes[best_idx])
    return cid, model.names[cid], float(confs[best_idx])

# Video stream display thread
def video_stream_thread():
    """Display camera feed with YOLO detection in OpenCV window"""
    print("🎥 Starting video stream display...")
    window_name = "YOLO Detection Stream - Press 'q' to close"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 600)
    
    while state["running"]:
        try:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            
            # Crop frame before inference (reduce height by 20%)
            cropped = crop_frame(frame)
            
            # Sharpen for better quality
            sharpened = sharpen_frame(cropped)
            
            # Run YOLO inference: iou=0.0, agnostic_nms=True, conf=0.5
            # This ensures no overlapping boxes and one class per object
            results = model.predict(sharpened, verbose=False, iou=0.0, agnostic_nms=True, conf=0.5)[0]
            
            # Draw detections on sharpened frame
            display_frame = sharpened.copy()
            
            if results.boxes and len(results.boxes) > 0:
                boxes = results.boxes.xyxy.cpu().numpy()
                confs = results.boxes.conf.cpu().numpy()
                classes = results.boxes.cls.cpu().numpy()
                
                for box, conf, cls in zip(boxes, confs, classes):
                    x1, y1, x2, y2 = map(int, box)
                    class_id = int(cls)
                    class_name = model.names[class_id]
                    confidence = float(conf)
                    
                    # Green color for all detections
                    color = (0, 255, 0)
                    
                    # Draw bounding box
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Draw label background
                    label = f"{class_name} {confidence:.2f}"
                    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.rectangle(display_frame, 
                                (x1, y1 - label_size[1] - 10), 
                                (x1 + label_size[0], y1), 
                                color, -1)
                    
                    # Draw label text
                    cv2.putText(display_frame, label, (x1, y1 - 5),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Show info
            cv2.putText(display_frame, "Press 'q' to close", (10, display_frame.shape[0] - 10),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Show frame
            cv2.imshow(window_name, display_frame)
            
            # Check for 'q' key to close
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("🎥 Closing video stream...")
                break
                
        except Exception as e:
            print(f"Video stream error: {e}")
            time.sleep(0.1)
    
    cv2.destroyAllWindows()
    print("🎥 Video stream closed")

# Serial reader
def reader_thread():
    buf = ""
    while state["running"]:
        try:
            c = ser.read(1)
            if not c: continue
            ch = c.decode(errors="ignore")
            if ch != "\n":
                buf += ch
                continue
            line = buf.strip()
            buf = ""
            if not line: continue
            
            print(f"[Arduino] {line}")
            
            if line.startswith("EVT ARRIVED P"):
                p = line.split()[-1]
                ok, frame = cap.read()
                if ok:
                    cv2.imwrite(f"captures/{p}.jpg", frame)
                    cid, cname, conf = infer_best(frame)
                    with lock:
                        state["scan"][p] = {"id": cid, "name": cname, "conf": round(conf, 4)}
                        selected = set(state["selected_ids"])
                    save_json()
                    
                    if cid in selected:
                        send_line("DEC PICK")
                        print(f"✅ PICK {p} -> {cid}:{cname}")
                    else:
                        send_line("DEC SKIP")
                        print(f"⏭️ SKIP {p} -> {cid}:{cname}")
        except: pass

# API
@app.route('/api/arduino/command', methods=['POST'])
def arduino_cmd():
    print(f"\n🔔 Received request to /api/arduino/command")
    print(f"   Headers: {dict(request.headers)}")
    data = request.get_json()
    print(f"   Data: {data}")
    cmd = data.get('command', '').lower() if data else ''
    print(f"   Command: {cmd}")
    
    if cmd == 'home':
        send_line("H0")
        return jsonify({"status": "ok", "message": "Home sent"})
    
    elif cmd == 'start':
        class_ids = data.get('class_ids', [])
        with lock:
            state["selected_ids"] = set(class_ids)
            state["scan"] = {}
        save_json()
        
        if class_ids:
            send_line(" ".join(map(str, class_ids)))
            time.sleep(0.05)
        send_line("MODE 1")
        time.sleep(0.05)
        send_line("START")
        return jsonify({"status": "ok", "message": f"Started with {class_ids}"})
    
    elif cmd == 'stop':
        send_line("STOP")
        return jsonify({"status": "ok", "message": "Stop sent"})
    
    return jsonify({"error": "Unknown command"}), 400

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

# Main
if __name__ == '__main__':
    print("🚀 Loading YOLO...")
    model = YOLO(MODEL_PATH)
    print("✅ YOLO loaded")
    
    # Initialize camera with Full HD resolution (matching test.py)
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # Stable quality codec
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)   # Full HD width
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)  # Full HD height
    cap.set(cv2.CAP_PROP_FPS, 30)             # 30 FPS standard
    
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = int(cap.get(cv2.CAP_PROP_FPS))
    print(f"📷 Camera: {actual_w}x{actual_h} @ {actual_fps} FPS")
    
    os.makedirs("captures", exist_ok=True)
    
    print(f"📡 Opening {PORT}...")
    ser = serial.Serial(PORT, BAUD, timeout=0.05)
    time.sleep(2)
    print("✅ Serial opened")
    
    # Start threads
    threading.Thread(target=reader_thread, daemon=True).start()
    threading.Thread(target=video_stream_thread, daemon=True).start()
    
    print("="*50)
    print("✅ Ready! API: http://localhost:5001")
    print("🎥 YOLO stream window opened (press 'q' to close)")
    print("="*50)
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)