import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

import screen_sender


class SenderGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Screen Sender UI")
        self.root.geometry("540x500")
        self.process: subprocess.Popen | None = None

        self.host_var = tk.StringVar()
        self.port_var = tk.StringVar(value="9999")
        self.token_var = tk.StringVar(value="mysecret")
        self.control_var = tk.StringVar(value="screen,mouse,keyboard,mic,system_audio")
        self.fps_var = tk.StringVar(value="12")
        self.quality_var = tk.StringVar(value="65")
        self.monitor_var = tk.StringVar(value="1")
        self.scale_var = tk.StringVar(value="1.0")
        self.audio_rate_var = tk.StringVar(value="48000")
        self.audio_channels_var = tk.StringVar(value="2")
        self.system_audio_device_var = tk.StringVar(value="")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=12, pady=12)
        frame.pack(fill="both", expand=True)

        fields = [
            ("Receiver Host/IP", self.host_var),
            ("Port", self.port_var),
            ("Token", self.token_var),
            ("Control Features", self.control_var),
            ("FPS", self.fps_var),
            ("Quality (1-100)", self.quality_var),
            ("Monitor", self.monitor_var),
            ("Scale", self.scale_var),
            ("Audio Rate", self.audio_rate_var),
            ("Audio Channels", self.audio_channels_var),
            ("System Audio Device (optional)", self.system_audio_device_var),
        ]

        for idx, (label, var) in enumerate(fields):
            tk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=2)
            entry = tk.Entry(frame, textvariable=var, width=48)
            entry.grid(row=idx, column=1, sticky="ew", padx=8, pady=2)

        frame.grid_columnconfigure(1, weight=1)

        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(10, 8))

        self.start_btn = tk.Button(btn_frame, text="Start Sender (Background)", command=self.start_sender)
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = tk.Button(btn_frame, text="Stop Sender", command=self.stop_sender, state="disabled")
        self.stop_btn.pack(side="left")

        self.status_var = tk.StringVar(value="Idle")
        tk.Label(frame, textvariable=self.status_var, fg="#004b87").grid(
            row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=(2, 6)
        )

        self.log_text = tk.Text(frame, height=12, wrap="word")
        self.log_text.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="nsew")
        frame.grid_rowconfigure(len(fields) + 2, weight=1)

    def _append_log(self, text: str) -> None:
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _build_command(self) -> list[str]:
        if not self.host_var.get().strip():
            raise ValueError("Receiver Host/IP is required.")

        sender_args = [
            "--host",
            self.host_var.get().strip(),
            "--port",
            self.port_var.get().strip(),
            "--token",
            self.token_var.get().strip(),
            "--control",
            self.control_var.get().strip(),
            "--fps",
            self.fps_var.get().strip(),
            "--quality",
            self.quality_var.get().strip(),
            "--monitor",
            self.monitor_var.get().strip(),
            "--scale",
            self.scale_var.get().strip(),
            "--audio-rate",
            self.audio_rate_var.get().strip(),
            "--audio-channels",
            self.audio_channels_var.get().strip(),
        ]

        if self.system_audio_device_var.get().strip():
            sender_args.extend(["--system-audio-device", self.system_audio_device_var.get().strip()])

        # In bundled EXE mode, launch this same EXE with --run-sender.
        if getattr(sys, "frozen", False):
            return [sys.executable, "--run-sender", *sender_args]

        # In script mode, launch this script with --run-sender using python.
        return [sys.executable, __file__, "--run-sender", *sender_args]

    def start_sender(self) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showinfo("Already Running", "Sender is already running.")
            return

        try:
            cmd = self._build_command()
        except ValueError as exc:
            messagebox.showerror("Invalid Input", str(exc))
            return

        self._append_log("Starting sender in background...")
        self._append_log(" ".join(cmd))

        creationflags = 0
        if hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"):
            creationflags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )
        except Exception as exc:
            messagebox.showerror("Start Failed", str(exc))
            self.process = None
            return

        self.status_var.set(f"Running in background (PID {self.process.pid})")
        self._append_log(f"Sender started in background. PID: {self.process.pid}")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def stop_sender(self) -> None:
        if self.process is None or self.process.poll() is not None:
            self.status_var.set("Idle")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            return

        self._append_log("Stopping sender...")
        self.process.terminate()
        self.status_var.set("Stopped")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def on_close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            # Keep app process alive and hide UI so sender keeps running.
            self.root.withdraw()
            return
        self.root.destroy()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--run-sender":
        # Forward all remaining args to screen_sender.
        sys.argv = ["screen_sender.py", *sys.argv[2:]]
        screen_sender.main()
        return

    root = tk.Tk()
    SenderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
