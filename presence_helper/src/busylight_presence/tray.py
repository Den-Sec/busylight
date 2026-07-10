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
from .startup import enable_startup, disable_startup, is_startup_enabled
from .update_progress_window import UpdateProgressWindow
from .webui_bridge import WebUiBridge
from .webview_window import open_device_webui
from .updater import (
    LatestRelease,
    download_exe,
    fetch_latest_release,
    install_and_restart,
    is_newer,
    wait_for_av_release,
)

log = logging.getLogger("busylight_presence.tray")


# How often the background thread looks for new releases. 1 hour is
# a sane default: short enough that a release pushed an hour ago will
# get picked up, long enough that we're not hammering the GitHub API.
# A first check fires ~3 seconds after launch so a user who downloads
# a slightly-stale exe gets the prompt immediately.
UPDATE_CHECK_INTERVAL_S = 60 * 60


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
        self._pending_firmware_update: Optional[LatestRelease] = None
        self._firmware_update_lock = threading.Lock()
        self._webview_thread: Optional[threading.Thread] = None
        self._webview_open = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        menu = Menu(
            Item(lambda _i: f"BusyLight Presence {__version__}", None,
                 enabled=False),
            Menu.SEPARATOR,
            Item("Open BusyLight", self._open_dashboard, default=True),
            Item(self._firmware_update_label,
                 self._on_firmware_update_click,
                 enabled=lambda _i: self._pending_firmware_update is not None),
            Item("Update firmware via USB…", self._on_firmware_ota_usb),
            Item("Reflash from factory (USB)…", self._on_factory_reflash),
            Item("Factory reset device (clears PIN + Wi-Fi)…",
                 self._on_factory_reset_device),
            Item("Settings…", self._open_settings),
            Item(
                "Start at login",
                self._toggle_startup,
                checked=lambda _i: is_startup_enabled(),
            ),
            Item(
                lambda _i: "Resume" if self._paused else "Pause",
                self._toggle_pause,
            ),
            Menu.SEPARATOR,
            Item(self._update_label, self._on_update_click,
                 enabled=lambda _i: self._pending_update is not None),
            Item("Check for updates now", self._on_manual_check),
            Item("View last update log", self._on_view_update_log),
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
        #
        # Run the WebView on a worker thread so it doesn't block
        # pystray's main-thread message loop — otherwise right-click
        # on the tray icon stops responding while the dashboard is
        # open (both WebView2 and pystray want exclusive ownership
        # of the main thread on Windows).
        if self._webview_open:
            # Already showing; let the OS bring it to front rather
            # than spawning a second window.
            return
        try:
            url = self._bridge.start()
        except Exception as e:  # noqa: BLE001
            log.exception("bridge start failed: %s", e)
            return

        def runner() -> None:
            self._webview_open = True
            try:
                open_device_webui(url)
            except Exception as e:  # noqa: BLE001
                log.exception("webview failed: %s", e)
            finally:
                self._webview_open = False

        self._webview_thread = threading.Thread(
            target=runner, daemon=True, name="busylight-webview",
        )
        self._webview_thread.start()

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

    def _toggle_startup(self, _icon, _item) -> None:
        if is_startup_enabled():
            disable_startup()
        else:
            enable_startup()

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

    def _firmware_update_label(self, _item) -> str:
        with self._firmware_update_lock:
            pending = self._pending_firmware_update
        if pending is None:
            return "Device firmware up to date"
        return f"Install device firmware {pending.tag}…"

    def _on_firmware_update_click(self, _icon, _item) -> None:
        # Reuse the existing USB-OTA flow. It will auto-fall-back to
        # factory reflash on signature_invalid (see below).
        threading.Thread(
            target=self._firmware_ota_via_usb, daemon=True,
        ).start()

    def _update_loop(self) -> None:
        # Short startup delay so the GitHub call doesn't fight tray
        # init for CPU, but small enough that someone who downloads a
        # stale exe sees the "update available" prompt right away.
        if self._stop_event.wait(3.0):
            return
        while not self._stop_event.is_set():
            self._check_for_update()
            self._check_firmware_update()
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

    def _on_view_update_log(self, _icon, _item) -> None:
        """Open `%TEMP%\\busylight-update.log` in the default editor.

        Useful when the self-update appears to have done nothing —
        the log lines reveal whether `move /y` failed (and why),
        whether the new exe got `start`-ed, etc.
        """
        import os
        import subprocess
        import tempfile
        log_path = os.path.join(tempfile.gettempdir(),
                                "busylight-update.log")
        if not os.path.exists(log_path):
            self._notify(
                "BusyLight update",
                "No update log yet — try the install once first.",
            )
            return
        try:
            os.startfile(log_path)
        except Exception as e:  # noqa: BLE001
            log.warning("could not open update log: %s", e)
            try:
                subprocess.Popen(["notepad.exe", log_path])
            except Exception:  # noqa: BLE001
                pass

    def _on_manual_check(self, _icon, _item) -> None:
        def _both() -> None:
            self._check_for_update(notify_no_update=True)
            self._check_firmware_update(notify_no_update=True)
        threading.Thread(target=_both, daemon=True).start()

    def _check_firmware_update(self, *,
                               notify_no_update: bool = False) -> None:
        """Ask the device its current firmware version and compare it
        against the latest GitHub release. If the device is behind, we
        notify and enable the dynamic menu item so the user can install
        with one click."""
        from .serial_client import (
            SerialClient,
            SerialProtocolError,
            SerialUnavailable,
            find_busylight_ports,
        )

        ports = find_busylight_ports()
        if not ports:
            # No device on USB — silently skip. The user gets prompted
            # again on the next periodic check.
            return
        try:
            info = SerialClient(port=ports[0]).get_info()
        except (SerialUnavailable, SerialProtocolError) as e:
            log.debug("firmware version probe failed: %s", e)
            return
        current_fw = info.get("fw") or ""

        try:
            latest = fetch_latest_release()
        except Exception as e:  # noqa: BLE001
            log.warning("release check raised: %s", e)
            return
        if latest is None or latest.firmware_asset is None:
            return

        if is_newer(latest.version, current_fw):
            with self._firmware_update_lock:
                self._pending_firmware_update = latest
            log.info("firmware update available: %s -> %s",
                     current_fw, latest.tag)
            self._notify(
                "BusyLight firmware update",
                f"Device is on {current_fw}, {latest.tag} is available. "
                "Click the tray icon to install over USB.",
            )
        else:
            with self._firmware_update_lock:
                self._pending_firmware_update = None
            if notify_no_update:
                self._notify(
                    "BusyLight firmware",
                    f"Device firmware is up to date ({current_fw}).",
                )

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
        # Modal progress dialog so the user sees what's going on
        # instead of just a brief balloon and a silent UAC prompt.
        progress = UpdateProgressWindow(
            title=f"Installing BusyLight {release.tag}"
        )
        progress.start()
        progress.set_message(
            f"Downloading {release.tag} from GitHub…"
        )
        try:
            def cb(written: int, total: int) -> None:
                if total > 0:
                    progress.set_progress(written / total)
                    mb_done = written / (1024 * 1024)
                    mb_tot = total / (1024 * 1024)
                    progress.set_message(
                        f"Downloading {release.tag} from GitHub…"
                        f"\n{mb_done:.1f} MB of {mb_tot:.1f} MB"
                    )
                else:
                    progress.set_indeterminate()
            new_exe = download_exe(release, progress_cb=cb)
        except Exception as e:  # noqa: BLE001
            log.exception("update download failed: %s", e)
            progress.set_message(f"Download failed: {e}")
            progress.set_progress(0.0)
            import time
            time.sleep(3.0)
            progress.close()
            self._notify("Update failed", str(e))
            return

        try:
            progress.set_progress(1.0)
            # Wait for AV to release the lock on the downloaded exe
            # before we hand off to the .bat. On Defender / ESET this
            # can take up to ~90 s on a 30 MB binary; without this
            # wait the .bat's `move /y` keeps hitting "Access is
            # denied" and the update silently rolls back to the old
            # version.
            progress.set_indeterminate()
            progress.set_message(
                "Antivirus is scanning the new file… "
                "(this can take up to ~90 seconds)"
            )
            def _av_cb(elapsed: float, total: float) -> None:
                progress.set_message(
                    "Antivirus is scanning the new file…\n"
                    f"{int(elapsed)}s of up to {int(total)}s"
                )
            wait_for_av_release(new_exe, timeout_s=90.0, progress_cb=_av_cb)
            progress.set_progress(1.0)
            progress.set_message(
                "Antivirus scan complete. Restarting BusyLight…\n"
                "If Windows asks for permission, click Yes."
            )
            import time
            time.sleep(1.5)
            progress.close()
            # Tell every cooperating thread we're going away so they
            # release their handles + ports. Then stop the tray icon
            # cleanly. The .bat already retries the move for 30 s in
            # case Windows holds the exe lock longer than expected.
            self._stop_event.set()
            try:
                self._bridge.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                if self._icon is not None:
                    self._icon.stop()
            except Exception:  # noqa: BLE001
                pass
            install_and_restart(new_exe)  # never returns
        except SystemExit:
            raise
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

        # 4. Push over serial. The presence loop AND the WebView
        #    bridge can both open the COM port — pause them both so
        #    they don't race the OTA reader for the handle.
        self._notify(
            "BusyLight update",
            "Flashing device over USB — please don't unplug the cable…",
        )
        self._paused = True
        WebUiBridge.set_suspended(True)
        try:
            sc = SerialClient(port=ports[0])
            sc.update_firmware(bin_path, sig_path)
        except (SerialUnavailable, SerialProtocolError) as e:
            msg = str(e)
            # signature_invalid means the device's embedded public key
            # doesn't match the key we signed the release with — OTA
            # cannot succeed without re-flashing. Fall back to the
            # factory reflash path automatically so the user doesn't
            # have to pick a different menu item.
            if "signature_invalid" in msg:
                self._notify(
                    "BusyLight update",
                    "Signature mismatch — falling back to factory "
                    "reflash automatically…",
                )
                self._paused = False
                WebUiBridge.set_suspended(False)
                self._factory_reflash()
                return
            self._notify("BusyLight update", f"Firmware flash failed: {msg}")
            return
        except Exception as e:  # noqa: BLE001
            self._notify("BusyLight update", f"Unexpected error: {e}")
            return
        finally:
            self._paused = False
            WebUiBridge.set_suspended(False)

        # 5. Device reboots into the new firmware; the tray reconnects
        #    automatically on the next poll tick.
        with self._firmware_update_lock:
            self._pending_firmware_update = None
        self._notify(
            "BusyLight update",
            f"Device updated to {release.tag}. Reconnecting…",
        )

    # ------------------------------------------------------------------
    # Factory reflash (bypasses the OTA signature check)
    # ------------------------------------------------------------------
    def _on_factory_reflash(self, _icon, _item) -> None:
        threading.Thread(
            target=self._factory_reflash, daemon=True
        ).start()

    def _on_factory_reset_device(self, _icon, _item) -> None:
        """Wipe device NVS (PIN, saved Wi-Fi, schedule) and reboot.
        After this the device boots with PIN = "1234" and no saved
        networks — useful when the PIN gets out of sync between the
        bridge and the device firmware."""
        from .serial_client import (
            SerialClient, SerialProtocolError, SerialUnavailable,
            find_busylight_ports,
        )

        def run() -> None:
            ports = find_busylight_ports()
            if not ports:
                self._notify(
                    "BusyLight reset",
                    "No USB device — plug in the cable and try again.",
                )
                return
            try:
                SerialClient(port=ports[0]).factory_reset()
            except (SerialUnavailable, SerialProtocolError) as e:
                self._notify(
                    "BusyLight reset",
                    f"Factory reset failed: {e}",
                )
                return
            self._notify(
                "BusyLight reset",
                "Device wiped. PIN is now 1234, no saved Wi-Fi. "
                "Reconnecting…",
            )

        threading.Thread(target=run, daemon=True).start()

    def _factory_reflash(self) -> None:
        """Re-flash the combined firmware image (bootloader + partitions
        + app) over USB using esptool. Bypasses the running app's OTA
        signature check, so this is the escape hatch when the device's
        embedded public key doesn't match the one used to sign our
        release `.bin`s.

        Preserves NVS (PIN, saved Wi-Fi, schedule) because the
        partition table layout is identical and esptool only writes
        the regions we tell it to — we deliberately do NOT pass
        `erase_all`.
        """
        import tempfile
        import urllib.request
        from pathlib import Path

        from .serial_client import find_busylight_ports

        ports = find_busylight_ports()
        if not ports:
            self._notify(
                "BusyLight reflash",
                "No USB device — plug in the cable and try again.",
            )
            return
        port = ports[0]

        try:
            release = fetch_latest_release()
        except Exception as e:  # noqa: BLE001
            self._notify("BusyLight reflash", f"GitHub lookup failed: {e}")
            return
        if release is None:
            self._notify(
                "BusyLight reflash",
                "Couldn't reach GitHub — check your internet connection.",
            )
            return

        # The release has firmware.bin (single app image, signed) but
        # for a factory reflash we need the combined image. Pick the
        # asset whose name contains "factory".
        factory_asset = None
        for a in [release.firmware_asset, release.signature_asset]:
            pass
        # Look in the raw release JSON because LatestRelease only
        # exposes the OTA pair.
        try:
            import json
            req = urllib.request.Request(
                "https://api.github.com/repos/Den-Sec/busylight/releases/latest",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"busylight-presence/{__version__}",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            for a in data.get("assets") or []:
                name = (a.get("name") or "").lower()
                if name.endswith(".bin") and "factory" in name:
                    factory_asset = {
                        "name": a["name"],
                        "url": a["browser_download_url"],
                    }
                    break
        except Exception as e:  # noqa: BLE001
            self._notify(
                "BusyLight reflash",
                f"Couldn't read release assets: {e}",
            )
            return

        if factory_asset is None:
            self._notify(
                "BusyLight reflash",
                f"Release {release.tag} has no `.factory.bin` asset.",
            )
            return

        self._notify(
            "BusyLight reflash",
            f"Downloading {factory_asset['name']}…",
        )
        try:
            dest = Path(tempfile.gettempdir()) / "busylight-update"
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / factory_asset["name"]
            req = urllib.request.Request(
                factory_asset["url"],
                headers={"User-Agent": f"busylight-presence/{__version__}"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                target.write_bytes(resp.read())
        except Exception as e:  # noqa: BLE001
            self._notify("BusyLight reflash", f"Download failed: {e}")
            return

        # esptool needs exclusive ownership of the COM port; pause
        # the presence polling loop so it doesn't compete for the cable.
        self._notify(
            "BusyLight reflash",
            "Re-flashing device — don't unplug the cable…",
        )
        self._paused = True
        WebUiBridge.set_suspended(True)
        try:
            import esptool
            args = [
                "--chip", "esp32c6",
                "--port", port,
                "--baud", "460800",
                "--before", "default_reset",
                "--after", "hard_reset",
                "write_flash",
                "--flash_mode", "dio",
                "--flash_freq", "80m",
                "--flash_size", "4MB",
                "0x0", str(target),
            ]
            esptool.main(args)
        except SystemExit as e:
            if getattr(e, "code", 0):
                self._notify(
                    "BusyLight reflash",
                    f"esptool failed (exit {e.code}).",
                )
                self._paused = False
                WebUiBridge.set_suspended(False)
                return
        except Exception as e:  # noqa: BLE001
            self._notify(
                "BusyLight reflash",
                f"Reflash failed: {e}",
            )
            self._paused = False
            WebUiBridge.set_suspended(False)
            return

        self._paused = False
        WebUiBridge.set_suspended(False)
        with self._firmware_update_lock:
            self._pending_firmware_update = None
        self._notify(
            "BusyLight reflash",
            f"Device re-flashed to {release.tag}. Reconnecting…",
        )
