"""
YOLO OpenCV Stream - Independent YOLO Detection Window
Chạy stream YOLO độc lập với OpenCV (không liên quan đến React frontend)
"""
import time
import argparse
import cv2
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description="YOLO OpenCV Stream - Independent Detection Window")
    parser.add_argument("--weights", type=str,
                        default=r"C:\AI_Robotics\runs\robotics_detector\weights\best.pt",
                        help="Path to YOLO weights file")
    parser.add_argument("--cam", type=int, default=0,
                        help="Camera index (0 for default camera)")

    # Camera quality settings
    parser.add_argument("--fps", type=int, default=30,
                        help="Target FPS (1080p standard)")
    parser.add_argument("--width", type=int, default=1920,
                        help="Camera width resolution")
    parser.add_argument("--height", type=int, default=1080,
                        help="Camera height resolution")

    # YOLO configs
    parser.add_argument("--imgsz", type=int, default=640,
                        help="YOLO inference image size")
    parser.add_argument("--conf", type=float, default=0.5,
                        help="Confidence threshold for detection")
    parser.add_argument("--iou", type=float, default=0.0,
                        help="IoU threshold for NMS (0 = no overlap)")
    
    # Rotation option
    parser.add_argument("--rotate", action="store_true",
                        help="Rotate frame 90° counter-clockwise")
    
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 YOLO OpenCV Stream - Starting...")
    print("=" * 60)
    print(f"📦 Weights: {args.weights}")
    print(f"📷 Camera: {args.cam}")
    print(f"🎯 Confidence: {args.conf}")
    print(f"🔄 Rotation: {'Enabled (90° CCW)' if args.rotate else 'Disabled'}")
    print("=" * 60)

    # Load YOLO model
    print("⏳ Loading YOLO model...")
    try:
        model = YOLO(args.weights)
        print("✅ YOLO model loaded successfully!")
    except Exception as e:
        print(f"❌ Error loading YOLO model: {e}")
        return

    # Open camera
    print("⏳ Opening camera...")
    cap = cv2.VideoCapture(args.cam, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print(f"❌ Cannot open camera {args.cam}")
        return
    
    # Set camera properties
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    # Check actual camera settings
    actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    
    print("✅ Camera opened successfully!")
    print(f"📐 Actual resolution: {actual_width}x{actual_height} @ {actual_fps} FPS")
    print("=" * 60)
    print("💡 Press 'q' or 'ESC' to quit")
    print("=" * 60)

    fps_smooth = 0
    prev_t = time.time()
    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("⚠️ Cannot read frame from camera")
                break

            frame_count += 1

            # ===============================
            # 🔄 ROTATE FRAME IF ENABLED
            # ===============================
            if args.rotate:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # ===============================
            # 🔍 YOLO DETECTION
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
            # 📌 FPS CALCULATION
            # ===============================
            now = time.time()
            fps = 1.0 / (now - prev_t)
            prev_t = now
            fps_smooth = 0.9 * fps_smooth + 0.1 * fps if fps_smooth else fps

            # ===============================
            # 📊 DISPLAY INFO ON FRAME
            # ===============================
            # FPS and config info
            cv2.putText(annotated, f"FPS: {fps_smooth:.1f} | conf={args.conf}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Detection count
            num_detections = len(results[0].boxes)
            cv2.putText(annotated, f"Detections: {num_detections}",
                        (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # Show frame
            cv2.imshow("YOLO Detection Stream (OpenCV)", annotated)

            # Check for quit key
            key = cv2.waitKey(1) & 0xFF
            if key in [ord('q'), 27]:  # 'q' or ESC
                print(f"\n🛑 Stopping stream... (Processed {frame_count} frames)")
                break

    except KeyboardInterrupt:
        print(f"\n⚠️ Interrupted by user (Processed {frame_count} frames)")
    except Exception as e:
        print(f"\n❌ Error during streaming: {e}")
    finally:
        # Cleanup
        print("🧹 Cleaning up...")
        cap.release()
        cv2.destroyAllWindows()
        print("✅ Stream stopped successfully!")
        print("=" * 60)


if __name__ == "__main__":
    main()
