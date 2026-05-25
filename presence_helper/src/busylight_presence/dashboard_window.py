"""Main BusyLight Presence window.

Always-on dashboard the user lands on when they click the tray icon.
Works whether or not the device is on Wi-Fi: state changes and quick
actions go over USB serial, the web UI is just one optional button
away.

Layout (top to bottom):

    +------------------------------------------------+
    |  BusyLight Presence              v0.3.x        |
    |                                                |
    |        (LED bead 160 px, live colour)          |
    |               AVAILABLE                        |
    |        Connected over USB · COM3               |
    |                                                |
    |  [Available] [Busy] [In call] [Away] [Off]     |
    |                                                |
    |  Today                                         |
    |   Available:  2h 14m                           |
    |   Busy:       0h 35m                           |
    |   ...                                          |
    |                                                |
    |  [Open device web UI]  [Add Wi-Fi]             |
    |  [Settings]                                    |
    +------------------------------------------------+

The web UI button enables itself only when the device reports
Wi-Fi as up via `get_info`. "Add Wi-Fi" works over USB and doesn't
require Wi-Fi to begin with — that's the whole point.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from . import __version__
from .bead import render_bead
from .serial_client import (
    SerialClient,
    SerialProtocolError,
    SerialUnavailable,
    find_busylight_ports,
)

log = logging.getLogger(__name__)


STATE_COLORS = {
    "AVAILABLE": "#34c759",
    "BUSY":      "#e74c3c",
    "IN_CALL":   "#f59e0b",
    "AWAY":      "#6c8bbd",
    "OFF":       "#94989f",
}

_STATE_LABEL = {
    "AVAILABLE": "Available",
    "BUSY":      "Busy",
    "IN_CALL":   "In a call",
    "AWAY":      "Away",
    "OFF":       "Off",
}


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    if h == 0:
        return f"{m}m"
    return f"{h}h {m:02d}m"


def _darken(hex_color: str, amount: float = 0.12) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f"#{r:02x}{g:02x}{b:02x}"


class DashboardWindow:
    def __init__(
        self,
        loop,
        on_open_settings: Callable[[], None],
        on_set_state: Callable[[str], None],
        on_open_webui: Callable[[Optional[str]], None],
    ) -> None:
        self._loop = loop
        self._on_open_settings = on_open_settings
        self._on_set_state = on_set_state
        self._on_open_webui = on_open_webui
        self._root: Optional[ctk.CTk] = None
        self._bead_label: Optional[ctk.CTkLabel] = None
        self._state_label: Optional[ctk.CTkLabel] = None
        self._transport_label: Optional[ctk.CTkLabel] = None
        self._webui_button: Optional[ctk.CTkButton] = None
        self._stats_labels: dict[str, ctk.CTkLabel] = {}
        self._refresh_job: Optional[str] = None
        self._cached_info: dict = {}

    def open(self) -> None:
        if self._root is not None:
            try:
                if self._root.winfo_exists():
                    self._root.destroy()
            except tk.TclError:
                pass
            self._root = None

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        root = ctk.CTk()
        root.title("BusyLight Presence")
        root.geometry("470x800")
        root.resizable(False, False)

        outer = ctk.CTkFrame(root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        self._build_header(outer)
        self._build_hero(outer)
        self._build_quick_actions(outer)
        self._build_stats(outer)
        self._build_action_buttons(outer)

        def _on_close() -> None:
            self._cancel_refresh(root)
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.protocol("WM_DELETE_WINDOW", _on_close)
        self._root = root
        # Kick a non-blocking info probe in the background so the
        # "Open device web UI" button enables itself as soon as the
        # device tells us Wi-Fi is up.
        threading.Thread(target=self._probe_device_info, daemon=True).start()
        self._refresh_loop(root)
        root.mainloop()
        self._root = None

    def close(self) -> None:
        if self._root is not None:
            try:
                self._cancel_refresh(self._root)
                self._root.destroy()
            except tk.TclError:
                pass
        self._root = None

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def _build_header(self, parent: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(
            row,
            text="BusyLight Presence",
            font=ctk.CTkFont("Segoe UI Semibold", 17),
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text=f"v{__version__}",
            font=ctk.CTkFont("JetBrains Mono", 11),
            text_color="#888",
        ).pack(side="right")

    def _build_hero(self, parent: ctk.CTkFrame) -> None:
        hero = ctk.CTkFrame(parent, corner_radius=18, fg_color="#f6f7f9")
        hero.pack(fill="x", pady=(16, 14))

        self._bead_label = ctk.CTkLabel(hero, text="", image=None)
        self._bead_label.pack(pady=(22, 6))

        self._state_label = ctk.CTkLabel(
            hero,
            text="—",
            font=ctk.CTkFont("Segoe UI Semibold", 22),
        )
        self._state_label.pack()

        self._transport_label = ctk.CTkLabel(
            hero,
            text="",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#5d6066",
        )
        self._transport_label.pack(pady=(2, 22))

    def _build_quick_actions(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="Set status",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x", pady=(2, 6))

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x")
        for i in range(5):
            grid.columnconfigure(i, weight=1, uniform="state")

        states = [
            ("AVAILABLE", "Available"),
            ("BUSY",      "Busy"),
            ("IN_CALL",   "In call"),
            ("AWAY",      "Away"),
            ("OFF",       "Off"),
        ]
        for col, (state, label) in enumerate(states):
            color = STATE_COLORS[state]
            btn = ctk.CTkButton(
                grid,
                text=label,
                fg_color=color,
                hover_color=_darken(color),
                text_color="#ffffff",
                font=ctk.CTkFont("Segoe UI Semibold", 11),
                height=38,
                corner_radius=10,
                command=lambda s=state: self._handle_set_state(s),
            )
            btn.grid(row=0, column=col, padx=3, sticky="ew")

    def _build_stats(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="Today",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x", pady=(20, 6))

        card = ctk.CTkFrame(parent, corner_radius=14, fg_color="#f6f7f9")
        card.pack(fill="x")
        for state in ("AVAILABLE", "BUSY", "IN_CALL", "AWAY", "OFF"):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=4)

            dot = ctk.CTkFrame(
                row, width=10, height=10, corner_radius=5,
                fg_color=STATE_COLORS[state],
            )
            dot.pack(side="left", padx=(0, 10))
            dot.pack_propagate(False)

            ctk.CTkLabel(
                row, text=_STATE_LABEL[state],
                font=ctk.CTkFont("Segoe UI", 12),
                anchor="w",
            ).pack(side="left")

            value = ctk.CTkLabel(
                row, text="—",
                font=ctk.CTkFont("JetBrains Mono", 12),
                text_color="#3a3d42",
                anchor="e",
            )
            value.pack(side="right")
            self._stats_labels[state] = value

    def _build_action_buttons(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="More",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x", pady=(20, 6))

        # Row: Open web UI + Add Wi-Fi
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        row1.columnconfigure(0, weight=1, uniform="actions")
        row1.columnconfigure(1, weight=1, uniform="actions")

        self._webui_button = ctk.CTkButton(
            row1,
            text="Open device web UI",
            fg_color="#3a82f7",
            hover_color="#2f6fd4",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=38,
            corner_radius=10,
            state="disabled",
            command=self._handle_open_webui,
        )
        self._webui_button.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(
            row1,
            text="Add Wi-Fi",
            fg_color="#34c759",
            hover_color="#2eaa4d",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=38,
            corner_radius=10,
            command=self._handle_add_wifi,
        ).grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # Row: Settings (full width-ish)
        ctk.CTkButton(
            parent,
            text="Settings…",
            fg_color="#e8eaee",
            hover_color="#dcdee2",
            text_color="#2a2d33",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=36,
            corner_radius=9,
            command=self._handle_open_settings,
        ).pack(fill="x")

    # ------------------------------------------------------------------
    # Live updates
    # ------------------------------------------------------------------
    def _refresh_loop(self, root: ctk.CTk) -> None:
        try:
            self._refresh_once()
        except Exception as e:  # noqa: BLE001
            log.debug("dashboard refresh error: %s", e)
        self._refresh_job = root.after(500, lambda: self._refresh_loop(root))

    def _cancel_refresh(self, root: ctk.CTk) -> None:
        if self._refresh_job is not None:
            try:
                root.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
            self._refresh_job = None

    def _probe_device_info(self) -> None:
        """Background: ask the device about its Wi-Fi/IP every few s
        so the 'Open web UI' button can enable itself once available."""
        import time
        while self._root is not None:
            try:
                ports = find_busylight_ports()
                if ports:
                    sc = SerialClient(port=ports[0])
                    info = sc.get_info()
                    self._cached_info = info or {}
            except (SerialUnavailable, SerialProtocolError, Exception):
                pass
            time.sleep(5)

    def _refresh_once(self) -> None:
        state = self._loop.last_pushed_state or self._loop.last_manual_state
        if state is None or state not in STATE_COLORS:
            state = "AVAILABLE"

        img = render_bead(state, 160)
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(160, 160))
        if self._bead_label is not None:
            self._bead_label.configure(image=ctk_img, text="")
            self._bead_label.image = ctk_img

        if self._state_label is not None:
            self._state_label.configure(
                text=_STATE_LABEL.get(state, state),
                text_color=STATE_COLORS.get(state, "#3a3d42"),
            )

        mode = getattr(self._loop.client, "current_mode", None)
        port = getattr(self._loop.client, "serial_port", None)
        host = self._loop.cfg.host
        if mode == "serial" and port:
            text = f"Connected over USB · {port}"
            color = "#16744a"
        elif mode == "http" and host:
            text = f"Connected over Wi-Fi · {host}"
            color = "#16744a"
        else:
            text = "Disconnected — plug in the cable or set Wi-Fi in Settings"
            color = "#a35a00"
        if self._transport_label is not None:
            self._transport_label.configure(text=text, text_color=color)

        stats = getattr(self._loop, "stats", None)
        for state_key, label in self._stats_labels.items():
            seconds = stats.get(state_key, 0.0) if stats else 0.0
            label.configure(text=_format_duration(seconds))

        # Toggle "Open web UI" availability based on the background
        # info probe. We don't disable the button entirely when the
        # device has no Wi-Fi yet — instead we leave a tooltip in the
        # label that explains, and the click handler shows a message.
        if self._webui_button is not None:
            if self._cached_info.get("wifi") and self._cached_info.get("ip"):
                self._webui_button.configure(state="normal")
            else:
                self._webui_button.configure(state="disabled")

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------
    def _handle_set_state(self, state: str) -> None:
        try:
            self._on_set_state(state)
        except Exception as e:  # noqa: BLE001
            log.warning("set state %s failed: %s", state, e)
        self._refresh_once()

    def _handle_open_settings(self) -> None:
        if self._root is not None:
            self._cancel_refresh(self._root)
            try:
                self._root.destroy()
            except tk.TclError:
                pass
            self._root = None
        self._on_open_settings()

    def _handle_open_webui(self) -> None:
        ip = self._cached_info.get("ip")
        host = self._cached_info.get("host")
        url: Optional[str] = None
        if self._cached_info.get("wifi") and ip:
            url = f"http://{ip}"
        elif host:
            url = f"http://{host}.local"
        if not url:
            # Shouldn't happen because the button is disabled in this
            # case, but guard anyway.
            return
        if self._root is not None:
            self._cancel_refresh(self._root)
            try:
                self._root.destroy()
            except tk.TclError:
                pass
            self._root = None
        self._on_open_webui(url)

    def _handle_add_wifi(self) -> None:
        AddWifiDialog(self._root, on_done=self._refresh_once).open()


# ---------------------------------------------------------------------------
# Add Wi-Fi modal
# ---------------------------------------------------------------------------

class AddWifiDialog:
    """Tiny modal that posts cmd:wifi_add to the device over USB."""

    def __init__(
        self,
        parent: Optional[ctk.CTk],
        on_done: Callable[[], None],
    ) -> None:
        self._parent = parent
        self._on_done = on_done

    def open(self) -> None:
        # Use CTkToplevel so the modal sits above the dashboard.
        top = ctk.CTkToplevel(self._parent) if self._parent else ctk.CTk()
        top.title("Add Wi-Fi network")
        top.geometry("400x300")
        top.resizable(False, False)
        # Modal-ish: grab the focus.
        if self._parent is not None:
            top.transient(self._parent)
            top.grab_set()

        outer = ctk.CTkFrame(top, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=18)

        ctk.CTkLabel(
            outer,
            text="Add Wi-Fi network",
            font=ctk.CTkFont("Segoe UI Semibold", 15),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            outer,
            text=(
                "Sent to the device over USB. The new network joins "
                "the saved list — your existing networks and PIN are "
                "untouched."
            ),
            wraplength=360, justify="left",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#5d6066",
        ).pack(fill="x", pady=(0, 12))

        ssid_var = tk.StringVar(value="")
        pwd_var = tk.StringVar(value="")

        ctk.CTkLabel(
            outer, text="SSID",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x")
        ctk.CTkEntry(
            outer, textvariable=ssid_var,
            font=ctk.CTkFont("Segoe UI", 12),
            height=32,
        ).pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(
            outer, text="Password",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x")
        ctk.CTkEntry(
            outer, textvariable=pwd_var, show="•",
            font=ctk.CTkFont("Segoe UI", 12),
            height=32,
        ).pack(fill="x", pady=(2, 4))

        msg_var = tk.StringVar(value="")
        ctk.CTkLabel(
            outer, textvariable=msg_var,
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#c0392b",
        ).pack(anchor="w", pady=(4, 8))

        def do_add() -> None:
            ssid = ssid_var.get().strip()
            pwd = pwd_var.get()
            if not ssid:
                msg_var.set("SSID is required")
                return
            ports = find_busylight_ports()
            if not ports:
                msg_var.set("No USB device — plug in the cable.")
                return
            try:
                sc = SerialClient(port=ports[0])
                sc.wifi_add(ssid, pwd)
            except (SerialUnavailable, SerialProtocolError) as e:
                msg_var.set(str(e))
                return
            msg_var.set("Added. Device is connecting in the background.")
            top.after(900, top.destroy)
            self._on_done()

        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(
            btn_row, text="Cancel",
            fg_color="#e8eaee",
            hover_color="#dcdee2",
            text_color="#2a2d33",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=34, corner_radius=9,
            command=top.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row, text="Add",
            fg_color="#34c759",
            hover_color="#2eaa4d",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=34, corner_radius=9,
            command=do_add,
        ).pack(side="right")

        if self._parent is None:
            top.mainloop()
