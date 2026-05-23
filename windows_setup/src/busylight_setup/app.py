from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import tkinter as tk
import time
from tkinter import messagebox, ttk

from . import serial_protocol as sp
from .serial_protocol import (
    SetupResult,
    available_busylight_ports,
    configure_device,
)
from .validation import validate_password, validate_pin, validate_ssid


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


class SetupWizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BusyLight Setup Wizard")
        self.geometry("560x420")
        self.resizable(False, False)

        self.port_var = tk.StringVar()
        self.ssid_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.pin_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Connect BusyLight via USB, then configure.")
        self.is_configuring = False
        self._port_devices: list[str] = []
        self._configure_process: mp.Process | None = None
        self._result_queue: "mp.Queue[dict] | None" = None
        self._configure_deadline: float | None = None
        self._poll_token = 0
        self._poll_after_id: str | None = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.refresh_ports()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="BusyLight First Setup", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(root, text="Configure Wi-Fi and PIN over USB", foreground="#555").pack(anchor="w", pady=(0, 16))

        form = ttk.Frame(root)
        form.pack(fill="x")

        ttk.Label(form, text="COM Port").grid(row=0, column=0, sticky="w", pady=6)
        self.port_box = ttk.Combobox(form, textvariable=self.port_var, state="readonly")
        self.port_box.grid(row=0, column=1, sticky="ew", padx=(10, 8), pady=6)
        self.refresh_btn = ttk.Button(form, text="Refresh", command=self.refresh_ports)
        self.refresh_btn.grid(row=0, column=2, sticky="ew", pady=6)

        ttk.Label(form, text="Wi-Fi SSID").grid(row=1, column=0, sticky="w", pady=6)
        self.ssid_entry = ttk.Entry(form, textvariable=self.ssid_var)
        self.ssid_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=6)

        ttk.Label(form, text="Wi-Fi Password").grid(row=2, column=0, sticky="w", pady=6)
        self.password_entry = ttk.Entry(form, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=6)

        ttk.Label(form, text="PIN (4-8 digits)").grid(row=3, column=0, sticky="w", pady=6)
        self.pin_entry = ttk.Entry(form, textvariable=self.pin_var, show="*")
        self.pin_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=6)

        form.columnconfigure(1, weight=1)

        self.configure_btn = ttk.Button(root, text="Configure BusyLight", command=self.on_configure)
        self.configure_btn.pack(fill="x", pady=(18, 10))
        ttk.Label(root, textvariable=self.status_var, wraplength=520).pack(anchor="w")

        notes = (
            "After success, open:\n"
            "1) http://busylight.local\n"
            "2) If .local does not resolve, use the fallback IP shown by your router or by this wizard when detected."
        )
        ttk.Label(root, text=notes, foreground="#555", wraplength=520, justify="left").pack(anchor="w", pady=(20, 0))

    def refresh_ports(self) -> None:
        ports = available_busylight_ports()
        # Show "COM3 - USB Serial Device" so users can pick by description.
        display_values = [f"{device}  -  {desc}" for device, desc in ports]
        self.port_box["values"] = display_values
        self._port_devices = [device for device, _ in ports]
        if display_values:
            self.port_box.current(0)
            self.port_var.set(display_values[0])
            self.status_var.set(
                f"Detected {len(display_values)} serial port(s). "
                "If yours is not listed, press Refresh."
            )
        else:
            self.port_var.set("")
            self._port_devices = []
            self.status_var.set("No serial ports detected. Connect BusyLight and press Refresh.")

    def _selected_port_device(self) -> str:
        """Resolve the display string back to the underlying COM device."""
        selected = self.port_var.get().strip()
        if not selected:
            return ""
        values = list(self.port_box["values"]) if self.port_box["values"] else []
        if selected in values:
            return self._port_devices[values.index(selected)]
        # User typed something custom — accept as-is so manual override works.
        return selected.split(" ")[0]

    def on_configure(self) -> None:
        if self.is_configuring:
            return

        try:
            port = self._selected_port_device()
            if not port:
                raise ValueError("Select a COM port.")

            ssid = validate_ssid(self.ssid_var.get())
            password = validate_password(self.password_var.get())
            pin = validate_pin(self.pin_var.get())

            self._set_busy(True)
            self.status_var.set("Configuring BusyLight... keep USB connected.")
            self._start_configure_process(port, ssid, password, pin)
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Setup failed: {exc}")
            messagebox.showerror("BusyLight Setup", str(exc))

    def _start_configure_process(self, port: str, ssid: str, password: str, pin: str) -> None:
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
        result_queue = self._result_queue
        deadline = self._configure_deadline
        if not proc or not result_queue:
            return

        # Drain queue first so we do not miss a just-completed result.
        while True:
            try:
                msg = result_queue.get_nowait()
            except queue.Empty:
                break

            if msg.get("type") == "progress":
                progress_text = str(msg.get("text", "")).strip()
                if progress_text:
                    self.status_var.set(progress_text)
                continue

            if msg.get("type") == "result":
                self._cleanup_configure_runtime()
                if msg.get("ok") is True:
                    result = SetupResult(
                        mdns_url=str(msg.get("mdns_url", "http://busylight.local")),
                        ip_url=msg.get("ip_url"),
                    )
                    self._on_configure_success(result)
                else:
                    self._on_configure_error(str(msg.get("error", "Unknown setup error.")))
                return

        now = time.monotonic()
        if deadline and now > deadline:
            self._terminate_configure_process()
            self._cleanup_configure_runtime()
            self._on_configure_error(
                "Setup timed out waiting for BusyLight response. Close any other tool using COM, unplug/replug USB, then retry."
            )
            return

        if not proc.is_alive():
            self._cleanup_configure_runtime()
            self._on_configure_error(
                "Setup process ended unexpectedly. Ensure COM port is free and retry."
            )
            return

        self._schedule_poll(token)

    def _on_configure_success(self, result: SetupResult) -> None:
        # We always have an mdns_url (e.g. http://busylight-f5f0.local). The
        # ip_url is often missing because the device re-enumerates its USB
        # CDC port during the post-config reboot, so the wizard loses the
        # serial sync before `server_started` arrives.
        # Try a 15 s mDNS browse on the LAN to recover it; the user gets
        # both URLs in the success dialog if it works.
        if result.ip_url or not result.mdns_url:
            self._set_busy(False)
            self._show_success(result)
            return

        self.status_var.set(
            "Looking up the device on your network…"
        )
        host = (
            result.mdns_url.replace("http://", "")
            .replace("https://", "")
            .rstrip("/")
            .split(".")[0]
        )

        def _worker(host: str, base_result: SetupResult) -> None:
            ip = sp.resolve_device_ip(host, timeout_s=15.0)
            if ip:
                updated = SetupResult(
                    mdns_url=base_result.mdns_url,
                    ip_url=f"http://{ip}",
                )
            else:
                updated = base_result

            def _finish() -> None:
                self._set_busy(False)
                self._show_success(updated)

            self.after(0, _finish)

        threading.Thread(
            target=_worker, args=(host, result), daemon=True
        ).start()

    def _on_configure_error(self, error_text: str) -> None:
        self._set_busy(False)
        self.status_var.set(f"Setup failed: {error_text}")
        messagebox.showerror("BusyLight Setup", error_text)

    def _set_busy(self, busy: bool) -> None:
        self.is_configuring = busy

        self.configure_btn.configure(state="disabled" if busy else "normal")
        self.refresh_btn.configure(state="disabled" if busy else "normal")
        self.port_box.configure(state="disabled" if busy else "readonly")
        self.ssid_entry.configure(state="disabled" if busy else "normal")
        self.password_entry.configure(state="disabled" if busy else "normal")
        self.pin_entry.configure(state="disabled" if busy else "normal")

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
            except Exception:
                pass
            self._poll_after_id = None
        self._terminate_configure_process()
        result_queue = self._result_queue
        if result_queue:
            try:
                result_queue.close()
            except Exception:
                pass
        self._configure_process = None
        self._result_queue = None
        self._configure_deadline = None

    def _on_close(self) -> None:
        self._cleanup_configure_runtime()
        self.destroy()

    def _show_success(self, result: SetupResult) -> None:
        lines = [
            "Configuration complete.",
            f"Open: {result.mdns_url}",
        ]
        if result.ip_url:
            lines.append(f"Fallback IP: {result.ip_url}")
        else:
            lines.append("Fallback IP not detected yet; check router DHCP list if needed.")

        msg = "\n".join(lines)
        self.status_var.set(msg)
        messagebox.showinfo("BusyLight Setup", msg)
