"""BusyLight Setup Wizard — premium look.

Single-window GUI that walks a user through their first device
provisioning. Built with customtkinter for round corners + modern
typography (Segoe UI Semibold), with a hand-drawn LED bead at the
top so the wizard feels like the same product as the web UI.

The actual serial provisioning still runs in a worker process so
the Tk UI never blocks while we talk to the ESP32 over USB.
"""

from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import tkinter as tk
import time
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from . import serial_protocol as sp
from .serial_protocol import (
    SetupResult,
    available_busylight_ports,
    configure_device,
)
from .validation import validate_password, validate_pin, validate_ssid


# ----------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("green")

# Hand-picked tokens that mirror the device's web UI (see
# firmware/data/styles.css). Keeps the wizard and the post-setup
# webpage feeling like the same product.
BG = "#eeece6"            # paper-warm background
SURFACE = "#fbfaf6"       # cards
LINE = "#d9d4c8"          # subtle borders
INK = "#15161a"
INK_MUTE = "#5e6168"
INK_FAINT = "#8f8d83"
AVAILABLE = "#34c759"     # state-green
BUSY = "#e74c3c"          # state-red (used for danger button)


# ----------------------------------------------------------------------
# Subprocess for the blocking serial call
# ----------------------------------------------------------------------

def _configure_subprocess_entry(
    port: str,
    ssid: str,
    password: str,
    pin: str,
    result_queue: "mp.Queue[dict]",
) -> None:
    try:
        def progress(text: str) -> None:
            result_queue.put({"type": "progress", "text": text})

        result = configure_device(port, ssid, password, pin, on_progress=progress)
        result_queue.put(
            {
                "type": "result",
                "ok": True,
                "mdns_url": result.mdns_url,
                "ip_url": result.ip_url,
            }
        )
    except Exception as exc:  # noqa: BLE001
        result_queue.put({"type": "result", "ok": False, "error": str(exc)})


def _factory_reset_subprocess(
    port: str, result_queue: "mp.Queue[dict]"
) -> None:
    import json
    import serial

    try:
        with serial.Serial(
            port=port,
            baudrate=115200,
            timeout=2.0,
            write_timeout=2.0,
            dsrdtr=False,
            rtscts=False,
        ) as ser:
            ser.dtr = True
            ser.rts = False
            time.sleep(0.3)
            ser.reset_input_buffer()
            ser.write(
                (json.dumps({"cmd": "factory_reset", "confirm": "YES"}) + "\n").encode()
            )
            ser.flush()
            deadline = time.time() + 5
            while time.time() < deadline:
                line = ser.readline()
                if not line:
                    continue
                text = line.decode("utf-8", errors="replace").strip()
                if "factory_reset_ok" in text:
                    result_queue.put({"type": "result", "ok": True})
                    return
        result_queue.put(
            {"type": "result", "ok": False, "error": "Device did not acknowledge."}
        )
    except Exception as exc:  # noqa: BLE001
        result_queue.put({"type": "result", "ok": False, "error": str(exc)})


# ----------------------------------------------------------------------
# Bead graphic
# ----------------------------------------------------------------------

def _bead_image(size: int = 110) -> ImageTk.PhotoImage:
    """A small green LED-bead PIL/Tk image to anchor the header."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        (4, 4, size - 4, size - 4),
        fill=(52, 199, 89, 110),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(7))
    img = Image.alpha_composite(img, halo)
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        (size * 0.18, size * 0.18, size * 0.82, size * 0.82),
        fill=(52, 199, 89, 255),
    )
    # Concentric ring (matches the web UI's hero-bead-shine).
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    pad = size * 0.10
    ring_draw.ellipse(
        (pad, pad, size - pad, size - pad),
        outline=(52, 199, 89, 110),
        width=3,
    )
    img = Image.alpha_composite(img, ring)
    return ImageTk.PhotoImage(img)


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------

class SetupWizard(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BusyLight — First Setup")
        self.geometry("580x720")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        # State
        self.port_var = tk.StringVar()
        self.ssid_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.pin_var = tk.StringVar()
        self.status_var = tk.StringVar(
            value="Plug your BusyLight into a USB port to get started."
        )
        self.is_busy = False
        self._port_devices: list[str] = []
        self._configure_process: Optional[mp.Process] = None
        self._reset_process: Optional[mp.Process] = None
        self._result_queue: Optional["mp.Queue[dict]"] = None
        self._poll_after_id: Optional[str] = None
        self._poll_token = 0
        self._configure_deadline: Optional[float] = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.refresh_ports()

    # ------------------------------------------------------------------
    # UI scaffold
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        # ---- header ----
        header = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        header.pack(fill="x", padx=28, pady=(26, 8))

        self._bead_img = _bead_image(96)
        bead = tk.Label(header, image=self._bead_img, bg=BG, borderwidth=0)
        bead.pack(pady=(2, 6))

        ctk.CTkLabel(
            header,
            text="Let's get you online.",
            font=("Segoe UI Semibold", 22),
            text_color=INK,
            fg_color=BG,
        ).pack()
        ctk.CTkLabel(
            header,
            text=(
                "Configure the Wi-Fi and PIN for your BusyLight over USB.\n"
                "We'll talk to the device, save your settings and reboot it."
            ),
            font=("Segoe UI", 11),
            text_color=INK_MUTE,
            fg_color=BG,
            justify="center",
        ).pack(pady=(4, 14))

        # ---- card ----
        card = ctk.CTkFrame(
            outer,
            fg_color=SURFACE,
            corner_radius=18,
            border_color=LINE,
            border_width=1,
        )
        card.pack(fill="x", padx=22, pady=(2, 18))

        self._add_field(card, "COM port", row_first=True)
        port_row = ctk.CTkFrame(card, fg_color="transparent")
        port_row.pack(fill="x", padx=20, pady=(0, 8))
        self.port_box = ctk.CTkOptionMenu(
            port_row,
            variable=self.port_var,
            values=["(scanning...)"],
            width=320,
            height=36,
            corner_radius=10,
            fg_color=BG,
            text_color=INK,
            button_color=AVAILABLE,
            button_hover_color="#2ba34a",
        )
        self.port_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.refresh_btn = ctk.CTkButton(
            port_row,
            text="Refresh",
            command=self.refresh_ports,
            width=86,
            height=36,
            corner_radius=999,
            fg_color=BG,
            text_color=INK,
            border_color=LINE,
            border_width=1,
            hover_color="#e6e3d8",
        )
        self.refresh_btn.pack(side="right")

        self.ssid_entry = self._add_entry(card, "Wi-Fi network (SSID)", self.ssid_var)
        self.password_entry = self._add_entry(
            card, "Wi-Fi password", self.password_var, show="•"
        )
        self.pin_entry = self._add_entry(
            card,
            "Access PIN (4 to 8 digits)",
            self.pin_var,
            show="•",
            placeholder="e.g. 1234",
        )

        # progress + status
        ctk.CTkFrame(card, fg_color="transparent", height=4).pack()
        self.progress = ctk.CTkProgressBar(
            card,
            mode="indeterminate",
            corner_radius=999,
            progress_color=AVAILABLE,
            fg_color=BG,
            height=6,
        )
        self.progress.pack(fill="x", padx=20, pady=(2, 10))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            card,
            textvariable=self.status_var,
            font=("Segoe UI", 11),
            text_color=INK_MUTE,
            fg_color="transparent",
            wraplength=480,
            justify="left",
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=20, pady=(0, 12))

        self.configure_btn = ctk.CTkButton(
            card,
            text="Configure BusyLight    →",
            command=self.on_configure,
            height=46,
            corner_radius=12,
            fg_color=INK,
            text_color=SURFACE,
            hover_color="#2b2e34",
            font=("Segoe UI Semibold", 13),
        )
        self.configure_btn.pack(fill="x", padx=20, pady=(0, 12))

        self.retry_btn = ctk.CTkButton(
            card,
            text="Retry",
            command=self.on_configure,
            height=36,
            corner_radius=10,
            fg_color=SURFACE,
            text_color=INK,
            border_color=LINE,
            border_width=1,
            hover_color="#efece2",
        )
        # Hidden until something fails.
        self.retry_btn.pack_forget()

        # Outside the card: secondary controls
        bottom = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        bottom.pack(fill="x", padx=28, pady=(0, 18))

        self.factory_btn = ctk.CTkButton(
            bottom,
            text="Factory reset device",
            command=self.on_factory_reset,
            height=34,
            corner_radius=999,
            fg_color=BG,
            text_color=BUSY,
            border_color="#e3bdb6",
            border_width=1,
            hover_color="#fadcd5",
        )
        self.factory_btn.pack(side="right")

        ctk.CTkLabel(
            bottom,
            text="Connect via USB before resetting.",
            font=("Segoe UI", 10),
            text_color=INK_FAINT,
            fg_color=BG,
        ).pack(side="left", padx=(2, 0))

    def _add_field(
        self, parent: ctk.CTkFrame, label: str, *, row_first: bool = False
    ) -> None:
        pad_top = 16 if row_first else 4
        ctk.CTkLabel(
            parent,
            text=label,
            font=("Segoe UI", 11),
            text_color=INK_MUTE,
            fg_color="transparent",
            anchor="w",
        ).pack(fill="x", padx=20, pady=(pad_top, 2))

    def _add_entry(
        self,
        parent: ctk.CTkFrame,
        label: str,
        var: tk.StringVar,
        *,
        show: str = "",
        placeholder: str = "",
    ) -> ctk.CTkEntry:
        self._add_field(parent, label)
        entry = ctk.CTkEntry(
            parent,
            textvariable=var,
            show=show,
            placeholder_text=placeholder,
            height=38,
            corner_radius=10,
            fg_color=BG,
            text_color=INK,
            border_color=LINE,
            border_width=1,
            font=("JetBrains Mono", 12) if show else ("Segoe UI", 12),
        )
        entry.pack(fill="x", padx=20, pady=(0, 6))
        return entry

    # ------------------------------------------------------------------
    # Ports
    # ------------------------------------------------------------------
    def refresh_ports(self) -> None:
        ports = available_busylight_ports()
        display_values = [
            f"{device}  -  {desc}" for device, desc in ports
        ]
        self._port_devices = [device for device, _ in ports]
        if display_values:
            self.port_box.configure(values=display_values)
            self.port_var.set(display_values[0])
            self.status_var.set(
                f"Detected {len(display_values)} serial port(s). "
                "If yours isn't listed, press Refresh."
            )
        else:
            self.port_box.configure(values=["(no port detected)"])
            self.port_var.set("(no port detected)")
            self.status_var.set(
                "No serial ports detected. Plug the BusyLight in and press Refresh."
            )

    def _selected_port_device(self) -> str:
        selected = self.port_var.get().strip()
        if not selected or selected.startswith("("):
            return ""
        values = list(self.port_box.cget("values")) if self.port_box.cget("values") else []
        if selected in values:
            return self._port_devices[values.index(selected)]
        return selected.split(" ")[0]

    # ------------------------------------------------------------------
    # Configure flow
    # ------------------------------------------------------------------
    def on_configure(self) -> None:
        if self.is_busy:
            return
        try:
            port = self._selected_port_device()
            if not port:
                raise ValueError("Pick a COM port first.")
            ssid = validate_ssid(self.ssid_var.get())
            password = validate_password(self.password_var.get())
            pin = validate_pin(self.pin_var.get())
        except ValueError as e:
            self.status_var.set(f"⚠  {e}")
            self._show_retry()
            return

        self._set_busy(True)
        self.status_var.set("Configuring BusyLight… keep the USB cable connected.")
        self.progress.start()
        self._start_configure_process(port, ssid, password, pin)

    def _start_configure_process(
        self, port: str, ssid: str, password: str, pin: str
    ) -> None:
        ctx = mp.get_context("spawn")
        self._result_queue = ctx.Queue()
        self._configure_process = ctx.Process(
            target=_configure_subprocess_entry,
            args=(port, ssid, password, pin, self._result_queue),
            daemon=True,
        )
        self._configure_process.start()
        self._configure_deadline = time.monotonic() + 90.0
        self._poll_token += 1
        self._schedule_poll(self._poll_token)

    def _schedule_poll(self, token: int) -> None:
        self._poll_after_id = self.after(180, lambda: self._poll_configure_result(token))

    def _poll_configure_result(self, token: int) -> None:
        if token != self._poll_token:
            return
        proc = self._configure_process
        rq = self._result_queue
        if not proc or not rq:
            return
        while True:
            try:
                msg = rq.get_nowait()
            except queue.Empty:
                break
            if msg.get("type") == "progress":
                text = str(msg.get("text", "")).strip()
                if text:
                    self.status_var.set(text)
                continue
            if msg.get("type") == "result":
                self._cleanup_configure_runtime()
                if msg.get("ok") is True:
                    self._handle_success(
                        SetupResult(
                            mdns_url=str(msg.get("mdns_url", "")),
                            ip_url=msg.get("ip_url"),
                        )
                    )
                else:
                    self._handle_failure(str(msg.get("error", "Unknown error.")))
                return

        if (
            self._configure_deadline is not None
            and time.monotonic() > self._configure_deadline
        ):
            self._terminate_configure_process()
            self._cleanup_configure_runtime()
            self._handle_failure(
                "Setup timed out. Close any other tool using the COM port, "
                "unplug/replug the USB cable, and try again."
            )
            return

        if not proc.is_alive():
            self._cleanup_configure_runtime()
            self._handle_failure("Setup process ended unexpectedly.")
            return

        self._schedule_poll(token)

    def _handle_success(self, result: SetupResult) -> None:
        # Try a 15s mDNS lookup if the device didn't hand us an IP.
        if result.ip_url or not result.mdns_url:
            self._finish_success(result)
            return

        self.status_var.set("Looking up the device on your network…")
        host = (
            result.mdns_url.replace("http://", "")
            .replace("https://", "")
            .rstrip("/")
            .split(".")[0]
        )

        def worker() -> None:
            ip = sp.resolve_device_ip(host, timeout_s=15.0)
            updated = SetupResult(
                mdns_url=result.mdns_url,
                ip_url=f"http://{ip}" if ip else None,
            )
            self.after(0, lambda: self._finish_success(updated))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_success(self, result: SetupResult) -> None:
        self._set_busy(False)
        self.progress.stop()
        self.progress.set(1)

        lines = [
            "✓  BusyLight is configured.",
            "",
            f"Open  {result.mdns_url}",
        ]
        if result.ip_url:
            lines.append(f"Or    {result.ip_url}")
        else:
            lines.append("(IP not detected; check your router's DHCP list if mDNS fails.)")
        self.status_var.set("\n".join(lines))
        self._hide_retry()

    def _handle_failure(self, message: str) -> None:
        self._set_busy(False)
        self.progress.stop()
        self.progress.set(0)
        self.status_var.set(f"⚠  Setup failed.\n{message}")
        self._show_retry()

    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        state = "disabled" if busy else "normal"
        for w in (
            self.configure_btn,
            self.refresh_btn,
            self.port_box,
            self.ssid_entry,
            self.password_entry,
            self.pin_entry,
            self.factory_btn,
        ):
            try:
                w.configure(state=state)
            except Exception:  # noqa: BLE001
                pass

    def _show_retry(self) -> None:
        try:
            self.retry_btn.pack(fill="x", padx=20, pady=(0, 12))
        except Exception:  # noqa: BLE001
            pass

    def _hide_retry(self) -> None:
        try:
            self.retry_btn.pack_forget()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Factory reset
    # ------------------------------------------------------------------
    def on_factory_reset(self) -> None:
        if self.is_busy:
            return
        port = self._selected_port_device()
        if not port:
            self.status_var.set("Pick a COM port first.")
            return
        if not tk.messagebox.askyesno(
            "Factory reset",
            "Wipe Wi-Fi credentials AND the PIN on this BusyLight? "
            "You'll need to provision it again from scratch.",
        ):
            return
        self._set_busy(True)
        self.status_var.set("Sending factory_reset to BusyLight…")

        ctx = mp.get_context("spawn")
        rq = ctx.Queue()
        self._reset_process = ctx.Process(
            target=_factory_reset_subprocess, args=(port, rq), daemon=True
        )
        self._reset_process.start()

        def poll() -> None:
            try:
                msg = rq.get_nowait()
            except queue.Empty:
                if self._reset_process and self._reset_process.is_alive():
                    self.after(180, poll)
                else:
                    self._set_busy(False)
                    self.status_var.set("Reset process ended unexpectedly.")
                return
            self._set_busy(False)
            if msg.get("ok"):
                self.status_var.set(
                    "✓  Factory reset acknowledged. Device is rebooting. "
                    "Configure it again above."
                )
            else:
                self.status_var.set(f"⚠  Factory reset failed: {msg.get('error', '')}")

        self.after(180, poll)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _terminate_configure_process(self) -> None:
        proc = self._configure_process
        if not proc:
            return
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1.0)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1.0)

    def _cleanup_configure_runtime(self) -> None:
        if self._poll_after_id:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:  # noqa: BLE001
                pass
            self._poll_after_id = None
        self._terminate_configure_process()
        rq = self._result_queue
        if rq:
            try:
                rq.close()
            except Exception:  # noqa: BLE001
                pass
        self._configure_process = None
        self._result_queue = None
        self._configure_deadline = None

    def _on_close(self) -> None:
        self._cleanup_configure_runtime()
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass


# Make tk.messagebox importable as `tk.messagebox` even though we use
# customtkinter — it's still the standard tkinter dialog under the hood.
import tkinter.messagebox  # noqa: E402, F401
tk.messagebox = tkinter.messagebox  # type: ignore[attr-defined]
