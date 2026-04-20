import argparse
import ctypes
import json
import socket
import struct
import threading
import time

import cv2
import mss
import numpy as np
import pyautogui

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture and stream screen frames to a receiver."
    )
    parser.add_argument(
        "--host",
        required=True,
        help="Receiver IP address (for example: 192.168.1.10)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9999,
        help="Receiver port (default: 9999)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=12.0,
        help="Target frame rate (default: 12)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=65,
        help="JPEG quality 1-100 (default: 65)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="Monitor number from mss.monitors (default: 1)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Resize factor before sending, e.g. 0.75 (default: 1.0)",
    )
    parser.add_argument(
        "--allow-control",
        action="store_true",
        help="Allow receiver to control mouse/keyboard on this PC",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Optional shared token for basic access control",
    )
    return parser.parse_args()


def send_packet(sock: socket.socket, packet_type: bytes, payload: bytes) -> None:
    sock.sendall(packet_type + struct.pack("!I", len(payload)))
    sock.sendall(payload)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed while receiving data.")
        buf.extend(chunk)
    return bytes(buf)


def recv_packet(sock: socket.socket) -> tuple[bytes, bytes]:
    header = recv_exact(sock, 5)
    packet_type = header[:1]
    (size,) = struct.unpack("!I", header[1:])
    payload = recv_exact(sock, size)
    return packet_type, payload


def clamp_to_monitor(monitor: dict, x: int, y: int) -> tuple[int, int]:
    cx = max(0, min(int(monitor["width"]) - 1, int(x)))
    cy = max(0, min(int(monitor["height"]) - 1, int(y)))
    return cx, cy


def set_cursor_position(user32: ctypes.WinDLL, monitor: dict, x: int, y: int) -> None:
    cx, cy = clamp_to_monitor(monitor, x, y)
    user32.SetCursorPos(int(monitor["left"]) + cx, int(monitor["top"]) + cy)


def mouse_button_flag(button: str, action: str) -> int | None:
    button = button.lower().strip()
    action = action.lower().strip()
    if button == "left":
        return MOUSEEVENTF_LEFTDOWN if action == "down" else MOUSEEVENTF_LEFTUP
    if button == "right":
        return MOUSEEVENTF_RIGHTDOWN if action == "down" else MOUSEEVENTF_RIGHTUP
    if button == "middle":
        return MOUSEEVENTF_MIDDLEDOWN if action == "down" else MOUSEEVENTF_MIDDLEUP
    return None


def apply_control_event(event: dict, monitor: dict) -> None:
    etype = event.get("type")
    user32 = ctypes.windll.user32
    if etype == "mouse_move":
        x = int(event.get("x", 0))
        y = int(event.get("y", 0))
        set_cursor_position(user32, monitor, x, y)
    elif etype == "mouse_click":
        x = int(event.get("x", 0))
        y = int(event.get("y", 0))
        button = event.get("button", "left")
        action = event.get("action", "down")
        set_cursor_position(user32, monitor, x, y)
        flag = mouse_button_flag(button, action)
        if flag is not None:
            user32.mouse_event(flag, 0, 0, 0, 0)
    elif etype == "mouse_scroll":
        amount = int(event.get("amount", 0))
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, amount, 0)
    elif etype == "key":
        key = str(event.get("key", "")).lower().strip()
        action = event.get("action", "press")
        if key:
            if action == "down":
                pyautogui.keyDown(key)
            elif action == "up":
                pyautogui.keyUp(key)
            else:
                pyautogui.press(key)
    elif etype == "type_text":
        text = str(event.get("text", ""))
        if text:
            pyautogui.write(text)


def control_listener(
    sock: socket.socket,
    monitor: dict,
    allow_control: bool,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        try:
            packet_type, payload = recv_packet(sock)
        except (ConnectionError, OSError):
            stop_event.set()
            return

        if packet_type != b"C":
            continue
        if not allow_control:
            continue

        try:
            event = json.loads(payload.decode("utf-8"))
            apply_control_event(event, monitor)
        except Exception:
            # Ignore malformed/unhandled control packets to keep streaming stable.
            continue


def main() -> None:
    args = parse_args()
    jpeg_quality = max(1, min(100, args.quality))
    frame_interval = 1.0 / max(1.0, args.fps)
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
    ctypes.windll.user32.SetProcessDPIAware()

    print(f"Connecting to receiver {args.host}:{args.port} ...")
    sock = socket.create_connection((args.host, args.port), timeout=10)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print("Connected. Streaming started. Press Ctrl+C to stop.")

    with mss.mss() as sct:
        if args.monitor < 1 or args.monitor >= len(sct.monitors):
            raise ValueError(
                f"Invalid monitor {args.monitor}. Available: 1 to {len(sct.monitors) - 1}"
            )
        monitor = sct.monitors[args.monitor]
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        stop_event = threading.Event()

        hello = {
            "monitor_width": int(monitor["width"]),
            "monitor_height": int(monitor["height"]),
            "allow_control": bool(args.allow_control),
            "token": args.token,
        }
        send_packet(sock, b"I", json.dumps(hello).encode("utf-8"))

        listener_thread = threading.Thread(
            target=control_listener,
            args=(sock, monitor, args.allow_control, stop_event),
            daemon=True,
        )
        listener_thread.start()

        try:
            while not stop_event.is_set():
                start = time.perf_counter()

                raw = sct.grab(monitor)
                frame = np.array(raw)[:, :, :3]  # BGRA -> BGR

                if args.scale != 1.0:
                    frame = cv2.resize(
                        frame,
                        dsize=None,
                        fx=args.scale,
                        fy=args.scale,
                        interpolation=cv2.INTER_AREA,
                    )

                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    continue

                send_packet(sock, b"F", encoded.tobytes())

                elapsed = time.perf_counter() - start
                sleep_for = frame_interval - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        except (KeyboardInterrupt, ConnectionError, OSError):
            print("\nStopping stream...")
        finally:
            stop_event.set()
            sock.close()
            print("Connection closed.")


if __name__ == "__main__":
    main()
