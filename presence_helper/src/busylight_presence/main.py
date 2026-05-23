"""Entry point for the BusyLight Presence helper.

Default mode runs as a tray-icon app (see `tray.py`). Pass `--no-tray`
to run the original console-only loop, handy for CI / cron / first-time
debugging on a host where Tk or pystray won't import.

Polling cadence:
  - mic_active == True  -> push IN_CALL to the device
  - mic_active == False -> restore the last "manual" state the user
                           set via the web UI (re-learned whenever the
                           device's state changes outside of the helper)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from . import __version__
from .client import (
    BusyLightAuthError,
    BusyLightClient,
    BusyLightNetworkError,
)
from .config import PresenceConfig, load_config
from .mic_monitor import microphone_in_use, supported_platform

log = logging.getLogger("busylight_presence")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="busylight-presence",
        description=(
            "Watch the microphone and switch the BusyLight to IN_CALL "
            "while any app is capturing audio."
        ),
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a presence.ini config file. Defaults to per-OS user dir.",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Read mic state once, push it, and exit. Useful for cron / testing.",
    )
    p.add_argument(
        "--no-tray",
        action="store_true",
        help="Run as a console loop instead of a tray app.",
    )
    p.add_argument(
        "--install-startup",
        action="store_true",
        help=(
            "Register the helper to launch at Windows login (writes a "
            "Run key under HKCU). Exits immediately after."
        ),
    )
    p.add_argument(
        "--uninstall-startup",
        action="store_true",
        help="Remove the auto-start registry entry, then exit.",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true", help="Debug logging."
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"busylight-presence {__version__}",
    )
    return p


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Polling loop (shared by both console + tray front-ends)
# ---------------------------------------------------------------------------

class PresenceLoop:
    """Stateless apart from the manual-state baseline; safe to drive from
    a console while() or a worker thread under pystray."""

    def __init__(self, cfg: PresenceConfig, client: BusyLightClient) -> None:
        self.cfg = cfg
        self.client = client
        self.running = True

        self.last_manual_state: str = cfg.default_state
        self.last_pushed_state: str | None = None
        self.last_mic_in_use: bool | None = None

    def stop(self, *_args) -> None:  # noqa: ANN001
        log.info("shutting down")
        self.running = False

    def update_config(self, cfg: PresenceConfig) -> None:
        """Apply a new config (host or PIN may have changed)."""
        if cfg.host != self.cfg.host or cfg.pin != self.cfg.pin:
            self.client = BusyLightClient(host=cfg.host, pin=cfg.pin)
            try:
                self.client.login()
            except (BusyLightAuthError, BusyLightNetworkError) as e:
                log.warning("re-login after config change failed: %s", e)
        self.cfg = cfg

    def tick(self) -> None:
        usage = microphone_in_use()
        try:
            current = self.client.get_state()
        except BusyLightNetworkError as e:
            log.warning("get_state failed: %s", e)
            current = None
        except BusyLightAuthError as e:
            log.warning("auth lost: %s", e)
            try:
                self.client.login()
            except (BusyLightAuthError, BusyLightNetworkError) as exc:
                log.error("re-login failed: %s", exc)
            return

        if current and current != "IN_CALL":
            if self.last_pushed_state != current:
                self.last_manual_state = current
                log.debug("learnt manual state -> %s", current)

        desired = "IN_CALL" if usage.in_use else self.last_manual_state

        if current == desired:
            self.last_pushed_state = desired
            self._log_transition(usage)
            return

        try:
            self.client.set_state(desired)
            self.last_pushed_state = desired
            self._log_transition(usage, set_to=desired)
        except BusyLightAuthError as e:
            log.warning("auth error while setting state: %s", e)
        except BusyLightNetworkError as e:
            log.warning("network error while setting state: %s", e)

    def _log_transition(self, usage, *, set_to: str | None = None) -> None:
        if usage.in_use == self.last_mic_in_use and set_to is None:
            return
        self.last_mic_in_use = usage.in_use
        if set_to:
            label = "→ %s" % set_to
        else:
            label = "(no change)"
        apps = ", ".join(usage.apps) if usage.apps else "—"
        log.info(
            "mic %s  apps=%s  %s",
            "ACTIVE" if usage.in_use else "idle",
            apps,
            label,
        )


# ---------------------------------------------------------------------------
# Auto-start install / uninstall
# ---------------------------------------------------------------------------

def _registry_run_path() -> str:
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


def _registry_value_name() -> str:
    return "BusyLightPresence"


def _install_startup() -> int:
    if sys.platform != "win32":
        print("--install-startup is Windows-only.", file=sys.stderr)
        return 2
    import winreg

    if getattr(sys, "frozen", False):
        target = f'"{sys.executable}"'
    else:
        # Run via "python -m busylight_presence" so the venv stays in scope.
        py = sys.executable
        target = f'"{py}" -m busylight_presence'

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _registry_run_path(),
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(
            key, _registry_value_name(), 0, winreg.REG_SZ, target
        )
    print(f"Registered to launch at login: {target}")
    return 0


def _uninstall_startup() -> int:
    if sys.platform != "win32":
        print("--uninstall-startup is Windows-only.", file=sys.stderr)
        return 2
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _registry_run_path(),
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _registry_value_name())
        print("Removed login auto-start entry.")
    except FileNotFoundError:
        print("Auto-start entry was not present; nothing to do.")
    return 0


# ---------------------------------------------------------------------------
# Front-ends
# ---------------------------------------------------------------------------

def _run_console(loop: PresenceLoop) -> int:
    signal.signal(signal.SIGINT, loop.stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, loop.stop)
    log.info(
        "watching %s every %.1fs (baseline state: %s)",
        loop.cfg.host,
        loop.cfg.poll_seconds,
        loop.last_manual_state,
    )
    while loop.running:
        try:
            loop.tick()
        except Exception as e:  # noqa: BLE001
            log.exception("unhandled error in tick: %s", e)
        time.sleep(loop.cfg.poll_seconds)
    return 0


def _run_tray(loop: PresenceLoop) -> int:
    try:
        from .tray import TrayApp
    except ImportError as e:
        log.error(
            "tray dependencies missing (%s) — falling back to console.", e
        )
        return _run_console(loop)

    def on_settings_saved(cfg: PresenceConfig) -> None:
        loop.update_config(cfg)

    tray = TrayApp(loop, on_settings_saved=on_settings_saved)
    tray.run()
    return 0


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _setup_logging(args.verbose)

    if args.install_startup:
        return _install_startup()
    if args.uninstall_startup:
        return _uninstall_startup()

    if not supported_platform():
        log.warning(
            "presence detection is currently Windows-only; on other "
            "platforms the helper will not flip the light."
        )

    try:
        cfg = load_config(args.config)
        cfg.ensure_valid()
    except (FileNotFoundError, ValueError) as e:
        log.error("config: %s", e)
        log.error(
            "Open the tray icon → Settings, or create the config file "
            "manually. Example:\n  [busylight]\n  host = busylight-XXXX.local"
            "\n  pin  = 1234"
        )
        # If running in tray mode and config is missing/invalid, still launch
        # the tray so the user can open Settings and configure it.
        if not args.no_tray:
            # Build a stub loop with no client and let the tray app open
            # the settings window.
            stub_client = BusyLightClient(host=cfg.host or "x", pin=cfg.pin or "0000")
            loop = PresenceLoop(cfg, stub_client)
            return _run_tray(loop)
        return 2

    client = BusyLightClient(host=cfg.host, pin=cfg.pin)
    try:
        client.login()
    except BusyLightAuthError as e:
        log.error("login failed: %s", e)
        if not args.no_tray:
            loop = PresenceLoop(cfg, client)
            return _run_tray(loop)
        return 3
    except BusyLightNetworkError as e:
        log.error("cannot reach BusyLight at %s: %s", cfg.host, e)
        if not args.no_tray:
            loop = PresenceLoop(cfg, client)
            return _run_tray(loop)
        return 4

    loop = PresenceLoop(cfg, client)

    try:
        current = client.get_state()
        if current and current != "IN_CALL":
            loop.last_manual_state = current
            loop.last_pushed_state = current
    except (BusyLightAuthError, BusyLightNetworkError):
        pass

    if args.once:
        loop.tick()
        return 0

    if args.no_tray:
        return _run_console(loop)
    return _run_tray(loop)


if __name__ == "__main__":
    sys.exit(main())
