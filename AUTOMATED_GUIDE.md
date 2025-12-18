# HƯỚNG DẪN CHẠY HỆ THỐNG TỰ ĐỘNG

## 🚫 DỪNG CÁC PROCESS CŨ

Bấm Ctrl+C trong các terminal sau:
- Terminal chạy `python main.py` (interactive mode) - DỪNG LẠI
- Terminal chạy `python arduino_api.py` - DỪNG LẠI  
- Terminal chạy `python app.py` - KHÔNG CẦN (nếu có)

## ✅ CHẠY HỆ THỐNG MỚI (TỰ ĐỘNG)

### Bước 1: Chạy Main Automated (thay thế main.py + arduino_api.py)

```bash
cd python_backend
python main_automated.py
```

**Điều này sẽ:**
- ✅ Mở serial COM4 (kết nối Arduino)
- ✅ Load YOLO model
- ✅ Mở camera
- ✅ Chạy Flask API trên port 5001
- ✅ Tự động nhận lệnh từ frontend (không cần nhập tay)

### Bước 2: Chạy Frontend (nếu chưa chạy)

```bash
cd frontend
npm run dev
```

### Bước 3: Chạy Backend chính (nếu cần LLM/Chat)

```bash
cd python_backend
python app.py
```

## 🎯 KIỂM TRA HỆ THỐNG

### Test API:
```bash
# Test health check
curl http://localhost:5001/health

# Test status
curl http://localhost:5001/api/status

# Test home command
curl -X POST http://localhost:5001/api/arduino/command -H "Content-Type: application/json" -d "{\"command\": \"home\"}"

# Test start command với class_ids
curl -X POST http://localhost:5001/api/arduino/command -H "Content-Type: application/json" -d "{\"command\": \"start\", \"class_ids\": [3, 7, 11]}"
```

## 📝 LUỒNG HOẠT ĐỘNG MỚI

```
Frontend (localhost:5173)
    ↓ HTTP POST
main_automated.py (localhost:5001)
    ↓ Serial (COM4)
Arduino
    ↓ Serial response
main_automated.py (serial reader thread)
    ↓ YOLO detection
Decision: DEC PICK / DEC SKIP
```

## 🎮 SỬ DỤNG GIAO DIỆN

1. Mở trình duyệt: `http://localhost:5173`
2. **Chọn các ô** cần lấy (ví dụ: ô 1, 2, 3)
3. **Bấm HOME**: Robot về vị trí home (H0)
4. **Bấm START**: 
   - Gửi class_ids đã chọn: `[0, 1, 2]`
   - Robot bắt đầu scan
   - YOLO detect và quyết định PICK/SKIP
5. **Bấm STOP**: Dừng robot khẩn cấp

## ⚙️ CẤU HÌNH

Nếu cần thay đổi COM port, sửa trong `main_automated.py`:

```python
PORT = "COM4"  # Thay đổi nếu cần
```

## 🐛 DEBUG

Nếu có lỗi:
1. Check terminal `main_automated.py` xem có log không
2. Check Arduino có phản hồi không
3. Check browser console có lỗi HTTP không
4. Kiểm tra COM port có đang bị chiếm bởi process khác không

## 📊 SO SÁNH

| Trước (Manual)          | Sau (Automated)         |
|------------------------|-------------------------|
| 2 scripts riêng        | 1 script duy nhất       |
| Nhập tay lệnh          | Tự động qua HTTP        |
| main.py + arduino_api  | main_automated.py       |
| Interactive terminal   | Background service      |

## ✨ ƯU ĐIỂM

- ✅ Không cần nhập tay
- ✅ Giao diện web điều khiển đầy đủ
- ✅ Tự động detect và quyết định PICK/SKIP
- ✅ Dễ debug qua HTTP logs
- ✅ Không conflict COM port
