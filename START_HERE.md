# 🚀 CHẠY HỆ THỐNG - ĐƠN GIẢN

## ⚠️ QUAN TRỌNG: Chỉ cần 3 process

1. **main.py** (Arduino + YOLO + API)
2. **app.py** (LLM/Chat - optional)
3. **npm run dev** (Frontend)

---

## 🛑 DỪNG CÁC PROCESS CŨ

Trong các terminal đang chạy, bấm **Ctrl+C** để dừng:
- ✅ Terminal `python main.py` (cũ) → **DỪNG**
- ✅ Terminal `python arduino_api.py` → **DỪNG**

**GIỮ LẠI:**
- ✅ `npm run dev` (Frontend)
- ✅ `python app.py` (LLM - nếu cần chat)

---

## ✅ CHẠY MỚI

### Terminal 1: Main (Arduino + YOLO + API)
```bash
cd python_backend
python main.py
```

**Bạn sẽ thấy:**
```
🚀 Loading YOLO...
✅ YOLO loaded
📡 Opening COM4...
✅ Serial opened
============================
✅ Ready! API: http://localhost:5001
============================
 * Running on http://0.0.0.0:5001
```

### Terminal 2: Frontend (nếu chưa chạy)
```bash
cd frontend
npm run dev
```

### Terminal 3: LLM/Chat (optional)
```bash
cd python_backend
python app.py
```

---

## 🎮 TEST

1. Mở trình duyệt: `http://localhost:5173`
2. **Bấm HOME** → Terminal main.py sẽ log: `[Arduino] ...`
3. **Chọn 3 ô** (ví dụ: ô 1, 2, 3)
4. **Bấm START** → Robot bắt đầu
5. **Bấm STOP** → Robot dừng

---

## 🐛 DEBUG

Nếu nút không hoạt động:

1. **Check main.py terminal** - Có log `[Arduino]` không?
2. **Check browser console** (F12) - Có lỗi fetch không?
3. **Check port** - `netstat -ano | findstr :5001`
   - Nếu không thấy → main.py chưa chạy
4. **Check Arduino** - Có kết nối COM4 không?

---

## 📂 CẤU TRÚC FILE (ĐÃ DỌN DẸP)

```
python_backend/
  ├── main.py          ⭐ CHÍNH - Arduino + YOLO + Flask API
  ├── app.py           ⭐ LLM/Chat (port 5000)
  ├── llm_service.py
  ├── stt_deepgram.py
  └── data/
      └── inventory.json

frontend/
  └── ... (React app)
```

**Đã XÓA (files thừa):**
- ❌ arduino_api.py
- ❌ arduino_api_bridge.py
- ❌ serial_bridge.py
- ❌ command_bridge.py
- ❌ main_automated.py
- ❌ main_with_bridge.py
- ❌ PATCH_main.py

---

## ✨ TẤT CẢ TRONG 1 FILE

**main.py** bây giờ có TẤT CẢ:**
- ✅ Serial communication (COM4)
- ✅ YOLO detection
- ✅ Flask API (port 5001)
- ✅ Nhận lệnh từ frontend (HOME/START/STOP)
- ✅ Tự động PICK/SKIP

**Chỉ 130 dòng code - Đơn giản và rõ ràng!**
