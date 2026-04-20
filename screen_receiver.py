import argparse
import json
import queue
import socket
import struct
import threading

import cv2
import numpy as np
import sounddevice as sd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Receive and display a remote screen stream."
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9999,
        help="Port to listen on (default: 9999)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Optional shared token (must match sender token)",
    )
    parser.add_argument(
        "--control",
        default="screen,mouse,keyboard,mic",
        help="Comma-separated features to use: screen,mouse,keyboard,mic",
    )
    return parser.parse_args()


def parse_feature_flags(raw: str) -> set[str]:
    allowed = {"screen", "mouse", "keyboard", "mic"}
    selected = {item.strip().lower() for item in raw.split(",") if item.strip()}
    unknown = selected - allowed
    if unknown:
        bad = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown control feature(s): {bad}")
    if not selected:
        raise ValueError("At least one control feature must be selected.")
    return selected


def recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed while receiving data.")
        buf.extend(chunk)
    return bytes(buf)


def send_packet(sock: socket.socket, packet_type: bytes, payload: bytes) -> None:
    sock.sendall(packet_type + struct.pack("!I", len(payload)))
    sock.sendall(payload)


def recv_packet(sock: socket.socket) -> tuple[bytes, bytes]:
    header = recv_exact(sock, 5)
    packet_type = header[:1]
    (size,) = struct.unpack("!I", header[1:])
    payload = recv_exact(sock, size)
    return packet_type, payload


def main() -> None:
    args = parse_args()
    local_features = parse_feature_flags(args.control)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)

    print(f"Waiting for sender on {args.host}:{args.port} ...")
    conn, addr = server.accept()
    print(f"Connected by {addr[0]}:{addr[1]}")
    print("Press 'q' in the video window to quit.")

    packet_type, payload = recv_packet(conn)
    if packet_type != b"I":
        conn.close()
        server.close()
        raise RuntimeError("Invalid handshake from sender.")

    hello = json.loads(payload.decode("utf-8"))
    remote_width = int(hello.get("monitor_width", 1920))
    remote_height = int(hello.get("monitor_height", 1080))
    remote_features = set(hello.get("enabled_features", []))
    remote_token = str(hello.get("token", ""))
    remote_audio_enabled = bool(hello.get("audio_enabled", False))
    remote_audio_rate = int(hello.get("audio_rate", 48000))
    remote_audio_channels = int(hello.get("audio_channels", 1))

    if args.token != remote_token:
        conn.close()
        server.close()
        raise RuntimeError("Token mismatch. Set same --token on sender and receiver.")

    use_mouse = "mouse" in local_features and "mouse" in remote_features
    use_keyboard = "keyboard" in local_features and "keyboard" in remote_features
    use_screen = "screen" in local_features and "screen" in remote_features
    use_mic = "mic" in local_features and "mic" in remote_features and remote_audio_enabled
    control_enabled = bool(use_mouse or use_keyboard)
    print(f"Remote monitor: {remote_width}x{remote_height}")
    print(f"Sender features: {', '.join(sorted(remote_features))}")
    print(f"Control active: {'yes' if control_enabled else 'no'}")
    audio_play_enabled = bool(use_mic)
    print(f"Audio active: {'yes' if audio_play_enabled else 'no'}")
    print("Focus video window for keyboard control.")

    window_name = "Remote Screen"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    last_frame_size = [remote_width, remote_height]

    def to_remote_coords(x: int, y: int) -> tuple[int, int] | None:
        frame_w = max(1, int(last_frame_size[0]))
        frame_h = max(1, int(last_frame_size[1]))
        if x < 0 or y < 0 or x >= frame_w or y >= frame_h:
            return None
        rx = int(max(0, min(remote_width - 1, (x / frame_w) * remote_width)))
        ry = int(max(0, min(remote_height - 1, (y / frame_h) * remote_height)))
        return rx, ry

    def send_control(event: dict) -> None:
        if not control_enabled:
            return
        etype = str(event.get("type", ""))
        if etype.startswith("mouse_") and not use_mouse:
            return
        if (etype == "key" or etype == "type_text") and not use_keyboard:
            return
        send_packet(conn, b"C", json.dumps(event).encode("utf-8"))

    def on_mouse(event: int, x: int, y: int, flags: int, param: object) -> None:
        coords = to_remote_coords(x, y)
        if coords is None:
            return
        rx, ry = coords

        if event == cv2.EVENT_MOUSEMOVE:
            send_control({"type": "mouse_move", "x": rx, "y": ry})
        elif event == cv2.EVENT_LBUTTONDOWN:
            send_control(
                {"type": "mouse_click", "action": "down", "button": "left", "x": rx, "y": ry}
            )
        elif event == cv2.EVENT_LBUTTONUP:
            send_control(
                {"type": "mouse_click", "action": "up", "button": "left", "x": rx, "y": ry}
            )
        elif event == cv2.EVENT_RBUTTONDOWN:
            send_control(
                {
                    "type": "mouse_click",
                    "action": "down",
                    "button": "right",
                    "x": rx,
                    "y": ry,
                }
            )
        elif event == cv2.EVENT_RBUTTONUP:
            send_control(
                {"type": "mouse_click", "action": "up", "button": "right", "x": rx, "y": ry}
            )
        elif event == cv2.EVENT_MBUTTONDOWN:
            send_control(
                {
                    "type": "mouse_click",
                    "action": "down",
                    "button": "middle",
                    "x": rx,
                    "y": ry,
                }
            )
        elif event == cv2.EVENT_MBUTTONUP:
            send_control(
                {
                    "type": "mouse_click",
                    "action": "up",
                    "button": "middle",
                    "x": rx,
                    "y": ry,
                }
            )
        elif event == cv2.EVENT_MOUSEWHEEL:
            amount = 240 if flags > 0 else -240
            send_control({"type": "mouse_scroll", "amount": amount})

    cv2.setMouseCallback(window_name, on_mouse)

    key_map = {
        8: "backspace",
        9: "tab",
        13: "enter",
        27: "esc",
        32: "space",
    }

    stop_audio = threading.Event()
    audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=120)

    def audio_player() -> None:
        try:
            with sd.RawOutputStream(
                samplerate=remote_audio_rate,
                channels=remote_audio_channels,
                dtype="int16",
                blocksize=1024,
            ) as stream:
                while not stop_audio.is_set():
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    stream.write(chunk)
        except Exception as exc:
            print(f"Audio playback stopped: {exc}")
            stop_audio.set()

    audio_thread = None
    if audio_play_enabled:
        audio_thread = threading.Thread(target=audio_player, daemon=True)
        audio_thread.start()
        print(
            f"Audio playback started: {remote_audio_rate} Hz, {remote_audio_channels} channel(s)."
        )

    try:
        while True:
            packet_type, payload = recv_packet(conn)
            if packet_type == b"A":
                if audio_play_enabled and not stop_audio.is_set():
                    try:
                        audio_queue.put_nowait(payload)
                    except queue.Full:
                        # Drop oldest chunk to keep latency low.
                        try:
                            audio_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            audio_queue.put_nowait(payload)
                        except queue.Full:
                            pass
                continue
            if packet_type != b"F":
                continue
            if not use_screen:
                continue

            img_array = np.frombuffer(payload, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if frame is None:
                continue
            last_frame_size[0] = int(frame.shape[1])
            last_frame_size[1] = int(frame.shape[0])

            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if use_keyboard and key != 255:
                if key in key_map:
                    send_control({"type": "key", "action": "press", "key": key_map[key]})
                elif 32 <= key <= 126:
                    # Printable ASCII keys.
                    send_control({"type": "type_text", "text": chr(key)})
    except (ConnectionError, OSError) as exc:
        print(f"Connection ended: {exc}")
    finally:
        stop_audio.set()
        try:
            conn.close()
        except Exception:
            pass
        server.close()
        cv2.destroyAllWindows()
        print("Receiver stopped.")


if __name__ == "__main__":
    main()
