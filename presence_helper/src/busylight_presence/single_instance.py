"""Single-instance guard using a Windows named mutex.

A login-autostart copy plus a manual double-click must not run two
trays / mic loops / updaters at once (they would also race over the one
exclusive COM handle). On non-Windows this is a no-op (the desktop app
is Windows-only anyway).
"""

from __future__ import annotations

import sys

_DEFAULT_NAME = "Global\\BusyLightPresence_SingleInstance"


class SingleInstance:
    def __init__(self, name: str = _DEFAULT_NAME) -> None:
        self._name = name
        self._handle = None
        self._already_running = False

    def acquire(self) -> bool:
        """Return True if we are the first instance, False otherwise."""
        if sys.platform != "win32":
            return True
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR
        ]
        ERROR_ALREADY_EXISTS = 183

        self._handle = kernel32.CreateMutexW(None, True, self._name)
        self._already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        return not self._already_running

    def release(self) -> None:
        if self._handle is not None and sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None
