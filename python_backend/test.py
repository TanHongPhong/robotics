import time
import argparse
import cv2
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str,
                        default=r"C:\AI_Robotics\runs\robotics_detector\weights\best.pt")
    parser.add_argument("--cam", type=int, default=0)

    # Bạn muốn tăng chất lượng → giảm FPS
    parser.add_argument("--fps", type=int, default=30)       # 1080p chuẩn
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)

    # YOLO configs
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.5)   # bạn yêu cầu
    parser.add_argument("--iou", type=float, default=0.0)    # overlap = 0
    args = parser.parse_args()

    # Load YOLO
    model = YOLO(args.weights)

    # Open camera
    cap = cv2.VideoCapture(args.cam, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # ổn định chất lượng
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    # Kiểm tra thông số thực tế camera đang chạy
    print("Camera actual:", 
          cap.get(cv2.CAP_PROP_FRAME_WIDTH), 
          cap.get(cv2.CAP_PROP_FRAME_HEIGHT), 
          cap.get(cv2.CAP_PROP_FPS))

    fps_smooth = 0
    prev_t = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # ===============================
        # 🔄 XOAY KHUNG HÌNH 90° CCW
        # ===============================


        # ===============================
        # 🔍 YOLO DETECT TRÊN KHUNG XOAY
        # ===============================
        results = model.predict(
            frame,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            verbose=False
        )

        annotated = results[0].plot()

        # ===============================
        # 📌 FPS đo thực tế
        # ===============================
        now = time.time()
        fps = 1.0 / (now - prev_t)
        prev_t = now
        fps_smooth = 0.9 * fps_smooth + 0.1 * fps if fps_smooth else fps

        cv2.putText(annotated, f"FPS: {fps_smooth:.1f} | conf={args.conf}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)

        cv2.imshow("YOLO Detection (Rotated 90° CCW)", annotated)

        if cv2.waitKey(1) & 0xFF in [ord('q'), 27]:
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
