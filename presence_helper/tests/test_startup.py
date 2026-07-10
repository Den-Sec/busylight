# presence_helper/tests/test_startup.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from busylight_presence import startup


@pytest.mark.skipif(sys.platform != "win32", reason="HKCU Run key is Windows-only")
def test_enable_disable_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a test-specific value name so we never touch the real entry.
    monkeypatch.setattr(startup, "_VALUE_NAME", "BusyLightPresenceTest")
    try:
        assert startup.is_startup_enabled() is False
        startup.enable_startup()
        assert startup.is_startup_enabled() is True
    finally:
        startup.disable_startup()
    assert startup.is_startup_enabled() is False


@pytest.mark.skipif(sys.platform != "win32", reason="HKCU Run key is Windows-only")
def test_disable_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup, "_VALUE_NAME", "BusyLightPresenceTest")
    startup.disable_startup()  # not present -> no raise
    startup.disable_startup()


def test_ensure_default_startup_noop_when_not_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Not a frozen exe -> ensure_default_startup does nothing and writes
    # no sentinel (dev runs must not register themselves).
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    sentinel = tmp_path / ".startup_configured"
    startup.ensure_default_startup(sentinel)
    assert not sentinel.exists()
