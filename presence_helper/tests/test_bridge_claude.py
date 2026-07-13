# presence_helper/tests/test_bridge_claude.py
from __future__ import annotations

import busylight_presence.webui_bridge as wb


def test_claude_mode_get_post(monkeypatch):
    # Drive the pure endpoint helpers directly (no HTTP server needed).
    import busylight_presence.claude_light as cl
    state = {"on": False}
    monkeypatch.setattr(cl, "is_on", lambda: state["on"])
    monkeypatch.setattr(cl, "enable", lambda: state.__setitem__("on", True))
    monkeypatch.setattr(cl, "disable", lambda: state.__setitem__("on", False))
    monkeypatch.setattr(cl, "status", lambda: {"on": state["on"], "working": 0, "focus": None})

    assert wb.claude_mode_status()["on"] is False
    wb.claude_mode_action("on")
    assert wb.claude_mode_status()["on"] is True
    wb.claude_mode_action("off")
    assert wb.claude_mode_status()["on"] is False
