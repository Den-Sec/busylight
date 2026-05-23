"""Configuration loader for the presence helper.

Reads in this priority order:
1. Explicit constructor arguments (used by tests).
2. Environment variables (BUSYLIGHT_HOST, BUSYLIGHT_PIN, …).
3. ``%APPDATA%/BusyLight/presence.ini`` on Windows, or
   ``~/.config/busylight/presence.ini`` everywhere else.

We use INI rather than YAML to avoid pulling in a PyYAML dependency
for what is two strings and a number.
"""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path


CONFIG_FILENAME = "presence.ini"
ENV_HOST = "BUSYLIGHT_HOST"
ENV_PIN = "BUSYLIGHT_PIN"
ENV_POLL = "BUSYLIGHT_POLL_SECONDS"
ENV_DEFAULT_STATE = "BUSYLIGHT_DEFAULT_STATE"


def _default_config_path() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / "BusyLight" / CONFIG_FILENAME
    if sys.platform == "darwin":
        return (
            Path.home() / "Library" / "Application Support" / "BusyLight" / CONFIG_FILENAME
        )
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "busylight" / CONFIG_FILENAME


@dataclass
class PresenceConfig:
    host: str
    pin: str
    poll_seconds: float = 2.0
    default_state: str = "AVAILABLE"
    config_path: Path | None = None

    def ensure_valid(self) -> None:
        if not self.host:
            raise ValueError(
                "BusyLight host is required (set BUSYLIGHT_HOST or "
                "edit the config file)"
            )
        if not self.pin or not self.pin.isdigit():
            raise ValueError(
                "BusyLight PIN must be set and contain only digits (4-8)"
            )
        if not (1 <= len(self.pin) <= 8):
            raise ValueError("PIN must be 4-8 digits")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be > 0")
        if self.default_state not in ("AVAILABLE", "BUSY", "AWAY", "IN_CALL"):
            raise ValueError(
                "default_state must be AVAILABLE / BUSY / AWAY / IN_CALL"
            )

    def save(self) -> None:
        if self.config_path is None:
            self.config_path = _default_config_path()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        parser = configparser.ConfigParser()
        parser["busylight"] = {
            "host": self.host,
            "pin": self.pin,
            "poll_seconds": str(self.poll_seconds),
            "default_state": self.default_state,
        }
        with self.config_path.open("w", encoding="utf-8") as fh:
            parser.write(fh)


def load_config(explicit_path: Path | None = None) -> PresenceConfig:
    path = explicit_path or _default_config_path()
    host = os.environ.get(ENV_HOST, "").strip()
    pin = os.environ.get(ENV_PIN, "").strip()
    poll = os.environ.get(ENV_POLL, "").strip()
    default_state = os.environ.get(ENV_DEFAULT_STATE, "").strip().upper()

    if path.is_file():
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        if parser.has_section("busylight"):
            section = parser["busylight"]
            host = host or section.get("host", "")
            pin = pin or section.get("pin", "")
            poll = poll or section.get("poll_seconds", "")
            default_state = default_state or section.get(
                "default_state", ""
            ).upper()

    poll_seconds = float(poll) if poll else 2.0
    default_state = default_state or "AVAILABLE"

    cfg = PresenceConfig(
        host=host,
        pin=pin,
        poll_seconds=poll_seconds,
        default_state=default_state,
        config_path=path,
    )
    return cfg
