"""Optional 'Claude mode': the BusyLight shows red while Claude Code is
working and green when it's idle, driven by Claude Code hooks.

A marker file (its presence = mode ON) is the single shared state between
the CLI, the hooks, and the tray/poll loop. Every device write is
best-effort and never raises — a hook must not fail a Claude Code turn.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import _default_config_path
from .serial_client import SerialClient, find_busylight_ports

_WORKING = "BUSY"       # red solid
_IDLE = "AVAILABLE"     # green solid


def flag_path() -> Path:
    return _default_config_path().parent / "claude_mode"


def is_on() -> bool:
    return flag_path().exists()


def _best_effort_set(state: str) -> bool:
    """Set the device state over USB serial. Never raises. Returns True on
    a confirmed set. Iterates candidate ports and takes the first that
    accepts the command (a non-BusyLight adapter rejects it)."""
    try:
        ports = find_busylight_ports()
    except Exception:  # noqa: BLE001
        return False
    for port in ports:
        try:
            SerialClient(port=port).set_state(state)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def enable() -> None:
    p = flag_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("on", encoding="ascii")
    _best_effort_set(_IDLE)


def disable() -> None:
    try:
        flag_path().unlink()
    except FileNotFoundError:
        pass


def set_working() -> None:
    if is_on():
        _best_effort_set(_WORKING)


def set_idle() -> None:
    if is_on():
        _best_effort_set(_IDLE)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sub = args[0] if args else "status"
    if sub == "on":
        enable()
    elif sub == "off":
        disable()
    elif sub == "working":
        set_working()
    elif sub == "idle":
        set_idle()
    elif sub == "status":
        print("on" if is_on() else "off")
    elif sub == "install-hooks":
        from .claude_hooks import install_hooks
        install_hooks()
    elif sub == "uninstall-hooks":
        from .claude_hooks import uninstall_hooks
        uninstall_hooks()
    else:
        print(f"unknown command: {sub}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
