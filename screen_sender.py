import argparse
import ctypes
import json
import queue
import socket
import struct
import threading
import time

import cv2
import mss
import numpy as np
import pyautogui
import sounddevice as sd

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
        "--control",
        default="screen,mouse,keyboard",
        help="Comma-separated features to share: screen,mouse,keyboard,mic,system_audio",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Optional shared token for basic access control",
    )
    parser.add_argument(
        "--audio-rate",
        type=int,
        default=48000,
        help="Audio sample rate (default: 48000)",
    )
    parser.add_argument(
        "--audio-channels",
        type=int,
        default=1,
        help="Audio channels (default: 1)",
    )
    parser.add_argument(
        "--system-audio-device",
        type=int,
        default=None,
        help="Optional output device index for system audio loopback",
    )
    return parser.parse_args()


def parse_feature_flags(raw: str) -> set[str]:
    allowed = {"screen", "mouse", "keyboard", "mic", "system_audio"}
    selected = {item.strip().lower() for item in raw.split(",") if item.strip()}
    unknown = selected - allowed
    if unknown:
        bad = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown control feature(s): {bad}")
    if not selected:
        raise ValueError("At least one control feature must be selected.")
    return selected


def pick_system_loopback_input_device(explicit_device: int | None) -> int:
    if explicit_device is not None:
        return int(explicit_device)

    devices = sd.query_devices()
    default_output = sd.default.device[1]
    if default_output is not None and int(default_output) >= 0:
        output_name = str(devices[int(default_output)]["name"]).lower()
        for idx, dev in enumerate(devices):
            name = str(dev["name"]).lower()
            if "loopback" in name and output_name in name:
                return idx

    for idx, dev in enumerate(devices):
        if "loopback" in str(dev["name"]).lower():
            return idx

    raise RuntimeError(
        "No WASAPI loopback input device found. "
        "Try updating sounddevice, or pass --system-audio-device <index> for a valid loopback device."
    )


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


def send_packet_locked(
    sock: socket.socket, lock: threading.Lock, packet_type: bytes, payload: bytes
) -> None:
    with lock:
        send_packet(sock, packet_type, payload)


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
    allowed_input_features: set[str],
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

        try:
            event = json.loads(payload.decode("utf-8"))
            etype = str(event.get("type", ""))
            if etype.startswith("mouse_") and "mouse" not in allowed_input_features:
                continue
            if (etype == "key" or etype == "type_text") and "keyboard" not in allowed_input_features:
                continue
            apply_control_event(event, monitor)
        except Exception:
            # Ignore malformed/unhandled control packets to keep streaming stable.
            continue


def audio_streamer(
    sock: socket.socket,
    send_lock: threading.Lock,
    stop_event: threading.Event,
    sample_rate: int,
    channels: int,
    source: str,
    system_audio_device: int | None,
) -> None:
    blocksize = 1024
    max_queue_chunks = 60
    bytes_per_sample = 2
    frame_bytes = blocksize * channels * bytes_per_sample

    def queue_push(q: queue.Queue[bytes], payload: bytes) -> None:
        try:
            q.put_nowait(payload)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass

    def build_stream_kwargs(src: str, on_audio) -> dict:
        kwargs = {
            "samplerate": sample_rate,
            "channels": channels,
            "dtype": "int16",
            "blocksize": blocksize,
            "callback": on_audio,
        }
        if src == "system_audio":
            kwargs["device"] = pick_system_loopback_input_device(system_audio_device)
            try:
                kwargs["extra_settings"] = sd.WasapiSettings(loopback=True)
            except TypeError:
                pass
        return kwargs

    if source in {"mic", "system_audio"}:
        single_queue: queue.Queue[bytes] = queue.Queue(maxsize=max_queue_chunks)

        def on_audio(indata, frames, time_info, status) -> None:
            if stop_event.is_set() or status:
                return
            queue_push(single_queue, bytes(indata))

        try:
            with sd.RawInputStream(**build_stream_kwargs(source, on_audio)):
                while not stop_event.is_set():
                    try:
                        chunk = single_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    send_packet_locked(sock, send_lock, b"A", chunk)
            return
        except Exception as exc:
            print(f"Audio stopped: {exc}")
            stop_event.set()
            return

    if source == "mixed":
        mic_queue: queue.Queue[bytes] = queue.Queue(maxsize=max_queue_chunks)
        sys_queue: queue.Queue[bytes] = queue.Queue(maxsize=max_queue_chunks)

        def on_mic(indata, frames, time_info, status) -> None:
            if stop_event.is_set() or status:
                return
            queue_push(mic_queue, bytes(indata))

        def on_system(indata, frames, time_info, status) -> None:
            if stop_event.is_set() or status:
                return
            queue_push(sys_queue, bytes(indata))

        latest_mic = bytes(frame_bytes)
        latest_sys = bytes(frame_bytes)
        try:
            with sd.RawInputStream(**build_stream_kwargs("mic", on_mic)), sd.RawInputStream(
                **build_stream_kwargs("system_audio", on_system)
            ):
                while not stop_event.is_set():
                    got = False
                    try:
                        latest_mic = mic_queue.get(timeout=0.03)
                        got = True
                    except queue.Empty:
                        pass
                    try:
                        latest_sys = sys_queue.get_nowait()
                        got = True
                    except queue.Empty:
                        pass
                    if not got:
                        continue

                    mic_arr = np.frombuffer(latest_mic, dtype=np.int16).astype(np.int32)
                    sys_arr = np.frombuffer(latest_sys, dtype=np.int16).astype(np.int32)
                    length = min(len(mic_arr), len(sys_arr))
                    if length == 0:
                        continue
                    mixed = np.clip(mic_arr[:length] + sys_arr[:length], -32768, 32767).astype(
                        np.int16
                    )
                    send_packet_locked(sock, send_lock, b"A", mixed.tobytes())
            return
        except Exception as exc:
            print(f"Audio stopped: {exc}")
            stop_event.set()
            return

    print(f"Audio stopped: Unknown source mode '{source}'")
    stop_event.set()


def main() -> None:
    args = parse_args()
    features = parse_feature_flags(args.control)
    share_screen = "screen" in features
    share_mic = "mic" in features
    share_system_audio = "system_audio" in features
    allow_mouse_control = "mouse" in features
    allow_keyboard_control = "keyboard" in features
    jpeg_quality = max(1, min(100, args.quality))
    frame_interval = 1.0 / max(1.0, args.fps)
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
    ctypes.windll.user32.SetProcessDPIAware()

    print(f"Connecting to receiver {args.host}:{args.port} ...")
    sock = socket.create_connection((args.host, args.port), timeout=10)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print("Connected. Sharing started. Press Ctrl+C to stop.")

    with mss.mss() as sct:
        if args.monitor < 1 or args.monitor >= len(sct.monitors):
            raise ValueError(
                f"Invalid monitor {args.monitor}. Available: 1 to {len(sct.monitors) - 1}"
            )
        monitor = sct.monitors[args.monitor]
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        stop_event = threading.Event()
        send_lock = threading.Lock()

        hello = {
            "monitor_width": int(monitor["width"]),
            "monitor_height": int(monitor["height"]),
            "enabled_features": sorted(features),
            "token": args.token,
            "audio_enabled": bool(share_mic or share_system_audio),
            "audio_source": (
                "mixed"
                if (share_mic and share_system_audio)
                else ("system_audio" if share_system_audio else ("mic" if share_mic else "none"))
            ),
            "audio_rate": int(args.audio_rate),
            "audio_channels": int(args.audio_channels),
        }
        send_packet_locked(sock, send_lock, b"I", json.dumps(hello).encode("utf-8"))

        listener_thread = threading.Thread(
            target=control_listener,
            args=(
                sock,
                monitor,
                {
                    name
                    for name, enabled in (
                        ("mouse", allow_mouse_control),
                        ("keyboard", allow_keyboard_control),
                    )
                    if enabled
                },
                stop_event,
            ),
            daemon=True,
        )
        listener_thread.start()

        audio_thread = None
        if share_mic or share_system_audio:
            audio_thread = threading.Thread(
                target=audio_streamer,
                args=(
                    sock,
                    send_lock,
                    stop_event,
                    int(args.audio_rate),
                    int(args.audio_channels),
                    (
                        "mixed"
                        if (share_mic and share_system_audio)
                        else ("system_audio" if share_system_audio else "mic")
                    ),
                    args.system_audio_device,
                ),
                daemon=True,
            )
            audio_thread.start()
            print(
                f"Audio streaming enabled "
                f"({'mixed' if (share_mic and share_system_audio) else ('system' if share_system_audio else 'mic')}): "
                f"{int(args.audio_rate)} Hz, {int(args.audio_channels)} channel(s)."
            )

        try:
            while not stop_event.is_set():
                start = time.perf_counter()
                if not share_screen:
                    time.sleep(0.05)
                    continue

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

                send_packet_locked(sock, send_lock, b"F", encoded.tobytes())

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
