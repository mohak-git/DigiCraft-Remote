# Setup Guide (Windows)

This file explains how to set up the full remote share system from zero.

Project scripts:

- `screen_sender.py` -> run on the PC being shared
- `screen_receiver.py` -> run on the PC that watches/controls

---

## 1) Prerequisites

On both PCs:

- Windows 10/11
- Python 3.9 or newer
- Internet connection
- Same project files (`screen_sender.py`, `screen_receiver.py`, `requirements.txt`)

Check Python:

```bash
python --version
```

---

## 2) Install Dependencies

Open terminal in the project folder on both PCs and run:

```bash
pip install -r requirements.txt
```

Dependencies used:

- `opencv-python` (video display/encoding)
- `mss` (screen capture)
- `numpy` (frame conversion)
- `pyautogui` (keyboard input)
- `sounddevice` (audio capture/playback)

---

## 3) Decide Network Method

To connect from different places (different routers), use one of:

1. **Tailscale (recommended)**
2. **Port forwarding + public IP**

### A) Tailscale (Recommended)

1. Install Tailscale on both PCs.
2. Log in to the same Tailscale account.
3. Copy receiver Tailscale IP (usually `100.x.x.x`).
4. Use that IP in sender command as `<receiver_ip>`.

### B) Port Forwarding

1. On receiver router, forward TCP port `9999` to receiver local PC IP.
2. Find receiver public IP.
3. Use public IP in sender command as `<receiver_ip>`.

---

## 4) Choose Features to Share

Both scripts use:

```text
--control screen,mouse,keyboard,mic,system_audio
```

Available feature names:

- `screen` -> video stream
- `mouse` -> remote mouse control
- `keyboard` -> remote keyboard control
- `mic` -> sender microphone audio
- `system_audio` -> sender speaker/output audio (Windows loopback)

Important:

- A feature is active only if enabled on **both sender and receiver**.

---

## 5) First-Time Full Setup (All Features)

Use a token (password-style string), example: `mysecret`.

### Step 1: Start receiver PC first

```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control screen,mouse,keyboard,mic,system_audio
```

### Step 2: Start sender PC

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard,mic,system_audio --audio-rate 48000 --audio-channels 2
```

Replace `<receiver_ip>` with:

- Tailscale IP (recommended), or
- receiver public IP (if port forwarding is configured)

---

## 6) Common Ready-to-Use Modes

### Full remote desktop

```text
screen,mouse,keyboard,mic,system_audio
```

### No audio

```text
screen,mouse,keyboard
```

### View only

```text
screen
```

### Screen + mic only

```text
screen,mic
```

### Screen + system audio only

```text
screen,system_audio
```

### Screen + mixed audio (mic + system audio)

```text
screen,mic,system_audio
```

### Input only

```text
mouse,keyboard
```

---

## 7) Performance Tuning (Sender Side)

Video quality/speed options:

- `--fps` (default `12.0`)
- `--quality` JPEG quality 1-100 (default `65`)
- `--scale` frame resize factor (default `1.0`)

Examples:

Low bandwidth internet:

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard --fps 8 --quality 45 --scale 0.6
```

Balanced default:

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard --fps 12 --quality 65 --scale 1.0
```

Better LAN quality:

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard --fps 20 --quality 80 --scale 1.0
```

---

## 8) Audio Settings (Sender Side)

Audio options:

- `--audio-rate` (default `48000`)
- `--audio-channels` (default `1`)
- `--system-audio-device` (optional output device index for loopback)

Examples:

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mic --audio-rate 48000 --audio-channels 1
```

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mic --audio-rate 44100 --audio-channels 2
```

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,system_audio --audio-rate 48000 --audio-channels 2
```

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,system_audio --audio-rate 48000 --audio-channels 2 --system-audio-device 5
```

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mic,system_audio --audio-rate 48000 --audio-channels 2
```

List available audio devices:

```bash
python -c "import sounddevice as sd; print(sd.query_devices())"
```

---

## 9) Verify It Works

After both scripts are running:

- Receiver window should show sender screen (if `screen` enabled).
- Moving/clicking mouse on receiver should move sender pointer (if `mouse` enabled).
- Typing in receiver window should type on sender (if `keyboard` enabled).
- Receiver should hear sender mic input (if `mic` enabled).
- Receiver should hear sender system sound (if `system_audio` enabled).
- Receiver should hear mixed mic + system sound (if both are enabled).

---

## 10) Stop and Safety

- Press `q` on receiver video window to stop.
- Press `Ctrl + C` in sender terminal to stop.
- Keep sender display scaling stable during session for best pointer precision.
- Keep token private.

---

## 11) Troubleshooting

### Connection error / timeout

- Start receiver first.
- Check IP and port.
- Check token match.
- Allow Python through Windows Firewall.
- Verify Tailscale is connected or port forwarding is correct.

### Mouse click not exact

- Keep sender on stable display scaling/resolution while connected.
- Use `--scale 1.0` on sender for best precision.

### Audio not working

- Ensure `mic` or `system_audio` is included in `--control` on both sides.
- Try `--audio-rate 44100`.
- Check microphone permission and device availability.
- For system audio, prefer `--audio-channels 2`.
- If needed, set `--system-audio-device` to the speaker/output device index.
- If you get a `WasapiSettings...loopback` error, update `sounddevice`; fallback loopback capture is now supported.
- For mixed audio, set `--control screen,mic,system_audio` on both sides.

---

## 12) Minimal Quick Start

Receiver:

```bash
python screen_receiver.py --host 0.0.0.0 --port 9999 --token mysecret --control screen,mouse,keyboard,mic,system_audio
```

Sender:

```bash
python screen_sender.py --host <receiver_ip> --port 9999 --token mysecret --control screen,mouse,keyboard,mic,system_audio --audio-rate 48000 --audio-channels 2
```
