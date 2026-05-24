"""Tray-icon front-end for the presence helper.

Wraps a `PresenceLoop` (from main.py) in a pystray application:

  - icon colour reflects the current state (green=idle,
    red=in_call, gray=disconnected, orange=warning).
  - left-click / "Settings…" opens the Tkinter config panel.
  - "Pause" / "Resume" suspends the polling loop without quitting.
  - "Open BusyLight" launches the device's web UI in the browser.
  - "Quit" stops cleanly.

The polling loop runs on a background thread; pystray owns the main
thread because it has to pump native Windows messages there. The
Tkinter settings window is opened from a pystray menu callback and
runs its own blocking `mainloop()` until the user closes it - Tk
must own the main thread on macOS/Linux, and on Windows pystray
invokes menu callbacks on the main thread anyway.
"""

from __future__ import annotations

import logging
import threading
import time
import webbrowser
from typing import Callable

import pystray
from pystray import MenuItem as Item, Menu

from .icons import status_icon
from .settings_window import SettingsWindow

log = logging.getLogger("busylight_presence.tray")


class TrayApp:
    """A tiny presence-aware tray icon."""

    def __init__(
        self,
        loop,
        on_settings_saved: Callable[..., None],
    ) -> None:
        self._loop = loop
        self._on_settings_saved = on_settings_saved
        self._icon: pystray.Icon | None = None
        self._paused = False
        self._settings = SettingsWindow(loop.cfg, on_save=self._handle_save)
        self._tick_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._current_status_name = "disconnected"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        menu = Menu(
            Item("BusyLight Presence", None, enabled=False),
            Menu.SEPARATOR,
            Item("Open BusyLight…", self._open_busylight),
            Item("Settings…", self._open_settings, default=True),
            Item(
                lambda _i: "Resume" if self._paused else "Pause",
                self._toggle_pause,
            ),
            Menu.SEPARATOR,
            Item("Quit", self._quit),
        )

        self._icon = pystray.Icon(
            name="busylight-presence",
            icon=status_icon("disconnected"),
            title="BusyLight Presence",
            menu=menu,
        )

        # Start polling on a worker thread.
        self._tick_thread = threading.Thread(
            target=self._poll_forever, daemon=True
        )
        self._tick_thread.start()

        # pystray.run() blocks until the icon is stopped from a menu.
        self._icon.run()

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------
    def _poll_forever(self) -> None:
        # Important: do NOT touch Tk from this worker thread. Tkinter
        # is not thread-safe and the settings window runs on the main
        # thread via its own mainloop when opened.
        while not self._stop_event.is_set():
            if not self._paused:
                try:
                    self._loop.tick()
                except Exception as e:  # noqa: BLE001
                    log.exception("tick error: %s", e)
            self._refresh_icon()
            time.sleep(self._loop.cfg.poll_seconds)

    def _refresh_icon(self) -> None:
        if self._icon is None:
            return
        if self._paused:
            target = "warning"
        elif self._loop.last_pushed_state == "IN_CALL":
            target = "in_call"
        elif self._loop.last_pushed_state == "AWAY":
            target = "away"
        elif self._loop.last_pushed_state is None:
            target = "disconnected"
        else:
            target = "idle"

        if target != self._current_status_name:
            self._current_status_name = target
            try:
                self._icon.icon = status_icon(target)
                self._icon.title = self._title_for(target)
            except Exception:  # noqa: BLE001
                pass

    def _title_for(self, status: str) -> str:
        mapping = {
            "idle": "BusyLight: available",
            "in_call": "BusyLight: in a call",
            "away": "BusyLight: away",
            "warning": "BusyLight Presence: paused",
            "disconnected":
                "BusyLight Presence: cannot reach the device",
        }
        return mapping.get(status, "BusyLight Presence")

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------
    def _open_busylight(self, _icon, _item):
        host = self._loop.cfg.host
        if host:
            webbrowser.open(f"http://{host}")

    def _open_settings(self, _icon, _item):
        # Tk only likes the main thread on Linux/macOS, but on Windows
        # opening from any thread works fine. pystray calls menu items
        # from its own thread.
        try:
            self._settings.open()
        except Exception as e:  # noqa: BLE001
            log.exception("settings window failed: %s", e)

    def _toggle_pause(self, _icon, _item):
        self._paused = not self._paused
        self._refresh_icon()

    def _quit(self, _icon, _item):
        self._stop_event.set()
        try:
            self._settings.close()
        except Exception:  # noqa: BLE001
            pass
        if self._icon is not None:
            self._icon.stop()

    # ------------------------------------------------------------------
    # Apply settings without restart
    # ------------------------------------------------------------------
    def _handle_save(self, cfg) -> None:
        self._on_settings_saved(cfg)
        self._refresh_icon()
