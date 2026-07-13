# presence_helper/tests/test_claude_light.py
from __future__ import annotations

import json

import busylight_presence.claude_light as cl


def _use_tmp(tmp_path, monkeypatch, *, on=True):
    monkeypatch.setattr(cl, "flag_path", lambda: tmp_path / "claude_mode")
    monkeypatch.setattr(cl, "state_path", lambda: tmp_path / "claude_state.json")
    monkeypatch.setattr(cl, "_lock_path", lambda: tmp_path / "claude_state.lock")
    monkeypatch.setattr(cl, "_best_effort_set", lambda state: cl._applied.append(state))
    cl._applied = []
    if on:
        (tmp_path / "claude_mode").write_text("on", encoding="ascii")


def test_noops_when_off(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch, on=False)
    cl.mark_working("A")
    cl.mark_idle("A")
    assert cl._applied == []


def test_aggregate_red_if_any_working(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    cl.mark_working("A")            # -> red
    cl.mark_working("B")            # -> red
    cl.mark_idle("A")              # B still working -> red
    assert cl._applied[-1] == "BUSY"
    cl.mark_idle("B")             # all idle -> green
    assert cl._applied[-1] == "AVAILABLE"


def test_sessionend_removes_session(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    cl.mark_working("A")
    cl.mark_sessionend("A")       # gone -> green
    assert cl._applied[-1] == "AVAILABLE"


def test_stale_working_pruned(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "_ttl_seconds", lambda: 100.0)
    times = iter([1000.0, 1000.0, 2000.0, 2000.0])
    monkeypatch.setattr(cl, "_now", lambda: next(times))
    cl.mark_working("A")           # ts=1000
    # A is now 1000s old > 100s TTL -> pruned -> green
    assert cl._desired_state(cl._load_state()) == "AVAILABLE"


def test_focus_binds_to_one_session(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    cl.mark_working("A")
    cl.mark_working("B")
    cl.set_focus("B")             # focus B
    cl.mark_idle("B")            # focused idle -> green even though A works
    assert cl._applied[-1] == "AVAILABLE"
    cl.clear_focus()             # back to aggregate; A still works -> red
    assert cl._applied[-1] == "BUSY"


def test_focus_manual_picks_most_recent(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    t = iter([10.0, 20.0, 30.0, 30.0, 30.0, 30.0])
    monkeypatch.setattr(cl, "_now", lambda: next(t))
    cl.mark_working("A")           # ts=10
    cl.mark_working("B")           # ts=20
    assert cl.set_focus("manual") == "B"   # most-recent active


def test_read_session_id_manual_on_tty(monkeypatch):
    class _TTY:
        def isatty(self):
            return True
    monkeypatch.setattr("sys.stdin", _TTY())
    assert cl._read_session_id() == "manual"


def test_read_session_id_from_stdin_json(monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "sess-42"})))
    assert cl._read_session_id() == "sess-42"


def test_concurrent_updates_do_not_lose_sessions(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    # Interleave: A working, B working, A idle -> B must remain working.
    cl.mark_working("A")
    cl.mark_working("B")
    cl.mark_idle("A")
    st = cl._load_state()
    assert "B" in st["working"] and "A" not in st["working"]
    assert cl._applied[-1] == "BUSY"   # B still working


def test_state_lock_is_best_effort(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(cl.os, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    cl.mark_working("A")   # must not raise
    assert "A" in cl._load_state()["working"]


def test_cli_all_subcommands_exit_zero(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "_read_session_id", lambda: "A")
    for sub in ["on", "working", "idle", "sessionend", "focus", "unfocus", "status", "off"]:
        assert cl.main([sub]) == 0
    assert cl.main(["bogus"]) == 2
