from __future__ import annotations

import sys

import pytest

from busylight_presence.main import main
from busylight_presence.single_instance import SingleInstance


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_uninstall_startup_flag_runs_even_when_instance_is_running(monkeypatch) -> None:
    # Hold the single-instance mutex to simulate an already-running app.
    guard = SingleInstance()
    assert guard.acquire() is True
    called: list[bool] = []
    monkeypatch.setattr(
        "busylight_presence.startup.disable_startup", lambda: called.append(True)
    )
    try:
        rc = main(["--uninstall-startup"])
    finally:
        guard.release()
    # The one-shot admin flag must still run (not be blocked by the guard).
    assert rc == 0
    assert called == [True]
