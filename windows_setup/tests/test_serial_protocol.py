"""Unit tests for the BusyLight wizard serial protocol layer.

These tests mock the underlying `serial.Serial` class via `FakeSerial`, so
they exercise the real handshake/configuration flow without touching any
hardware. Real device verification lives in the integration step.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Iterable

import pytest
from serial import SerialTimeoutException

from busylight_setup import serial_protocol as sp


class FakeSerial:
    """Minimal stand-in for `serial.Serial` covering everything we use."""

    def __init__(self, responses: Iterable[bytes] = ()) -> None:
        self.write_buffer = bytearray()
        self.responses: deque[bytes] = deque(responses)
        self.dtr = False
        self.rts = False
        self.write_raises: Exception | None = None
        self.closed = False

    # ---------- properties pyserial relies on ----------
    def write(self, data: bytes) -> int:
        if self.write_raises is not None:
            exc = self.write_raises
            self.write_raises = None  # one-shot raise
            raise exc
        self.write_buffer.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        if self.responses:
            return self.responses.popleft()
        return b""

    def reset_input_buffer(self) -> None:
        pass

    # ---------- context manager (used by `with Serial(...) as ser`) ----------
    def __enter__(self) -> "FakeSerial":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.closed = True


def _line(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# build_config_packet
# ---------------------------------------------------------------------------
def test_build_config_packet_has_expected_shape() -> None:
    payload = sp.build_config_packet("MyWifi", "secretpass", "123456")
    assert payload == {
        "cmd": "set_config",
        "ssid": "MyWifi",
        "password": "secretpass",
        "pin": "123456",
    }


# ---------------------------------------------------------------------------
# _read_json_line
# ---------------------------------------------------------------------------
def test_read_json_line_strips_junk_prefix() -> None:
    ser = FakeSerial(responses=[b'garbage{"event":"pong","ok":true}\n'])
    msg = sp._read_json_line(ser)
    assert msg == {"event": "pong", "ok": True}


def test_read_json_line_returns_none_on_empty() -> None:
    ser = FakeSerial(responses=[b""])
    assert sp._read_json_line(ser) is None


def test_read_json_line_returns_none_on_unparseable() -> None:
    ser = FakeSerial(responses=[b"not json at all\n"])
    assert sp._read_json_line(ser) is None


def test_read_json_line_handles_whitespace_only_line() -> None:
    ser = FakeSerial(responses=[b"   \n"])
    assert sp._read_json_line(ser) is None


# ---------------------------------------------------------------------------
# _wait_for_pong
# ---------------------------------------------------------------------------
def test_wait_for_pong_accepts_pong_event() -> None:
    ser = FakeSerial(responses=[_line({"event": "pong", "ok": True})])
    sp._wait_for_pong(ser, timeout_s=2.0)
    # First payload sent must be a ping.
    first_line = bytes(ser.write_buffer).splitlines()[0]
    assert json.loads(first_line.decode())["cmd"] == "ping"


def test_wait_for_pong_accepts_ready_beacon() -> None:
    ser = FakeSerial(responses=[_line({"event": "ready", "ok": True, "fw": "0.2.0"})])
    sp._wait_for_pong(ser, timeout_s=2.0)


def test_wait_for_pong_ignores_unrelated_messages() -> None:
    ser = FakeSerial(
        responses=[
            _line({"event": "wifi_reconnect", "ok": False}),
            _line({"event": "pong", "ok": True}),
        ]
    )
    sp._wait_for_pong(ser, timeout_s=2.0)


def test_wait_for_pong_raises_on_timeout() -> None:
    ser = FakeSerial(responses=[])  # device never answers
    with pytest.raises(RuntimeError, match="handshake"):
        sp._wait_for_pong(ser, timeout_s=0.2)


def test_wait_for_pong_recovers_after_write_timeout() -> None:
    ser = FakeSerial(responses=[_line({"event": "pong", "ok": True})])
    ser.write_raises = SerialTimeoutException("simulated")
    # Should swallow the timeout, keep polling, and accept the pong.
    sp._wait_for_pong(ser, timeout_s=2.0)


# ---------------------------------------------------------------------------
# configure_device end-to-end (Serial monkey-patched)
# ---------------------------------------------------------------------------
@pytest.fixture()
def patched_serial(monkeypatch: pytest.MonkeyPatch):
    """Replace `Serial` inside `serial_protocol` with a controllable fake."""

    instances: list[FakeSerial] = []

    def factory(responses: Iterable[bytes]):
        def _ctor(**_kwargs):
            ser = FakeSerial(responses=responses)
            instances.append(ser)
            return ser

        return _ctor

    def install(responses: Iterable[bytes]) -> list[FakeSerial]:
        monkeypatch.setattr(sp, "Serial", factory(responses))
        return instances

    return install


def test_configure_device_happy_path(patched_serial) -> None:
    instances = patched_serial(
        [
            _line({"event": "ready", "ok": True, "fw": "0.2.0"}),
            _line({"event": "config_saved", "ok": True}),
            _line({"event": "server_started", "ok": True, "ip": "192.168.1.42"}),
        ]
    )
    result = sp.configure_device("COM3", "MyWifi", "pwd", "1234", timeout_s=5.0)
    # No `host` field in any response: wizard falls back to plain busylight.local.
    assert result.mdns_url == "http://busylight.local"
    assert result.ip_url == "http://192.168.1.42"
    ser = instances[0]
    assert ser.dtr is True
    assert ser.rts is False
    written = bytes(ser.write_buffer).decode()
    assert '"cmd": "set_config"' in written
    assert '"ssid": "MyWifi"' in written


def test_configure_device_uses_host_from_ready(patched_serial) -> None:
    patched_serial(
        [
            _line({"event": "ready", "ok": True, "fw": "0.2.0",
                   "host": "busylight-abcd"}),
            _line({"event": "config_saved", "ok": True,
                   "host": "busylight-abcd"}),
            _line({"event": "server_started", "ok": True,
                   "ip": "192.168.1.42", "host": "busylight-abcd"}),
        ]
    )
    result = sp.configure_device("COM3", "MyWifi", "pwd", "1234", timeout_s=5.0)
    assert result.mdns_url == "http://busylight-abcd.local"
    assert result.ip_url == "http://192.168.1.42"


def test_configure_device_ignores_autonomous_wifi_retry(patched_serial) -> None:
    """The device emits {ok:false,event:wifi_retry} while reconnecting.

    Those are status events, not command rejections. The wizard must keep
    listening until it sees `config_saved`.
    """
    patched_serial(
        [
            _line({"event": "ready", "ok": True, "host": "busylight-f5f0"}),
            _line({"event": "wifi_retry", "ok": False, "attempt": 1}),
            _line({"event": "wifi_retry", "ok": False, "attempt": 2}),
            _line({"event": "config_saved", "ok": True,
                   "host": "busylight-f5f0"}),
        ]
    )
    # No server_started: short-circuit after the 8 s grace window.
    # Patch time.monotonic / time.time to fast-forward.
    import busylight_setup.serial_protocol as sp_mod

    now = [0.0]

    def fake_time() -> float:
        return now[0]

    real_time = sp_mod.time.time
    sp_mod.time.time = fake_time  # type: ignore[attr-defined]
    try:
        # Advance the clock by 9 seconds after config_saved is observed.
        original_read = sp_mod._read_json_line

        def stepped_read(ser):
            now[0] += 0.5
            return original_read(ser)

        sp_mod._read_json_line = stepped_read  # type: ignore[attr-defined]
        try:
            result = sp.configure_device(
                "COM3", "SSID", "pwd", "1234", timeout_s=60.0
            )
        finally:
            sp_mod._read_json_line = original_read  # type: ignore[attr-defined]
    finally:
        sp_mod.time.time = real_time  # type: ignore[attr-defined]

    assert result.mdns_url == "http://busylight-f5f0.local"
    assert result.ip_url is None


def test_configure_device_raises_on_device_error(patched_serial) -> None:
    patched_serial(
        [
            _line({"event": "ready", "ok": True}),
            _line({"ok": False, "error": "validation"}),
        ]
    )
    with pytest.raises(RuntimeError, match="validation"):
        sp.configure_device("COM3", "SSID", "pwd", "1234", timeout_s=5.0)


def test_configure_device_raises_when_config_never_saved(patched_serial) -> None:
    patched_serial(
        [
            _line({"event": "ready", "ok": True}),
            # No `config_saved` event, just silence afterwards.
        ]
    )
    with pytest.raises(RuntimeError, match="confirm configuration save"):
        sp.configure_device("COM3", "SSID", "pwd", "1234", timeout_s=0.5)


def test_configure_device_returns_without_ip_when_server_started_missing(
    patched_serial,
) -> None:
    # Pad responses with empty reads so the 8-second short-circuit can trigger.
    silence = [b""] * 200
    patched_serial(
        [
            _line({"event": "ready", "ok": True}),
            _line({"event": "config_saved", "ok": True}),
            *silence,
        ]
    )
    # NOTE: the 8s short-circuit is wall-clock based; we monkey-patch time
    # to keep the test fast.
    import busylight_setup.serial_protocol as sp_mod

    fake_now = iter(
        [0.0, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        + [10.0] * 200  # jump past the 8s window
    )

    def _time():
        try:
            return next(fake_now)
        except StopIteration:
            return 999.0

    sp_mod.time.time = _time  # type: ignore[attr-defined]
    try:
        result = sp.configure_device("COM3", "SSID", "pwd", "1234", timeout_s=30.0)
    finally:
        import time as real_time

        sp_mod.time.time = real_time.time  # type: ignore[attr-defined]
    assert result.ip_url is None
    assert result.mdns_url == "http://busylight.local"


# ---------------------------------------------------------------------------
# available_ports — smoke test (just ensure it returns a list).
# ---------------------------------------------------------------------------
def test_available_ports_returns_list() -> None:
    ports = sp.available_ports()
    assert isinstance(ports, list)


# ---------------------------------------------------------------------------
# available_busylight_ports — uses a stub list_ports.comports()
# ---------------------------------------------------------------------------
class _FakePort:
    def __init__(self, device: str, vid: int | None, description: str) -> None:
        self.device = device
        self.vid = vid
        self.description = description


def test_busylight_ports_prefers_espressif_vid(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = [
        _FakePort("COM1", 0x0000, "Generic UART"),
        _FakePort("COM3", 0x303A, "USB Serial Device"),
        _FakePort("COM7", 0x10C4, "Silicon Labs CP210x"),
    ]
    monkeypatch.setattr(sp.list_ports, "comports", lambda: fake)
    ports = sp.available_busylight_ports()
    devices = [d for d, _ in ports]
    assert devices == ["COM3", "COM7"]


def test_busylight_ports_falls_back_when_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = [
        _FakePort("COM1", 0x0000, "Generic UART"),
        _FakePort("COM2", None, "Unknown"),
    ]
    monkeypatch.setattr(sp.list_ports, "comports", lambda: fake)
    ports = sp.available_busylight_ports()
    devices = [d for d, _ in ports]
    assert devices == ["COM1", "COM2"]


def test_busylight_ports_returns_empty_when_no_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp.list_ports, "comports", lambda: [])
    assert sp.available_busylight_ports() == []
