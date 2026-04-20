# Windows Remote Share + Control

Simple Python remote share for Windows with:
- Screen streaming
- Mouse + keyboard remote control
- Microphone audio streaming
- Feature toggle system via `--control`

This project has:
- `screen_sender.py` -> run on the PC being shared
- `screen_receiver.py` -> run on the PC that watches/controls

## 1) Install

Run on both PCs:

```bash
pip install -r requirements.txt
```

## 2) Features

- **Screen**: live video stream from sender monitor
- **Mouse**: move/click/scroll remote pointer
- **Keyboard**: send key presses to sender PC
- **Mic**: stream sender microphone audio to receiver
- **Token**: basic shared access token check
- **Precision pointer mapping**: DPI-aware sender cursor placement

## 3) `--control` Feature Selector

Both scripts use `--control` with comma-separated values:

- `screen`
- `mouse`
- `keyboard`
- `mic`

Example:

```text
screen,mouse,keyboard,mic
```

Important:
- A feature becomes active only if **both sender and receiver** include it in `--control`.

## 4) Full Example (All Features)

Receiver (viewer/controller):

```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control screen,mouse,keyboard,mic
```

Sender (shared PC):

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard,mic
```

`--token` must match on both sides.

## 5) Practical Mode Examples

### A) Full remote desktop (video + mouse + keyboard + mic)

Receiver:
```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control screen,mouse,keyboard,mic
```

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard,mic
```

### B) No audio (video + controls only)

Receiver:
```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control screen,mouse,keyboard
```

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard
```

### C) View only

Receiver:
```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control screen
```

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen
```

### D) Screen + mic only (no remote input)

Receiver:
```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control screen,mic
```

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mic
```

### E) Input only (mouse + keyboard, no screen/mic)

Receiver:
```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control mouse,keyboard
```

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control mouse,keyboard
```

## 6) Video Quality / Performance Examples

### Low bandwidth internet

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard --fps 8 --quality 45 --scale 0.6
```

### Balanced default

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard --fps 12 --quality 65 --scale 1.0
```

### Better LAN quality

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard --fps 20 --quality 80 --scale 1.0
```

## 7) Audio Settings Examples

### Default audio

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mic --audio-rate 48000 --audio-channels 1
```

### 44.1 kHz audio

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mic --audio-rate 44100 --audio-channels 1
```

### Stereo audio

Sender:
```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mic --audio-rate 48000 --audio-channels 2
```

## 8) All CLI Flags

### `screen_sender.py`

- `--host` (required): receiver IP/hostname
- `--port` (default `9999`): receiver port
- `--control` (default `screen,mouse,keyboard`): features to share
- `--token` (default empty): shared auth token
- `--fps` (default `12.0`): target video FPS
- `--quality` (default `65`): JPEG quality (1-100)
- `--monitor` (default `1`): monitor index from `mss.monitors`
- `--scale` (default `1.0`): resize factor before sending
- `--audio-rate` (default `48000`): mic sample rate
- `--audio-channels` (default `1`): mic channels

### `screen_receiver.py`

- `--host` (default `0.0.0.0`): bind address
- `--port` (default `9999`): listening port
- `--control` (default `screen,mouse,keyboard,mic`): features to use
- `--token` (default empty): shared auth token

## 9) Stop / Notes / Troubleshooting

- Press `q` in receiver window to stop.
- Keyboard control works only when receiver video window is focused.
- For best pointer precision, keep sender display scaling stable during session.
- If connection fails over internet, use Tailscale or correct port forwarding.
- If audio fails, try `--audio-rate 44100`.
