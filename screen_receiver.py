import argparse
import json
import socket
import struct

import cv2
import numpy as np


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
        action="store_true",
        help="Send mouse/keyboard events to sender (requires sender --allow-control)",
    )
    return parser.parse_args()


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
    remote_allows_control = bool(hello.get("allow_control", False))
    remote_token = str(hello.get("token", ""))

    if args.token != remote_token:
        conn.close()
        server.close()
        raise RuntimeError("Token mismatch. Set same --token on sender and receiver.")

    control_enabled = bool(args.control and remote_allows_control)
    print(f"Remote monitor: {remote_width}x{remote_height}")
    if args.control and not remote_allows_control:
        print("Receiver requested control but sender did not enable --allow-control.")
    print(f"Control active: {'yes' if control_enabled else 'no'}")
    print("Focus video window for keyboard control.")

    window_name = "Remote Screen"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    last_frame_size = [remote_width, remote_height]

    def to_remote_coords(x: int, y: int) -> tuple[int, int] | None:
        frame_w = max(1, int(last_frame_size[0]))
        frame_h = max(1, int(last_frame_size[1]))
        try:
            _, _, win_w, win_h = cv2.getWindowImageRect(window_name)
        except cv2.error:
            win_w, win_h = frame_w, frame_h
        if win_w <= 0 or win_h <= 0:
            win_w, win_h = frame_w, frame_h

        # OpenCV keeps aspect ratio in many window states; account for padding
        # (letterbox/pillarbox) so pointer mapping stays accurate.
        scale = min(win_w / frame_w, win_h / frame_h)
        draw_w = max(1.0, frame_w * scale)
        draw_h = max(1.0, frame_h * scale)
        offset_x = (win_w - draw_w) / 2.0
        offset_y = (win_h - draw_h) / 2.0

        if x < offset_x or y < offset_y or x > (offset_x + draw_w) or y > (offset_y + draw_h):
            return None

        frame_x = (x - offset_x) / scale
        frame_y = (y - offset_y) / scale
        rx = int(max(0, min(remote_width - 1, (frame_x / frame_w) * remote_width)))
        ry = int(max(0, min(remote_height - 1, (frame_y / frame_h) * remote_height)))
        return rx, ry

    def send_control(event: dict) -> None:
        if not control_enabled:
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

    try:
        while True:
            packet_type, payload = recv_packet(conn)
            if packet_type != b"F":
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
            if control_enabled and key != 255:
                if key in key_map:
                    send_control({"type": "key", "action": "press", "key": key_map[key]})
                elif 32 <= key <= 126:
                    # Printable ASCII keys.
                    send_control({"type": "type_text", "text": chr(key)})
    except (ConnectionError, OSError) as exc:
        print(f"Connection ended: {exc}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        server.close()
        cv2.destroyAllWindows()
        print("Receiver stopped.")


if __name__ == "__main__":
    main()
