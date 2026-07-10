"""Per-user 'start at login' via the HKCU Run key.

Windows-only and admin-free: HKCU (not HKLM) needs no elevation, which
is exactly why the presence exe must NOT ship a requireAdministrator
manifest — Windows silently skips elevated apps from the Run key at
logon.
"""

from __future__ import annotations

import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "BusyLightPresence"


def _target_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # Dev runs go through the module so the venv stays in scope.
    return f'"{sys.executable}" -m busylight_presence'


def enable_startup() -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(
            key, _VALUE_NAME, 0, winreg.REG_SZ, _target_command()
        )


def disable_startup() -> None:
    if sys.platform != "win32":
        return
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        pass


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE
        ) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def ensure_default_startup(sentinel: Path) -> None:
    """Enable start-at-login once, on the first frozen run (default-on).

    Respects a later user opt-out: the sentinel file means "we've already
    made the default choice", so we never re-enable after the user
    disables it from the tray.
    """
    if not getattr(sys, "frozen", False):
        return
    if sentinel.exists():
        return
    try:
        if not is_startup_enabled():
            enable_startup()
    finally:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("1", encoding="ascii")
