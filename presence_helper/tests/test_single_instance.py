from __future__ import annotations

import sys

import pytest

from busylight_presence.single_instance import SingleInstance


def test_non_windows_always_acquires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    a = SingleInstance("busylight-test-nonwin")
    assert a.acquire() is True
    a.release()


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_second_acquire_is_rejected() -> None:
    name = "Global\\BusyLightPresence_Test_Mutex"
    first = SingleInstance(name)
    second = SingleInstance(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False  # already exists -> not first
    finally:
        first.release()
        second.release()
