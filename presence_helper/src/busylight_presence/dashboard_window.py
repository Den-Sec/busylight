"""Main BusyLight Presence window.

A small dashboard the user lands on when they click the tray icon.
Visual language matches the web UI (iOS-like palette, soft cards,
LED bead hero) so the desktop and the device feel like one product.

Layout:

    +---------------------------------------------+
    |  BusyLight Presence              v0.3.x     |
    |                                             |
    |       (LED bead, 160 px, live colour)       |
    |                                             |
    |              AVAILABLE                      |
    |        Connected over USB · COM3            |
    |                                             |
    |  [Available] [Busy] [In call] [Away] [Off]  |
    |                                             |
    |  Today                                      |
    |   Available:   2h 14m                       |
    |   Busy:        0h 35m                       |
    |   In call:     1h 02m                       |
    |                                             |
    |  [ Settings… ]                              |
    +---------------------------------------------+
"""

from __future__ import annotations

import logging
import tkinter as tk
from io import BytesIO
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image

from . import __version__
from .bead import render_bead

log = logging.getLogger(__name__)


# Match the web UI tile colours so the desktop and the device pages
# feel like one product.
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


class DashboardWindow:
    """customtkinter window. Use `open()` to show (creates Tk root)."""

    def __init__(
        self,
        loop,
        on_open_settings: Callable[[], None],
        on_set_state: Callable[[str], None],
    ) -> None:
        self._loop = loop
        self._on_open_settings = on_open_settings
        self._on_set_state = on_set_state
        self._root: Optional[ctk.CTk] = None
        self._bead_label: Optional[ctk.CTkLabel] = None
        self._state_label: Optional[ctk.CTkLabel] = None
        self._transport_label: Optional[ctk.CTkLabel] = None
        self._stats_labels: dict[str, ctk.CTkLabel] = {}
        self._refresh_job: Optional[str] = None

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
        root.geometry("460x740")
        root.resizable(False, False)

        # Window-level padding container.
        outer = ctk.CTkFrame(root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        self._build_header(outer)
        self._build_hero(outer)
        self._build_quick_actions(outer)
        self._build_stats(outer)
        self._build_footer(outer)

        # Closing the window just hides it; the tray keeps the helper alive.
        def _on_close() -> None:
            self._cancel_refresh(root)
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.protocol("WM_DELETE_WINDOW", _on_close)
        self._root = root
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
            anchor="e",
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
        # Order matches the web UI; OFF is hidden when 0 to keep the
        # card light when the user isn't using scheduling.
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
                row,
                text=_STATE_LABEL[state],
                font=ctk.CTkFont("Segoe UI", 12),
                anchor="w",
            ).pack(side="left")

            value = ctk.CTkLabel(
                row,
                text="—",
                font=ctk.CTkFont("JetBrains Mono", 12),
                text_color="#3a3d42",
                anchor="e",
            )
            value.pack(side="right")
            self._stats_labels[state] = value

    def _build_footer(self, parent: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(20, 0))

        ctk.CTkButton(
            row,
            text="Settings…",
            fg_color="#e8eaee",
            hover_color="#dcdee2",
            text_color="#2a2d33",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=36,
            corner_radius=9,
            command=self._handle_open_settings,
        ).pack(side="left")

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

    def _refresh_once(self) -> None:
        state = self._loop.last_pushed_state or self._loop.last_manual_state
        if state is None or state not in STATE_COLORS:
            state = "AVAILABLE"

        # Bead
        img = render_bead(state, 160)
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(160, 160))
        if self._bead_label is not None:
            self._bead_label.configure(image=ctk_img, text="")
            self._bead_label.image = ctk_img  # prevent GC

        # State label
        if self._state_label is not None:
            self._state_label.configure(
                text=_STATE_LABEL.get(state, state),
                text_color=STATE_COLORS.get(state, "#3a3d42"),
            )

        # Transport indicator
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
            text = "Disconnected — plug in the cable or check Wi-Fi"
            color = "#a35a00"
        if self._transport_label is not None:
            self._transport_label.configure(text=text, text_color=color)

        # Stats
        stats = getattr(self._loop, "stats", None)
        for state_key, label in self._stats_labels.items():
            seconds = stats.get(state_key, 0.0) if stats else 0.0
            label.configure(text=_format_duration(seconds))

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
        # Close ourselves first so Tk lets go of the main thread, then
        # the tray re-opens us after the settings window exits.
        if self._root is not None:
            self._cancel_refresh(self._root)
            try:
                self._root.destroy()
            except tk.TclError:
                pass
            self._root = None
        self._on_open_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _darken(hex_color: str, amount: float = 0.12) -> str:
    """Darken a #rrggbb hex by `amount` (0..1)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f"#{r:02x}{g:02x}{b:02x}"
