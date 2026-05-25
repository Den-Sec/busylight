"""Progress dialog for the in-app updater.

A small customtkinter window with a header, a description label that
updates as the install progresses ("Downloading… 7.4 MB / 19 MB",
"Installing…", "Restarting…"), and an indeterminate-or-determinate
progress bar.

Lives on its own thread so it doesn't fight pystray's main-thread
message loop. The caller updates it via `set_progress()` /
`set_message()` from any thread; we marshall the calls onto the Tk
thread via `after()`.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from .bead import render_bead

log = logging.getLogger(__name__)


class UpdateProgressWindow:
    """Thread-safe progress dialog. Construct, call `start()` to show,
    then `set_progress` / `set_message` from anywhere. Call `close()`
    when done."""

    def __init__(self, title: str = "BusyLight update") -> None:
        self._title = title
        self._thread: Optional[threading.Thread] = None
        self._root: Optional[ctk.CTk] = None
        self._cmd_q: queue.Queue[tuple[str, object]] = queue.Queue()
        self._ready_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="update-progress",
        )
        self._thread.start()
        # Wait until Tk root + widgets exist so the first set_*
        # actually has somewhere to land.
        self._ready_event.wait(timeout=3.0)

    def set_message(self, text: str) -> None:
        self._cmd_q.put(("message", text))

    def set_progress(self, fraction: float) -> None:
        """`fraction` is 0.0 to 1.0. Pass None for indeterminate."""
        self._cmd_q.put(("progress", max(0.0, min(1.0, fraction))))

    def set_indeterminate(self) -> None:
        self._cmd_q.put(("indeterminate", None))

    def close(self) -> None:
        self._cmd_q.put(("close", None))
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ------------------------------------------------------------------
    # Tk thread
    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            ctk.set_appearance_mode("light")
            ctk.set_default_color_theme("blue")
            root = ctk.CTk()
            self._root = root
            root.title(self._title)
            root.geometry("440x220")
            root.resizable(False, False)
            root.attributes("-topmost", True)
            root.protocol("WM_DELETE_WINDOW", lambda: None)  # disable X

            outer = ctk.CTkFrame(root, fg_color="transparent")
            outer.pack(fill="both", expand=True, padx=22, pady=18)

            head = ctk.CTkFrame(outer, fg_color="transparent")
            head.pack(fill="x")
            bead_img = render_bead("available", 38)
            ctk_bead = ctk.CTkImage(light_image=bead_img, size=(38, 38))
            bead_lbl = ctk.CTkLabel(head, text="", image=ctk_bead)
            bead_lbl.image = ctk_bead
            bead_lbl.pack(side="left")
            ctk.CTkLabel(
                head,
                text=self._title,
                font=ctk.CTkFont("Segoe UI Semibold", 15),
                anchor="w",
            ).pack(side="left", padx=(10, 0))

            msg_var = tk.StringVar(value="Starting…")
            ctk.CTkLabel(
                outer,
                textvariable=msg_var,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color="#3a3d42",
                wraplength=400,
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=(12, 8))

            bar = ctk.CTkProgressBar(outer, height=14)
            bar.pack(fill="x", pady=(0, 8))
            bar.set(0.0)

            pct_var = tk.StringVar(value="")
            ctk.CTkLabel(
                outer,
                textvariable=pct_var,
                font=ctk.CTkFont("JetBrains Mono", 10),
                text_color="#5d6066",
                anchor="e",
            ).pack(fill="x")

            indeterminate_running = {"on": False}

            def pump() -> None:
                # Drain any pending commands from the worker thread.
                while True:
                    try:
                        cmd, payload = self._cmd_q.get_nowait()
                    except queue.Empty:
                        break
                    if cmd == "message":
                        msg_var.set(str(payload))
                    elif cmd == "progress":
                        if indeterminate_running["on"]:
                            bar.stop()
                            bar.configure(mode="determinate")
                            indeterminate_running["on"] = False
                        f = float(payload)  # type: ignore[arg-type]
                        bar.set(f)
                        pct_var.set(f"{int(f * 100)} %")
                    elif cmd == "indeterminate":
                        if not indeterminate_running["on"]:
                            bar.configure(mode="indeterminate")
                            bar.start()
                            indeterminate_running["on"] = True
                        pct_var.set("")
                    elif cmd == "close":
                        try:
                            root.destroy()
                        except tk.TclError:
                            pass
                        return
                root.after(50, pump)

            self._ready_event.set()
            root.after(50, pump)
            root.mainloop()
        except Exception as e:  # noqa: BLE001
            log.exception("update progress window crashed: %s", e)
            self._ready_event.set()
