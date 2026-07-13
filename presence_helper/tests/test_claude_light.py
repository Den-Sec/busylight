from __future__ import annotations

import io
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
    cl.mark_working("A", "/x")
    cl.mark_idle("A", "/x")
    assert cl._applied == []


def test_aggregate_red_if_any_working(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    cl.mark_working("A", "/home/me/proj-a")
    cl.mark_working("B", "/home/me/proj-b")
    cl.mark_idle("A", "/home/me/proj-a")     # B still working
    assert cl._applied[-1] == "BUSY"
    cl.mark_idle("B", "/home/me/proj-b")     # all idle
    assert cl._applied[-1] == "AVAILABLE"


def test_focus_follows_one_session(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    cl.mark_working("A", "/p/a")
    cl.mark_working("B", "/p/b")
    cl.set_focus("B")
    cl.mark_idle("B", "/p/b")                # focused idle -> green (A ignored)
    assert cl._applied[-1] == "AVAILABLE"
    cl.mark_working("B", "/p/b")             # focused works -> red
    assert cl._applied[-1] == "BUSY"
    cl.clear_focus()                         # aggregate; A+B working -> red
    assert cl._applied[-1] == "BUSY"


def test_sessionend_removes_and_unfocuses(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    cl.mark_working("A", "/p/a")
    cl.set_focus("A")
    cl.mark_sessionend("A")
    st = cl._load_state()
    assert "A" not in st["sessions"] and st["focus"] is None
    assert cl._applied[-1] == "AVAILABLE"


def test_status_labels_and_collision(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    cl.mark_working("aaaa1111", "/home/me/busylight")
    cl.mark_idle("bbbb2222", "/home/me/busylight")   # same folder -> collision
    cl.mark_idle("cccc3333", "/home/me/lan-ai")
    s = cl.status()
    labels = {item["id"]: item["label"] for item in s["sessions"]}
    assert labels["cccc3333"] == "lan-ai"
    # collision pair gets a short-id suffix
    assert labels["aaaa1111"] == "busylight (aaaa)"
    assert labels["bbbb2222"] == "busylight (bbbb)"
    assert s["working"] == 1
    assert {i["id"] for i in s["sessions"]} == {"aaaa1111", "bbbb2222", "cccc3333"}


def test_status_sessions_sorted_recent_first(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    t = iter([10.0, 20.0, 30.0, 30.0, 30.0, 30.0])
    monkeypatch.setattr(cl, "_now", lambda: next(t))
    cl.mark_idle("old", "/p/old")
    cl.mark_idle("new", "/p/new")
    s = cl.status()
    assert s["sessions"][0]["id"] == "new"


def test_prune_drops_stale(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "_ttl_seconds", lambda: 100.0)
    t = iter([1000.0, 2000.0, 2000.0])
    monkeypatch.setattr(cl, "_now", lambda: next(t))
    cl.mark_working("A", "/p/a")              # ts=1000
    # now 2000, TTL 100 -> A is stale -> aggregate sees nothing -> green
    assert cl._desired_state(cl._load_state()) == "AVAILABLE"


def test_read_hook_input_manual_on_tty(monkeypatch):
    class _TTY:
        def isatty(self):
            return True
    monkeypatch.setattr("sys.stdin", _TTY())
    assert cl._read_hook_input() == ("manual", None)


def test_read_hook_input_parses_sid_and_cwd(monkeypatch):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"session_id": "s1", "cwd": "/proj"}))
    )
    assert cl._read_hook_input() == ("s1", "/proj")


def test_mutation_happens_under_lock(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    seen = {}
    real_save = cl._save_state
    def spy_save(state):
        seen["locked"] = cl._lock_path().exists()
        return real_save(state)
    monkeypatch.setattr(cl, "_save_state", spy_save)
    cl.mark_working("A", "/p/a")
    assert seen["locked"] is True
    assert not cl._lock_path().exists()


def test_cli_all_subcommands_exit_zero(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "_read_hook_input", lambda: ("A", "/p/a"))
    for sub in ["on", "working", "idle", "sessionend", "unfocus", "status", "off"]:
        assert cl.main([sub]) == 0
    assert cl.main(["focus", "SID"]) == 0     # positional focus
    assert cl.main(["bogus"]) == 2
