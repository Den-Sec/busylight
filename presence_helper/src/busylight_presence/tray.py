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
from typing import Callable, Optional

import pystray
from pystray import MenuItem as Item, Menu

from . import __version__
from .icons import status_icon
from .settings_window import SettingsWindow
from .webui_bridge import WebUiBridge
from .webview_window import open_device_webui
from .updater import (
    LatestRelease,
    download_exe,
    fetch_latest_release,
    install_and_restart,
    is_newer,
)

log = logging.getLogger("busylight_presence.tray")


# How often the background thread looks for new releases. 4h is long
# enough to be invisible to the user, short enough that a release
# pushed in the morning will be picked up by evening on a workstation
# that's been on all day.
UPDATE_CHECK_INTERVAL_S = 4 * 60 * 60


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
        self._bridge = WebUiBridge()
        self._tick_thread: threading.Thread | None = None
        self._update_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._current_status_name = "disconnected"
        self._current_via_usb = False
        self._pending_update: Optional[LatestRelease] = None
        self._update_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        menu = Menu(
            Item(lambda _i: f"BusyLight Presence {__version__}", None,
                 enabled=False),
            Menu.SEPARATOR,
            Item("Open BusyLight", self._open_dashboard, default=True),
            Item("Update firmware via USB…", self._on_firmware_ota_usb),
            Item("Settings…", self._open_settings),
            Item(
                lambda _i: "Resume" if self._paused else "Pause",
                self._toggle_pause,
            ),
            Menu.SEPARATOR,
            Item(self._update_label, self._on_update_click,
                 enabled=lambda _i: self._pending_update is not None),
            Item("Check for updates now", self._on_manual_check),
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

        # Background release checker — sleeps a bit before the first
        # probe so the helper doesn't hit GitHub during startup race.
        self._update_thread = threading.Thread(
            target=self._update_loop, daemon=True
        )
        self._update_thread.start()

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

        via_usb = getattr(self._loop.client, "current_mode", None) == "serial"

        if (
            target != self._current_status_name
            or via_usb != self._current_via_usb
        ):
            self._current_status_name = target
            self._current_via_usb = via_usb
            try:
                self._icon.icon = status_icon(target, via_usb=via_usb)
                self._icon.title = self._title_for(target, via_usb=via_usb)
            except Exception:  # noqa: BLE001
                pass

    def _title_for(self, status: str, via_usb: bool = False) -> str:
        mapping = {
            "idle": "BusyLight: available",
            "in_call": "BusyLight: in a call",
            "away": "BusyLight: away",
            "warning": "BusyLight Presence: paused",
            "disconnected":
                "BusyLight Presence: cannot reach the device",
        }
        title = mapping.get(status, "BusyLight Presence")
        if via_usb and status != "disconnected" and status != "warning":
            title = f"{title} (via USB)"
        return title

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

    def _open_dashboard(self, _icon, _item):
        # The "dashboard" is now the firmware's own web UI, served by
        # the local bridge over USB serial. Same exact look and feel
        # as the device's HTTP UI, but doesn't require Wi-Fi.
        try:
            url = self._bridge.start()
            open_device_webui(url)
        except Exception as e:  # noqa: BLE001
            log.exception("web UI failed: %s", e)

    def _open_settings_from_dashboard(self) -> None:
        # Dashboard closes itself before calling us, so we can just
        # open settings normally. After settings closes we don't
        # auto-reopen the dashboard — that would feel like a loop;
        # the user clicks the tray again if they want it back.
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
        try:
            self._bridge.stop()
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

    # ------------------------------------------------------------------
    # Auto-update
    # ------------------------------------------------------------------
    def _update_label(self, _item) -> str:
        with self._update_lock:
            pending = self._pending_update
        if pending is None:
            return "Up to date"
        return f"Install update {pending.tag}…"

    def _update_loop(self) -> None:
        # Small startup delay so we don't fire a network call during
        # tray init (some users still see SmartScreen at this point).
        if self._stop_event.wait(20.0):
            return
        while not self._stop_event.is_set():
            self._check_for_update()
            # Interruptible sleep — Event.wait returns True if stopped.
            if self._stop_event.wait(UPDATE_CHECK_INTERVAL_S):
                return

    def _check_for_update(self, *, notify_no_update: bool = False) -> None:
        try:
            latest = fetch_latest_release()
        except Exception as e:  # noqa: BLE001
            log.warning("release check raised: %s", e)
            return
        if latest is None:
            return
        if is_newer(latest.version, __version__):
            with self._update_lock:
                self._pending_update = latest
            log.info("update available: %s (current %s)",
                     latest.tag, __version__)
            self._notify(
                "BusyLight update available",
                f"{latest.tag} is ready — click the tray icon to install.",
            )
        else:
            with self._update_lock:
                self._pending_update = None
            if notify_no_update:
                self._notify(
                    "BusyLight Presence",
                    f"You're on the latest version ({__version__}).",
                )

    def _on_manual_check(self, _icon, _item) -> None:
        threading.Thread(
            target=self._check_for_update,
            kwargs={"notify_no_update": True},
            daemon=True,
        ).start()

    def _on_update_click(self, _icon, _item) -> None:
        with self._update_lock:
            release = self._pending_update
        if release is None:
            return
        # Run in a thread so the tray stays responsive while downloading.
        threading.Thread(
            target=self._install_update, args=(release,), daemon=True
        ).start()

    def _install_update(self, release: LatestRelease) -> None:
        try:
            self._notify(
                "Downloading BusyLight update",
                f"Fetching {release.tag} from GitHub…",
            )
            new_exe = download_exe(release)
        except Exception as e:  # noqa: BLE001
            log.exception("update download failed: %s", e)
            self._notify("Update failed", str(e))
            return
        try:
            self._stop_event.set()  # let worker threads wind down
            install_and_restart(new_exe)
        except SystemExit:
            raise  # install_and_restart exits the process by design
        except Exception as e:  # noqa: BLE001
            log.exception("update install failed: %s", e)
            self._notify("Update failed", str(e))

    def _notify(self, title: str, message: str) -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title=title)
        except Exception as e:  # noqa: BLE001
            log.debug("notify failed: %s", e)

    # ------------------------------------------------------------------
    # Firmware OTA over USB
    # ------------------------------------------------------------------
    def _on_firmware_ota_usb(self, _icon, _item) -> None:
        threading.Thread(
            target=self._firmware_ota_via_usb,
            daemon=True,
        ).start()

    def _firmware_ota_via_usb(self) -> None:
        """Download the latest signed firmware from GitHub and flash it
        to the device over the USB cable. No Wi-Fi required.
        """
        import tempfile
        import urllib.request
        from pathlib import Path

        from .serial_client import (
            SerialClient,
            SerialProtocolError,
            SerialUnavailable,
            find_busylight_ports,
        )

        # 1. Find the device.
        ports = find_busylight_ports()
        if not ports:
            self._notify(
                "BusyLight update",
                "No USB device — plug in the cable and try again.",
            )
            return

        # 2. Find the latest release on GitHub.
        try:
            release = fetch_latest_release()
        except Exception as e:  # noqa: BLE001
            self._notify("BusyLight update", f"GitHub lookup failed: {e}")
            return
        if release is None:
            self._notify(
                "BusyLight update",
                "Couldn't reach GitHub — check your internet connection.",
            )
            return
        if release.firmware_asset is None or release.signature_asset is None:
            self._notify(
                "BusyLight update",
                f"Release {release.tag} has no firmware asset.",
            )
            return

        # 3. Download .bin + .sig to %TEMP%.
        self._notify(
            "BusyLight update",
            f"Downloading firmware {release.tag}…",
        )
        try:
            dest = Path(tempfile.gettempdir()) / "busylight-update"
            dest.mkdir(parents=True, exist_ok=True)
            bin_path = dest / release.firmware_asset.name
            sig_path = dest / release.signature_asset.name
            for asset, target in (
                (release.firmware_asset, bin_path),
                (release.signature_asset, sig_path),
            ):
                req = urllib.request.Request(
                    asset.url,
                    headers={"User-Agent": f"busylight-presence/{__version__}"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    target.write_bytes(resp.read())
        except Exception as e:  # noqa: BLE001
            self._notify("BusyLight update", f"Download failed: {e}")
            return

        # 4. Push over serial. The presence loop talks to the device
        #    too — pause it so we don't fight for the COM port.
        self._notify(
            "BusyLight update",
            "Flashing device over USB — please don't unplug the cable…",
        )
        self._paused = True
        try:
            sc = SerialClient(port=ports[0])
            sc.update_firmware(bin_path, sig_path)
        except (SerialUnavailable, SerialProtocolError) as e:
            self._notify("BusyLight update", f"Firmware flash failed: {e}")
            return
        except Exception as e:  # noqa: BLE001
            self._notify("BusyLight update", f"Unexpected error: {e}")
            return
        finally:
            self._paused = False

        # 5. Device reboots into the new firmware; the tray reconnects
        #    automatically on the next poll tick.
        self._notify(
            "BusyLight update",
            f"Device updated to {release.tag}. Reconnecting…",
        )
