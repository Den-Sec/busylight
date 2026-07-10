from __future__ import annotations

from pathlib import Path

from busylight_presence.config import PresenceConfig
from busylight_presence.main import _fallback_config


def test_fallback_config_is_usable(tmp_path: Path) -> None:
    cfg = _fallback_config(tmp_path / "presence.ini")
    assert isinstance(cfg, PresenceConfig)
    # Safe defaults so the tray can launch into Settings.
    assert cfg.host == ""
    assert cfg.pin == ""
    assert cfg.poll_seconds == 2.0
