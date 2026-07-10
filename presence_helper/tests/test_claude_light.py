# presence_helper/tests/test_claude_light.py
from __future__ import annotations

import busylight_presence.claude_light as cl


def _point_flag_at(tmp_path, monkeypatch):
    # Redirect the flag into a temp dir so tests never touch the real config.
    monkeypatch.setattr(cl, "flag_path", lambda: tmp_path / "claude_mode")


def test_working_idle_are_noops_when_flag_absent(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(cl, "_best_effort_set", lambda state: calls.append(state))
    assert cl.is_on() is False
    cl.set_working()
    cl.set_idle()
    assert calls == []  # no device writes when the mode is off


def test_working_idle_set_states_when_flag_present(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(cl, "_best_effort_set", lambda state: calls.append(state))
    cl.enable()  # creates flag (and sets green)
    assert cl.is_on() is True
    calls.clear()
    cl.set_working()
    cl.set_idle()
    assert calls == ["BUSY", "AVAILABLE"]


def test_enable_disable_toggles_flag(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "_best_effort_set", lambda state: None)
    cl.enable()
    assert cl.is_on() is True
    cl.disable()
    assert cl.is_on() is False
    cl.disable()  # idempotent, no raise


def test_best_effort_set_swallows_all_errors(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    def _boom():
        raise RuntimeError("no ports")
    monkeypatch.setattr(cl, "find_busylight_ports", _boom)
    # Must not raise even if enumeration blows up.
    assert cl._best_effort_set("BUSY") is False


def test_best_effort_set_swallows_per_port_errors(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "find_busylight_ports", lambda: ["COM_X", "COM_Y"])

    class _Boom:
        def __init__(self, port):
            pass

        def set_state(self, state):
            raise RuntimeError("no ack")

    monkeypatch.setattr(cl, "SerialClient", _Boom)
    assert cl._best_effort_set("BUSY") is False  # both ports fail -> False, no raise


def test_best_effort_set_returns_true_on_first_success(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "find_busylight_ports", lambda: ["COM_X"])

    class _Ok:
        def __init__(self, port):
            pass

        def set_state(self, state):
            pass

    monkeypatch.setattr(cl, "SerialClient", _Ok)
    assert cl._best_effort_set("BUSY") is True


def test_cli_working_exits_zero_even_with_no_device(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "find_busylight_ports", lambda: [])
    cl.enable()
    assert cl.main(["working"]) == 0
    assert cl.main(["idle"]) == 0
    assert cl.main(["status"]) == 0
