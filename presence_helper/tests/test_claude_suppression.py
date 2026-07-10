from __future__ import annotations

from busylight_presence.tray import _should_drive_from_mic


def test_drives_from_mic_when_normal():
    assert _should_drive_from_mic(paused=False, claude_on=False) is True


def test_no_mic_drive_when_paused():
    assert _should_drive_from_mic(paused=True, claude_on=False) is False


def test_no_mic_drive_in_claude_mode():
    assert _should_drive_from_mic(paused=False, claude_on=True) is False
