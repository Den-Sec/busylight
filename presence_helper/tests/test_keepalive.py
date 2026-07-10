from __future__ import annotations

from busylight_presence.client import BusyLightNetworkError
from busylight_presence.config import PresenceConfig
from busylight_presence.main import PresenceLoop


class _RecordingClient:
    def __init__(self, raise_exc=None):
        self.get_state_calls = 0
        self._raise = raise_exc

    def get_state(self):
        self.get_state_calls += 1
        if self._raise:
            raise self._raise
        return "AVAILABLE"

    def set_state(self, state):
        raise AssertionError("keepalive must NOT set state")

    def login(self):
        pass


def test_keepalive_pings_without_driving_led():
    c = _RecordingClient()
    loop = PresenceLoop(PresenceConfig(host="x", pin="1234"), c)
    loop.keepalive()
    assert c.get_state_calls == 1  # one serial round-trip, no set_state


def test_keepalive_swallows_network_errors():
    c = _RecordingClient(raise_exc=BusyLightNetworkError("down"))
    loop = PresenceLoop(PresenceConfig(host="x", pin="1234"), c)
    loop.keepalive()  # must NOT raise
    assert c.get_state_calls == 1
