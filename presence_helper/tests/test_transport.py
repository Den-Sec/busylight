# presence_helper/tests/test_transport.py
from __future__ import annotations

import busylight_presence.transport as transport_mod
from busylight_presence.transport import BusyLightTransport


class _FakeSerial:
    """Stands in for SerialClient: answers ping() only for the real port."""

    instances: list[str] = []

    def __init__(self, port: str) -> None:
        self.port = port
        _FakeSerial.instances.append(port)

    def ping(self) -> bool:
        return self.port == "COM_REAL"

    def login(self) -> None:
        if self.port != "COM_REAL":
            raise RuntimeError("decoy should never be logged in")


def test_selects_port_that_answers_pong(monkeypatch) -> None:
    _FakeSerial.instances = []
    # A generic CH340 decoy enumerates before the real BusyLight.
    monkeypatch.setattr(
        transport_mod, "find_busylight_ports", lambda: ["COM_DECOY", "COM_REAL"]
    )
    monkeypatch.setattr(transport_mod, "SerialClient", _FakeSerial)

    t = BusyLightTransport(host="", pin="")
    t._refresh_serial(force=True)

    assert t.serial_port == "COM_REAL"


def test_no_pong_means_no_serial(monkeypatch) -> None:
    monkeypatch.setattr(
        transport_mod, "find_busylight_ports", lambda: ["COM_DECOY"]
    )

    class _NeverPong(_FakeSerial):
        def ping(self) -> bool:
            return False

    monkeypatch.setattr(transport_mod, "SerialClient", _NeverPong)
    t = BusyLightTransport(host="", pin="")
    t._refresh_serial(force=True)
    assert t.serial_port is None


def test_rescan_interval_is_short_while_disconnected() -> None:
    t = BusyLightTransport(host="", pin="")
    t._serial = None
    assert t._rescan_interval() == transport_mod.SERIAL_RESCAN_DISCONNECTED_S
    t._serial = object()  # pretend connected
    assert t._rescan_interval() == transport_mod.SERIAL_RESCAN_CONNECTED_S
