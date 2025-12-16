import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import serial
from serial.tools import list_ports

CFG_PATH = Path("robot_config.json")

# ====== Default data (stored on PC) ======
PX_BASE = [120,240,360,360,240,120,120,240,360]
PY_BASE = [0,0,0,200,200,200,400,400,400]

@dataclass
class RobotConfig:
    port: str = ""          # COMx (Windows) - you can leave empty for auto-detect
    baud: int = 115200
    deltaX: float = 0.0
    deltaY: float = 0.0

def load_cfg() -> RobotConfig:
    if CFG_PATH.exists():
        data = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        return RobotConfig(**data)
    cfg = RobotConfig()
    save_cfg(cfg)
    return cfg

def save_cfg(cfg: RobotConfig) -> None:
    CFG_PATH.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")

def auto_find_port() -> str:
    ports = list(list_ports.comports())
    # ưu tiên cổng có "Arduino" trong mô tả nếu có
    for p in ports:
        desc = (p.description or "").lower()
        if "arduino" in desc or "ch340" in desc or "usb serial" in desc:
            return p.device
    if ports:
        return ports[0].device
    raise RuntimeError("Không tìm thấy cổng COM. Hãy cắm Arduino và thử lại.")

class ArduinoRobot:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 2.0):
        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout)
        time.sleep(1.5)  # Arduino reset khi mở serial

        # flush
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self):
        self.ser.close()

    def _readline(self) -> str:
        line = self.ser.readline().decode(errors="ignore").strip()
        return line

    def send_wait_ok(self, cmd: str, timeout_s: float = 60.0) -> str:
        self.ser.write((cmd.strip() + "\n").encode())
        self.ser.flush()

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            line = self._readline()
            if not line:
                continue
            # print debug from Arduino
            print(f"[ARD] {line}")
            if line.startswith("OK"):
                return line
            if line.startswith("ERR"):
                raise RuntimeError(line)
        raise TimeoutError(f"Timeout waiting response for: {cmd}")

    def home(self):
        return self.send_wait_ok("H0", timeout_s=120)
    
    def delay_s(self, sec: float):
        return self.send_wait_ok(f"D {sec:.3f}", timeout_s=max(5.0, sec + 5.0))


    def move_xy(self, x_mm: float, y_mm: float):
        return self.send_wait_ok(f"M {x_mm:.3f} {y_mm:.3f}", timeout_s=120)

    def pick_xy(self, x_mm: float, y_mm: float):
        return self.send_wait_ok(f"P {x_mm:.3f} {y_mm:.3f}", timeout_s=240)

def point_xy(n: int, cfg: RobotConfig) -> tuple[float, float]:
    # n: 1..9
    x = PX_BASE[n-1] + cfg.deltaX
    y = PY_BASE[n-1] + cfg.deltaY
    return x, y

def repl():
    cfg = load_cfg()
    if not cfg.port:
        cfg.port = auto_find_port()
        save_cfg(cfg)

    print("=== Robot PC Controller ===")
    print(f"Config: {CFG_PATH.resolve()}")
    print(f"Serial: {cfg.port} @ {cfg.baud}")
    print("Commands:")
    print("  home")
    print("  offset dx dy       (mm)  -> lưu vào robot_config.json")
    print("  pick N             (1..9)")
    print("  pickxy x y         (mm)")
    print("  movexy x y         (mm)")
    print("  show               -> xem delta hiện tại")
    print("  quit")

    bot = ArduinoRobot(cfg.port, cfg.baud)

    try:
        while True:
            s = input(">> ").strip()
            if not s:
                continue
            parts = s.split()

            if parts[0] in ("quit", "exit"):
                break

            if parts[0] == "show":
                print(f"deltaX={cfg.deltaX}, deltaY={cfg.deltaY}")
                continue

            if parts[0] == "offset" and len(parts) == 3:
                cfg.deltaX = float(parts[1])
                cfg.deltaY = float(parts[2])
                save_cfg(cfg)
                print("Saved offset.")
                continue

            if parts[0] == "home":
                bot.home()
                continue

            if parts[0] == "delay" and len(parts) == 2:
                sec = float(parts[1])
                bot.delay_s(sec)
                continue

            if parts[0] == "pick" and len(parts) == 2:
                n = int(parts[1])
                if not (1 <= n <= 9):
                    print("N must be 1..9")
                    continue
                x, y = point_xy(n, cfg)
                print(f"Pick P{n}: x={x:.3f}, y={y:.3f}")
                bot.pick_xy(x, y)
                continue

            if parts[0] == "pickxy" and len(parts) == 3:
                x = float(parts[1]); y = float(parts[2])
                bot.pick_xy(x, y)
                continue

            if parts[0] == "movexy" and len(parts) == 3:
                x = float(parts[1]); y = float(parts[2])
                bot.move_xy(x, y)
                continue

            print("Unknown command.")
    finally:
        bot.close()

if __name__ == "__main__":
    repl()
