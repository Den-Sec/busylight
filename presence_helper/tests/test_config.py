"""Tests for the INI / env-var config loader."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from busylight_presence.config import (
    PresenceConfig,
    _default_config_path,
    load_config,
)


def test_default_config_path_under_appdata_on_windows() -> None:
    path = _default_config_path()
    assert path.name == "presence.ini"
    assert path.parent.name in {"BusyLight", "busylight"}


def test_load_config_reads_ini(tmp_path: Path) -> None:
    cfg_path = tmp_path / "presence.ini"
    cfg_path.write_text(
        "[busylight]\n"
        "host = busylight-aabb.local\n"
        "pin = 4242\n"
        "poll_seconds = 1.5\n"
        "default_state = BUSY\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.host == "busylight-aabb.local"
    assert cfg.pin == "4242"
    assert cfg.poll_seconds == 1.5
    assert cfg.default_state == "BUSY"


def test_env_vars_override_ini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "presence.ini"
    cfg_path.write_text(
        "[busylight]\nhost = file-host.local\npin = 1234\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BUSYLIGHT_HOST", "env-host.local")
    monkeypatch.setenv("BUSYLIGHT_PIN", "9999")
    cfg = load_config(cfg_path)
    assert cfg.host == "env-host.local"
    assert cfg.pin == "9999"


def test_ensure_valid_rejects_missing_host() -> None:
    with pytest.raises(ValueError, match="host"):
        PresenceConfig(host="", pin="1234").ensure_valid()


def test_ensure_valid_rejects_non_digit_pin() -> None:
    with pytest.raises(ValueError, match="digits"):
        PresenceConfig(host="x", pin="12ab").ensure_valid()


def test_ensure_valid_rejects_bad_default_state() -> None:
    with pytest.raises(ValueError, match="default_state"):
        PresenceConfig(host="x", pin="1234", default_state="OFFLINE").ensure_valid()


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    cfg = PresenceConfig(
        host="x.local",
        pin="1234",
        poll_seconds=3.0,
        default_state="AWAY",
        config_path=tmp_path / "presence.ini",
    )
    cfg.save()
    reloaded = load_config(tmp_path / "presence.ini")
    assert reloaded.host == "x.local"
    assert reloaded.pin == "1234"
    assert reloaded.poll_seconds == 3.0
    assert reloaded.default_state == "AWAY"


def test_load_config_uses_defaults_when_no_file_no_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in (
        "BUSYLIGHT_HOST",
        "BUSYLIGHT_PIN",
        "BUSYLIGHT_POLL_SECONDS",
        "BUSYLIGHT_DEFAULT_STATE",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config(tmp_path / "does-not-exist.ini")
    assert cfg.host == ""
    assert cfg.pin == ""
    assert cfg.poll_seconds == 2.0
    assert cfg.default_state == "AVAILABLE"
