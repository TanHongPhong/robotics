# YOLO OpenCV Stream - Hướng dẫn sử dụng

## 📝 Mô tả

File `yolo_opencv_stream.py` là một YOLO stream độc lập chạy bằng OpenCV, **KHÔNG liên quan** đến React frontend. Stream này sẽ mở một cửa sổ riêng để hiển thị kết quả phát hiện từ YOLO.

## 🚀 Cách chạy

### 1. Chạy với cấu hình mặc định
```bash
cd d:\robotics\robotics\python_backend
python yolo_opencv_stream.py
```

### 2. Chạy với tùy chọn

#### Chỉ định file weights khác
```bash
python yolo_opencv_stream.py --weights "path/to/your/weights.pt"
```

#### Chọn camera khác (nếu có nhiều camera)
```bash
python yolo_opencv_stream.py --cam 1
```

#### Thay đổi confidence threshold
```bash
python yolo_opencv_stream.py --conf 0.7
```

#### Bật xoay khung hình 90° (counter-clockwise)
```bash
python yolo_opencv_stream.py --rotate
```

#### Thay đổi độ phân giải camera
```bash
python yolo_opencv_stream.py --width 1280 --height 720
```

### 3. Kết hợp nhiều tùy chọn
```bash
python yolo_opencv_stream.py --weights "C:\AI_Robotics\runs\robotics_detector\weights\best.pt" --conf 0.6 --rotate --cam 0
```

## ⚙️ Tham số cấu hình

| Tham số | Mặc định | Mô tả |
|---------|----------|-------|
| `--weights` | `C:\AI_Robotics\runs\robotics_detector\weights\best.pt` | Đường dẫn đến file weights YOLO |
| `--cam` | `0` | Index của camera (0 = camera mặc định) |
| `--fps` | `30` | FPS mục tiêu cho camera |
| `--width` | `1920` | Chiều rộng khung hình |
| `--height` | `1080` | Chiều cao khung hình |
| `--imgsz` | `640` | Kích thước ảnh cho YOLO inference |
| `--conf` | `0.5` | Ngưỡng confidence cho detection |
| `--iou` | `0.0` | Ngưỡng IoU cho NMS |
| `--rotate` | `False` | Bật xoay khung hình 90° CCW |

## 🎮 Điều khiển

- **`q`** hoặc **`ESC`**: Thoát stream
- **`Ctrl+C`**: Dừng chương trình

## 📊 Thông tin hiển thị

Stream sẽ hiển thị:
- ✅ FPS thực tế
- ✅ Confidence threshold
- ✅ Số lượng detections trong frame
- ✅ Bounding boxes và labels từ YOLO

## 🔧 Tích hợp với Backend

Nếu bạn muốn stream này **tự động chạy** khi khởi động backend Flask/FastAPI, có thể:

### Cách 1: Chạy trong subprocess (recommended)

Thêm vào `app.py` hoặc file backend chính:

```python
import subprocess
import threading

def start_yolo_stream():
    """Chạy YOLO stream trong subprocess riêng"""
    subprocess.Popen([
        "python", 
        "yolo_opencv_stream.py",
        "--conf", "0.5",
        "--rotate"  # nếu cần xoay
    ])

# Chạy khi khởi động backend
threading.Thread(target=start_yolo_stream, daemon=True).start()
```

### Cách 2: Chạy trong thread riêng

```python
import threading
from yolo_opencv_stream import main as yolo_main

# Chạy YOLO stream trong thread riêng
yolo_thread = threading.Thread(target=yolo_main, daemon=True)
yolo_thread.start()
```

> **⚠️ Lưu ý**: Cách 1 (subprocess) được khuyến nghị vì tách biệt hoàn toàn, tránh xung đột GIL của Python.

## 🎯 Use Cases

1. **Development**: Chạy riêng để test YOLO model mà không cần frontend
2. **Debugging**: Xác minh YOLO hoạt động đúng trước khi tích hợp
3. **Dual Display**: Hiển thị webcam trên React + YOLO stream trên cửa sổ OpenCV cùng lúc
4. **Production**: Chạy song song với React frontend để có 2 view khác nhau

## 💡 Tips

- Stream này **độc lập hoàn toàn** với React frontend
- Web frontend của bạn vẫn có thể hiển thị webcam bình thường
- YOLO stream sẽ mở cửa sổ OpenCV riêng
- Phù hợp cho việc monitoring hoặc debugging

## 🐛 Troubleshooting

### Camera không mở được
```bash
# Thử camera index khác
python yolo_opencv_stream.py --cam 1
```

### Weights không tìm thấy
```bash
# Kiểm tra đường dẫn weights
python yolo_opencv_stream.py --weights "đường/dẫn/chính/xác/best.pt"
```

### FPS thấp
```bash
# Giảm resolution hoặc YOLO image size
python yolo_opencv_stream.py --width 1280 --height 720 --imgsz 416
```
