"""Serial-over-USB transport for talking to a BusyLight device offline.

The firmware exposes a tiny JSON command protocol on its USB CDC port
(see `firmware/src/main.cpp::handleSerialProvisioning`). This client
uses it to set / read state without needing Wi-Fi, so the helper keeps
working when the laptop is on a network the device isn't on (or no
network at all).

Connection model
----------------
The serial port is opened on every call and closed immediately after
(`open-write-close`). It's slow-ish (~150 ms per round trip on
Windows) but avoids holding the port exclusively, which is important
because the setup wizard needs to open the same port for provisioning
and `--install-startup` users would otherwise have to quit the helper
first.

State encoding
--------------
The HTTP API speaks state names ("BUSY", "IN_CALL", ...). The serial
API speaks `BusyStatus` enum ints. We convert at the boundary so
`SerialClient` is a drop-in for `BusyLightClient`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

try:
    import serial  # pyserial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - guarded at runtime
    serial = None  # type: ignore[assignment]
    list_ports = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


# Mirror of firmware `BusyStatus` (firmware/include/led_engine.h).
STATE_NAME_TO_INT = {
    "AVAILABLE": 0,
    "BUSY": 1,
    "IN_CALL": 2,
    "AWAY": 3,
    "WIFI_ERROR": 4,
    "OFF": 5,
}
STATE_INT_TO_NAME = {v: k for k, v in STATE_NAME_TO_INT.items()}


# Async beacons the firmware emits on its own — never replies to our
# commands, so skip them while reading for a reply. Mirror of every
# `event:` value the firmware logs autonomously in main.cpp.
ASYNC_BEACONS: frozenset[str] = frozenset(
    {
        "ready",
        "server_started",
        "ap_portal_started",
        "wifi_retry",
        "littlefs_fail",
    }
)


# Espressif native USB-CDC + common UART bridge chips. Same list the
# setup wizard uses, kept in sync intentionally so both tools detect
# the same hardware.
ESPRESSIF_VIDS: frozenset[int] = frozenset(
    {
        0x303A,  # Espressif Systems (native USB CDC on ESP32-C3/C6/S2/S3)
        0x10C4,  # Silicon Labs CP210x (older dev boards)
        0x1A86,  # WCH CH340 (cheap clone dev boards)
    }
)


class SerialUnavailable(RuntimeError):
    """Raised when no BusyLight-looking USB port is reachable."""


class SerialProtocolError(RuntimeError):
    """Raised on JSON decode / unexpected device responses."""


def find_busylight_ports() -> list[str]:
    """COM/tty paths whose USB VID matches a known ESP variant.

    Returns an empty list if pyserial isn't installed or no device is
    plugged in. Order matches `list_ports.comports()` which on Windows
    is roughly insertion order — good enough for "pick the first one".
    """
    if list_ports is None:
        return []
    out: list[str] = []
    for p in list_ports.comports():
        vid = getattr(p, "vid", None)
        if vid in ESPRESSIF_VIDS:
            out.append(p.device)
    return out


@dataclass
class SerialClient:
    """Talks to the BusyLight over USB CDC.

    Mirrors `BusyLightClient`'s public surface (`login`, `set_state`,
    `get_state`) so the higher-level transport can swap between them
    without callers caring which one is in use.
    """

    port: str
    timeout_s: float = 1.5
    baudrate: int = 115200

    # ------------------------------------------------------------------
    # Compat with BusyLightClient — serial has no auth, login is a no-op.
    # ------------------------------------------------------------------
    def login(self) -> None:
        # A `ping` round-trip serves as the equivalent of "session
        # established": it proves we can actually talk to the device.
        if not self.ping():
            raise SerialUnavailable(
                f"device on {self.port} did not respond to ping"
            )

    def ping(self) -> bool:
        try:
            resp = self._roundtrip({"cmd": "ping"})
        except SerialUnavailable:
            return False
        except SerialProtocolError:
            return False
        return bool(resp.get("ok")) and resp.get("event") == "pong"

    def set_state(self, state: str) -> None:
        if state not in STATE_NAME_TO_INT:
            raise ValueError(f"invalid state {state!r}")
        resp = self._roundtrip(
            {"cmd": "set_state", "state": STATE_NAME_TO_INT[state]}
        )
        if not resp.get("ok"):
            raise SerialProtocolError(
                resp.get("error") or "set_state rejected"
            )

    def get_state(self) -> Optional[str]:
        resp = self._roundtrip({"cmd": "get_state"})
        if not resp.get("ok"):
            return None
        raw = resp.get("state")
        if not isinstance(raw, int):
            return None
        return STATE_INT_TO_NAME.get(raw)

    def get_info(self) -> dict:
        """Optional helper — returns whatever the firmware reports
        about itself (hostname, fw version, wifi up/down, IP)."""
        return self._roundtrip({"cmd": "get_info"})

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _roundtrip(self, payload: dict) -> dict:
        if serial is None:
            raise SerialUnavailable("pyserial not installed")
        line = json.dumps(payload, separators=(",", ":")) + "\n"

        # Rapid open/close cycles on Windows CDC ports occasionally trip
        # `ClearCommError` while the kernel is still tearing down the
        # previous handle. Two attempts with a short pause papers over
        # that without holding the port open between calls.
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                return self._one_roundtrip(line)
            except SerialUnavailable as e:
                last_err = e
                if attempt == 0:
                    time.sleep(0.15)
                    continue
                raise
        # Unreachable; appease the type checker.
        raise last_err if last_err else SerialUnavailable("unknown error")

    def _one_roundtrip(self, line: str) -> dict:
        try:
            with serial.Serial(
                self.port,
                baudrate=self.baudrate,
                timeout=self.timeout_s,
                write_timeout=self.timeout_s,
                rtscts=False,
                dsrdtr=False,
                xonxoff=False,
            ) as ser:
                # Don't let pyserial toggle DTR/RTS on open: ESP32-C6 in
                # native USB-CDC mode uses DTR as an MCU reset line on
                # some toolchains, which would otherwise reboot the
                # device on every command. The wizard does the same.
                try:
                    ser.dtr = True
                    ser.rts = False
                except Exception:  # noqa: BLE001
                    pass

                # Drain anything the firmware emitted before we opened
                # (e.g. `{"event":"ready"}` on cold boot, async
                # `wifi_retry` beacons). We don't want to confuse those
                # with a reply to our command.
                ser.reset_input_buffer()
                ser.write(line.encode("utf-8"))
                ser.flush()
                # The firmware responds with exactly one JSON line per
                # command. We may also see async beacons interleaved
                # (e.g. `wifi_retry` every 5-30 s as the radio backs off).
                # Skip those and take the next JSON line as the reply.
                for _ in range(6):
                    raw = ser.readline().decode("utf-8", errors="replace")
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("event") in ASYNC_BEACONS:
                        continue
                    return obj
                raise SerialProtocolError(
                    "no JSON reply within timeout"
                )
        except serial.SerialException as e:
            raise SerialUnavailable(str(e)) from e
        except OSError as e:
            # Windows surfaces "PermissionError: Access is denied" when
            # another process is holding the port (e.g. the setup wizard).
            raise SerialUnavailable(str(e)) from e
