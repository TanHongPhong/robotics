# YOLO CLASS MAPPING - Inventory 4x4 Grid

## Danh sách đầy đủ 16 classes từ model YOLO

| Cell ID | Class ID | Product Name    | Description           |
|---------|----------|-----------------|-----------------------|
| 1       | 0        | coca lon        | Coca-Cola lon         |
| 2       | 1        | pepsi lon       | Pepsi lon             |
| 3       | 2        | goi qua         | Gói quà               |
| 4       | 3        | van tho         | Vận thơ               |
| 5       | 4        | cay quat        | Cây quất              |
| 6       | 5        | siukay          | Siêu kay              |
| 7       | 6        | xuanay          | Xuân ấy               |
| 8       | 7        | photron         | Phở trộn              |
| 9       | 8        | haohao          | Hảo Hảo               |
| 10      | 9        | omachi          | Omachi                |
| 11      | 10       | coca chai       | Coca-Cola chai        |
| 12      | 11       | nuoc khoang     | Nước khoáng           |
| 13      | 12       | ket sprite      | Két Sprite            |
| 14      | 13       | ket coca        | Két Coca              |
| 15      | 14       | ket pepsi       | Két Pepsi             |
| 16      | 15       | ket fanta       | Két Fanta             |

## Grid Layout (4x4)

```
┌──────────┬──────────┬──────────┬──────────┐
│ Ô 1      │ Ô 2      │ Ô 3      │ Ô 4      │
│ coca lon │ pepsi lon│ goi qua  │ van tho  │
│ [ID: 0]  │ [ID: 1]  │ [ID: 2]  │ [ID: 3]  │
├──────────┼──────────┼──────────┼──────────┤
│ Ô 5      │ Ô 6      │ Ô 7      │ Ô 8      │
│ cay quat │ siukay   │ xuanay   │ photron  │
│ [ID: 4]  │ [ID: 5]  │ [ID: 6]  │ [ID: 7]  │
├──────────┼──────────┼──────────┼──────────┤
│ Ô 9      │ Ô 10     │ Ô 11     │ Ô 12     │
│ haohao   │ omachi   │ coca chai│nuoc khoang
│ [ID: 8]  │ [ID: 9]  │ [ID: 10] │ [ID: 11] │
├──────────┼──────────┼──────────┼──────────┤
│ Ô 13     │ Ô 14     │ Ô 15     │ Ô 16     │
│ket sprite│ ket coca │ ket pepsi│ ket fanta│
│ [ID: 12] │ [ID: 13] │ [ID: 14] │ [ID: 15] │
└──────────┴──────────┴──────────┴──────────┘
```

## Luồng hoạt động

1. **User chọn ô** (ví dụ: Ô 4, Ô 8, Ô 12)
   - Class IDs được chọn: `[3, 7, 11]` 
   - Tương ứng: `van tho`, `photron`, `nuoc khoang`

2. **Bấm START**
   - Frontend gửi: `{ command: "start", class_ids: [3, 7, 11] }`
   - Arduino API (port 5001) → Serial (COM4)
   - Gửi đến Arduino:
     ```
     3 7 11
     MODE 1
     START
     ```

3. **main.py nhận lệnh**
   - Lưu `selected_class_ids = {3, 7, 11}`
   - Khi robot scan đến từng ô:
     - Nếu detect được class trong set → `DEC PICK`
     - Nếu không → `DEC SKIP`

## Files liên quan

- **Backend inventory**: `python_backend/data/inventory.json`
- **Frontend fallback**: `frontend/src/context/InventoryContext.jsx`
- **Serial bridge**: `python_backend/serial_bridge.py`
- **Arduino API**: `python_backend/arduino_api.py` (port 5001)
- **Main control**: `python_backend/main.py` (serial listener)

## Commands

### Python Backend
```bash
# Terminal 1: Main YOLO + Serial listener
cd python_backend
python main.py

# Terminal 2: Arduino API server
cd python_backend
python arduino_api.py
```

### Frontend
```bash
cd frontend
npm run dev
```

## Testing

1. Mở `http://localhost:5173`
2. Chọn một vài ô (ví dụ: ô 3, 7, 11)
3. Check console → `Selected class IDs: [2, 6, 10]`
4. Bấm **HOME** → Arduino nhận `H0`
5. Bấm **START** → Arduino nhận class_ids + MODE 1 + START
6. Robot scan và pick theo class_ids đã chọn
