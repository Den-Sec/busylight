from __future__ import annotations

import busylight_presence.webui_bridge as wb


def test_claude_mode_on_off_and_focus(monkeypatch):
    import busylight_presence.claude_light as cl
    calls = {"focus": None, "cleared": 0, "on": False}
    monkeypatch.setattr(cl, "is_on", lambda: calls["on"])
    monkeypatch.setattr(cl, "enable", lambda: calls.__setitem__("on", True))
    monkeypatch.setattr(cl, "disable", lambda: calls.__setitem__("on", False))
    monkeypatch.setattr(cl, "set_focus", lambda sid: calls.__setitem__("focus", sid))
    monkeypatch.setattr(
        cl, "clear_focus", lambda: calls.__setitem__("cleared", calls["cleared"] + 1)
    )
    monkeypatch.setattr(cl, "status", lambda: {"on": calls["on"], "focus": calls["focus"],
                                               "working": 0, "sessions": []})

    wb.claude_mode_action("on")
    assert calls["on"] is True
    wb.claude_mode_action("focus", "SESS-9")     # focus a specific session
    assert calls["focus"] == "SESS-9"
    wb.claude_mode_action("focus", None)         # empty session -> clear
    assert calls["cleared"] == 1
    wb.claude_mode_action("unfocus")
    assert calls["cleared"] == 2
    s = wb.claude_mode_status()
    assert "sessions" in s
