# Mode 1/2 Implementation Documentation

## Tổng Quan

Hệ thống robot hiện đã hỗ trợ 2 MODE hoạt động:

### MODE 1: Gắp theo lựa chọn (Live Pick)
- Giao diện: Lưới 4×4 danh sách vật cần lấy
- Cách hoạt động:
  1. Người dùng chọn các sản phẩm cần lấy trên giao diện web
  2. Nhấn START → Robot bắt đầu scan từng ô
  3. Tại mỗi ô: Camera phát hiện vật → So sánh với danh sách đã chọn
  4. Nếu khớp → PICK, nếu không → SKIP
  5. Hoàn tất → Về HOME

### MODE 2: Scan kệ + Gắp (Scan then Pick)
- Giao diện: **GIỐNG HỆT MODE 1** (lưới 4×4)
- Cách hoạt động:
  1. Nhấn nút SCAN → Robot scan toàn bộ 9 ô, lưu kết quả vào `inventory_scan.json`
  2. Người dùng chọn các sản phẩm cần lấy
  3. Nhấn START → Robot chỉ đến các ô có vật đã chọn và gắp (KHÔNG SCAN LẠI)
  4. Hoàn tất → Về HOME

## Thay Đổi Frontend

### Files Mới/Cập Nhật:
1. **`frontend/src/pages/InventoryPage.jsx`** (CREATED)
   - Component chính cho trang Inventory
   - Quản lý state cho Mode 1/2
   - Xử lý các nút: Mode Toggle, Scan, Home, Start/Stop
   - Hiển thị lưới 4×4 sản phẩm

2. **`frontend/src/pages/InventoryPage.css`** (UPDATED)
   - Style cho control panel mới
   - Style cho nút Mode, Scan, Home, Start/Stop
   - Responsive design

3. **`frontend/src/components/ProductCard.jsx`** (UPDATED)
   - Thêm props: `onClick`, `disabled`
   - Thêm hiển thị trạng thái `done`

4. **`frontend/src/components/ProductCard.css`** (UPDATED)
   - Thêm style cho trạng thái `disabled` và `done`
   - Thêm `done-badge` styling

### Giao Diện Mới:

```
┌─────────────────────────────────────────────────┐
│  📦 Quản Lý Kho Hàng - Mode 1/2                │
│  Mode 1: ... / Mode 2: ...         [Statistics]│
├─────────────────────────────────────────────────┤
│  [Mode 1] [Scan] [Home]              [Start]   │ ← Control Panel
├─────────────────────────────────────────────────┤
│  ┌────┬────┬────┬────┐                         │
│  │ 1  │ 2  │ 3  │ 4  │                         │
│  ├────┼────┼────┼────┤                         │
│  │ 5  │ 6  │ 7  │ 8  │  ← 4×4 Product Grid    │
│  ├────┼────┼────┼────┤                         │
│  │ 9  │ 10 │ 11 │ 12 │                         │
│  ├────┼────┼────┼────┤                         │
│  │ 13 │ 14 │ 15 │ 16 │                         │
│  └────┴────┴────┴────┘                         │
└─────────────────────────────────────────────────┘
```

### Các Nút Điều Khiển:

1. **Nút MODE (Toggle)**
   - Click để chuyển đổi Mode 1 ↔ Mode 2
   - Màu tím (Mode 1), Màu hồng (Mode 2)
   - Disabled khi robot đang chạy

2. **Nút SCAN**
   - Chỉ hoạt động ở Mode 2
   - Disabled ở Mode 1 hoặc khi robot đang chạy
   - Gửi lệnh scan toàn bộ kệ

3. **Nút HOME**
   - Đưa robot về vị trí home
   - Disabled khi robot đang chạy

4. **Nút START/STOP**
   - START: Bắt đầu quá trình gắp
   - STOP: Dừng khẩn cấp
   - Tự động chuyển đổi giữa START và STOP

## Thay Đổi Backend

### Files Mới/Cập Nhật:

1. **`python_backend/app.py`** (UPDATED)
   - Thêm API endpoints mới:
     - `POST /api/robot/start` - Khởi động robot (Mode 1/2)
     - `POST /api/robot/stop` - Dừng robot
     - `POST /api/robot/home` - Home robot
     - `POST /api/robot/scan` - Trigger scan Mode 2
     - `POST /api/robot/mode` - Set mode

2. **`python_backend/data/inventory_scan.json`** (CREATED)
   - Lưu kết quả scan của Mode 2
   - Format: `{time, scan: {P1: {id, name, conf, ...}, ...}}`

### API Endpoints:

#### 1. Start Robot
```http
POST /api/robot/start
Content-Type: application/json

{
  "mode": 1,
  "class_ids": [0, 1, 4, 9, 14]
}

Response:
{
  "status": "success",
  "message": "Mode 1 started with 5 selected items",
  "mode": 1,
  "class_ids": [0, 1, 4, 9, 14]
}
```

#### 2. Stop Robot
```http
POST /api/robot/stop

Response:
{
  "status": "success",
  "message": "Robot stopped"
}
```

#### 3. Home Robot
```http
POST /api/robot/home

Response:
{
  "status": "success",
  "message": "Robot homing"
}
```

#### 4. Scan (Mode 2 only)
```http
POST /api/robot/scan

Response:
{
  "status": "success",
  "message": "Scan initiated - robot will scan all shelf positions",
  "scan_data_path": "..."
}
```

#### 5. Set Mode
```http
POST /api/robot/mode
Content-Type: application/json

{
  "mode": 2
}

Response:
{
  "status": "success",
  "mode": 2,
  "message": "Mode set to 2"
}
```

## Tích Hợp với Arduino

### Giao Thức Serial (Theo `laygiainhatcholinh.py` và `5tr.ino`):

#### Mode 1:
```
Python → Arduino: MODE 1
Python → Arduino: START
Arduino → Python: EVT ARRIVED P1
Python → Arduino: DEC PICK (hoặc DEC SKIP)
... (lặp cho P2-P9)
Arduino → Python: [MODE1] DONE
```

#### Mode 2 - Scan:
```
Python → Arduino: MODE 2
Python → Arduino: START
Arduino → Python: EVT ARRIVED P1
Python saves to JSON + sends: DEC SKIP
... (lặp cho P2-P9)
Arduino → Python: SCAN_DONE
```

#### Mode 2 - Pick:
```
Python → Arduino: LIST P1 P3 P5
Arduino picks từng vị trí trong list
Arduino → Python: [MODE2] DONE
```

## TODO: Tích Hợp Serial Thực Tế

Hiện tại các API endpoints đã được tạo nhưng **chưa kết nối với serial port**.

Để hoàn thiện, cần:

1. **Import module từ `laygiainhatcholinh.py`** vào `app.py`
2. **Chia sẻ serial connection** giữa app.py và laygiainhatcholinh.py
3. **Gọi hàm serial commands** từ các API endpoints:
   - `robot_start()` → Gửi class IDs + START
   - `robot_stop()` → Gửi STOP
   - `robot_home()` → Gửi H0
   - `robot_scan()` → Gửi MODE 2 + START (scan)

## Testing Checklist

- [ ] Mode toggle hoạt động đúng
- [ ] Nút Scan chỉ active ở Mode 2
- [ ] Mode 1: Start với danh sách đã chọn
- [ ] Mode 2: Scan → Chọn → Start
- [ ] Nút Home hoạt động
- [ ] Nút Stop hoạt động
- [ ] UI không bị lỗi hiển thị
- [ ] Integration với Arduino serial commands
- [ ] Test end-to-end flow

## Lưu Ý Quan Trọng

✅ **KHÔNG thay đổi**:
- Trang Chat
- Trang Settings
- Các component khác
- Logic backend hiện tại của LLM/STT

✅ **ĐÃ giữ nguyên**:
- Giao diện lưới 4×4 cho cả Mode 1 và Mode 2
- Logic Arduino (5tr.ino)
- Logic Python điều khiển (laygiainhatcholinh.py)

✅ **ĐÃ thêm mới**:
- 2 nút: Mode Toggle, Scan
- API endpoints cho robot control
- State management cho Mode 1/2
