# BusyLight "Claude mode v2.1" — session selector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the confusing "Focus current session" button with a dropdown selector of open Claude Code sessions labeled by project folder; the light follows the chosen session, or aggregates over all ("All sessions").

**Architecture:** `claude_state.json` becomes a session registry `{sessions: {sid: {cwd, status, ts}}, focus}`. Hooks capture `cwd` from stdin. `status()` returns a labeled session list; the bridge exposes it and a focus-by-id action; the dashboard renders a `<select>`.

**Tech Stack:** Python 3.10+, existing `claude_light`/`webui_bridge`/bundled `webui/`, pytest.

## Global Constraints (from the spec)
- Every device write best-effort, CLI exits 0, `is_on()` + all state reads exception-guarded — a hook must never fail a Claude Code turn. No-op when the mode flag is off. All state writes under the existing best-effort file lock + atomic save; `_apply()` stays OUTSIDE the lock.
- Light: prune sessions older than TTL; focus set & session present → red iff that session `status=="working"`; else aggregate → red iff ANY session working.
- Labels: folder basename of `cwd` (`"session"` if none); disambiguate same-basename collisions with ` (<sid[:4]>)`; sessions sorted most-recent first.
- Keep `enable`/`disable`/`is_on` (tray depends on them). Bundled webui only; do NOT touch `firmware/data/`. ruff ≤ 100; keep full suite green.

**Run tests:** from `presence_helper/`, `& .\.venv\Scripts\python.exe -m pytest tests/<file> -q`.

---

## Task W1: Session registry in `claude_light`

**Files:**
- Rewrite: `presence_helper/src/busylight_presence/claude_light.py`
- Rewrite: `presence_helper/tests/test_claude_light.py`

**Interfaces produced:** `is_on`, `enable`, `disable`, `mark_working(sid, cwd=None)`, `mark_idle(sid, cwd=None)`, `mark_sessionend(sid)`, `set_focus(sid)`, `clear_focus()`, `status() -> dict`, `_read_hook_input() -> tuple[str, str|None]`, `main(argv)`. Keeps `flag_path`/`state_path`/`_lock_path`/`_state_lock`/`_best_effort_set`/`_now`/`_ttl_seconds`.

- [ ] **Step 1: Rewrite `tests/test_claude_light.py`** (write the tests first):

```python
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
```

- [ ] **Step 2: Run — expect FAIL** (`mark_working` signature/`sessions` shape).
Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_light.py -q`

- [ ] **Step 3: Rewrite `claude_light.py`.** Keep the module header/imports/`_ttl_seconds`/`_now`/`flag_path`/`state_path`/`_lock_path`/`_state_lock`/`is_on`/`_best_effort_set` EXACTLY as they are now (lines 1–112 of the current file, incl. the lock). Replace everything from `_load_state` (line 115) to the end with:

```python
def _load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
        raw = data.get("sessions") if isinstance(data, dict) else None
        sessions: dict = {}
        if isinstance(raw, dict):
            for sid, v in raw.items():
                if isinstance(v, dict) and isinstance(v.get("ts"), (int, float)):
                    sessions[sid] = {
                        "cwd": v.get("cwd") if isinstance(v.get("cwd"), str) else None,
                        "status": "working" if v.get("status") == "working" else "idle",
                        "ts": v["ts"],
                    }
        focus = data.get("focus") if isinstance(data, dict) else None
        return {"sessions": sessions, "focus": focus if isinstance(focus, str) else None}
    except Exception:  # noqa: BLE001
        return {"sessions": {}, "focus": None}


def _save_state(state: dict) -> None:
    try:
        p = state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:  # noqa: BLE001
        pass


def _prune(state: dict) -> dict:
    ttl = _ttl_seconds()
    now = _now()
    state["sessions"] = {
        sid: s
        for sid, s in state["sessions"].items()
        if isinstance(s.get("ts"), (int, float)) and (now - s["ts"]) <= ttl
    }
    return state


def _read_hook_input() -> tuple[str, str | None]:
    """(session_id, cwd) from a hook's stdin JSON; never blocks on a manual
    (tty) run."""
    try:
        stdin = sys.stdin
        if stdin is None or stdin.isatty():
            return "manual", None
        raw = stdin.read()
    except Exception:  # noqa: BLE001
        return "manual", None
    if not raw:
        return "manual", None
    try:
        obj = json.loads(raw)
        sid = obj.get("session_id")
        cwd = obj.get("cwd")
        sid = sid if isinstance(sid, str) and sid else "manual"
        cwd = cwd if isinstance(cwd, str) and cwd else None
        return sid, cwd
    except Exception:  # noqa: BLE001
        return "manual", None


def _desired_state(state: dict) -> str | None:
    if not is_on():
        return None
    state = _prune(state)
    sessions = state["sessions"]
    focus = state.get("focus")
    if focus and focus in sessions:
        return _WORKING if sessions[focus]["status"] == "working" else _IDLE
    any_working = any(s["status"] == "working" for s in sessions.values())
    return _WORKING if any_working else _IDLE


def _apply(state: dict) -> None:
    ds = _desired_state(state)
    if ds is not None:
        _best_effort_set(ds)


def enable() -> None:
    p = flag_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("on", encoding="ascii")
    _best_effort_set(_IDLE)


def disable() -> None:
    try:
        flag_path().unlink()
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001
        pass
    with _state_lock():
        _save_state({"sessions": {}, "focus": None})


def _upsert(st: dict, sid: str, cwd: str | None, status: str) -> None:
    prev = st["sessions"].get(sid, {})
    st["sessions"][sid] = {
        "cwd": cwd if cwd is not None else prev.get("cwd"),
        "status": status,
        "ts": _now(),
    }


def mark_working(sid: str, cwd: str | None = None) -> None:
    if not is_on():
        return
    with _state_lock():
        st = _load_state()
        _upsert(st, sid, cwd, "working")
        _save_state(st)
    _apply(st)


def mark_idle(sid: str, cwd: str | None = None) -> None:
    if not is_on():
        return
    with _state_lock():
        st = _load_state()
        _upsert(st, sid, cwd, "idle")
        _save_state(st)
    _apply(st)


def mark_sessionend(sid: str) -> None:
    if not is_on():
        return
    with _state_lock():
        st = _load_state()
        st["sessions"].pop(sid, None)
        if st.get("focus") == sid:
            st["focus"] = None
        _save_state(st)
    _apply(st)


def set_focus(sid: str | None) -> str | None:
    with _state_lock():
        st = _load_state()
        st["focus"] = sid if (sid and sid != "manual") else None
        _save_state(st)
    _apply(st)
    return st.get("focus")


def clear_focus() -> None:
    with _state_lock():
        st = _load_state()
        st["focus"] = None
        _save_state(st)
    _apply(st)


def _label_for(sid: str, cwd: str | None) -> str:
    if cwd:
        base = os.path.basename(cwd.rstrip("/\\"))
        return base or cwd
    return "session"


def status() -> dict:
    st = _prune(_load_state())
    sessions = st["sessions"]
    bases: dict[str, list[str]] = {}
    for sid, s in sessions.items():
        bases.setdefault(_label_for(sid, s.get("cwd")), []).append(sid)
    items = []
    for sid, s in sorted(sessions.items(), key=lambda kv: kv[1]["ts"], reverse=True):
        base = _label_for(sid, s.get("cwd"))
        label = base if len(bases[base]) == 1 else f"{base} ({sid[:4]})"
        items.append({
            "id": sid, "label": label, "cwd": s.get("cwd"), "status": s["status"],
        })
    working = sum(1 for s in sessions.values() if s["status"] == "working")
    return {
        "on": is_on(),
        "focus": st.get("focus"),
        "working": working,
        "sessions": items,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sub = args[0] if args else "status"
    if sub == "on":
        enable()
    elif sub == "off":
        disable()
    elif sub == "working":
        sid, cwd = _read_hook_input()
        mark_working(sid, cwd)
    elif sub == "idle":
        sid, cwd = _read_hook_input()
        mark_idle(sid, cwd)
    elif sub == "sessionend":
        sid, _cwd = _read_hook_input()
        mark_sessionend(sid)
    elif sub == "focus":
        if len(args) > 1:
            set_focus(args[1])
        else:
            sid, _cwd = _read_hook_input()
            set_focus(sid)
    elif sub == "unfocus":
        clear_focus()
    elif sub == "status":
        print(json.dumps(status()))
    elif sub == "install-hooks":
        from .claude_hooks import install_hooks
        install_hooks()
    elif sub == "uninstall-hooks":
        from .claude_hooks import uninstall_hooks
        uninstall_hooks()
    else:
        print(f"unknown command: {sub}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run green.** `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_light.py tests/ -q` (the pre-existing `test_main_startup_flags` mutex failure is environmental if a tray app runs — ignore it; introduce no NEW failures).

- [ ] **Step 5: Commit**
```bash
git add presence_helper/src/busylight_presence/claude_light.py presence_helper/tests/test_claude_light.py
git commit -m "feat(claude-mode-v2.1): session registry with cwd labels + focus-by-id"
```

---

## Task W2: Bridge focus-by-id + dashboard dropdown

**Files:**
- Modify: `presence_helper/src/busylight_presence/webui_bridge.py` (`claude_mode_action` takes a session; POST passes it)
- Modify: `presence_helper/src/busylight_presence/webui/index.html` (button → `<select>`)
- Modify: `presence_helper/src/busylight_presence/webui/app.js` (populate dropdown, focus-by-id)
- Modify: `presence_helper/tests/test_bridge_claude.py` (focus-by-id)

- [ ] **Step 1: Update the bridge test** — replace `test_bridge_claude.py` body:

```python
from __future__ import annotations

import busylight_presence.webui_bridge as wb


def test_claude_mode_on_off_and_focus(monkeypatch):
    import busylight_presence.claude_light as cl
    calls = {"focus": None, "cleared": 0, "on": False}
    monkeypatch.setattr(cl, "is_on", lambda: calls["on"])
    monkeypatch.setattr(cl, "enable", lambda: calls.__setitem__("on", True))
    monkeypatch.setattr(cl, "disable", lambda: calls.__setitem__("on", False))
    monkeypatch.setattr(cl, "set_focus", lambda sid: calls.__setitem__("focus", sid))
    monkeypatch.setattr(cl, "clear_focus", lambda: calls.__setitem__("cleared", calls["cleared"] + 1))
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
```

- [ ] **Step 2: Run — expect FAIL** (`claude_mode_action` takes no `session`).

- [ ] **Step 3: Update the bridge.** In `webui_bridge.py`, change `claude_mode_action`:

```python
def claude_mode_action(action: str, session: str | None = None) -> dict:
    """Pure, testable helper: apply a Claude-mode action, return new status."""
    from . import claude_light
    if action == "on":
        claude_light.enable()
    elif action == "off":
        claude_light.disable()
    elif action == "focus":
        if session:
            claude_light.set_focus(session)
        else:
            claude_light.clear_focus()
    elif action == "unfocus":
        claude_light.clear_focus()
    return claude_light.status()
```

Find the POST route for `/api/claude-mode` (added in v2) and pass the session through:
```python
        if path == "/api/claude-mode":
            body = self._read_json_body()
            action = (body.get("action") or "").strip()
            session = body.get("session")
            session = session if isinstance(session, str) and session else None
            return self._send_json(200, claude_mode_action(action, session))
```
(`claude_mode_status()` and the GET route are unchanged.)

- [ ] **Step 4: Swap the button for a dropdown.** In `webui/index.html`, replace the line
`<button id="claude-focus" type="button" class="ghost">Focus current session</button>`
with:
```html
<label class="lede lede--sm" for="claude-focus-select">Which session drives the light</label>
<select id="claude-focus-select" class="mqtt-toggle">
  <option value="">All sessions (aggregate)</option>
</select>
```
(Reuse whatever `<select>` styling exists; the exact class is cosmetic — match a sibling `<select>` in the file if one exists, e.g. the schedule state selector.)

- [ ] **Step 5: Wire the dropdown in `app.js`.** Replace the `claudeFocusBtn` element ref and its click handler with the select. Specifically:
- Change the element ref (near line 554): `const claudeFocusSelect = document.getElementById("claude-focus-select");`
- In `refreshClaude()`, after setting the status text, repopulate the dropdown from `s.sessions` and select the current focus:
```javascript
    if (claudeFocusSelect) {
      const cur = s.focus || "";
      const opts = ['<option value="">All sessions (aggregate)</option>'];
      for (const sess of s.sessions || []) {
        const sel = sess.id === s.focus ? " selected" : "";
        const mark = sess.status === "working" ? "● " : "○ ";
        opts.push(
          `<option value="${sess.id}"${sel}>${mark}${sess.label} — ${sess.status}</option>`
        );
      }
      claudeFocusSelect.innerHTML = opts.join("");
      claudeFocusSelect.value = cur;
    }
```
- Replace the old focus button handler (near line 1409) with:
```javascript
if (claudeFocusSelect) {
  claudeFocusSelect.addEventListener("change", (e) =>
    claudeAction("focus", e.target.value));
}
```
- Extend `claudeAction` to send the session:
```javascript
async function claudeAction(action, session) {
  try {
    await api("/api/claude-mode", {
      method: "POST",
      body: JSON.stringify(session === undefined ? { action } : { action, session }),
    });
    if (claudeMsg) claudeMsg.textContent = "";
  } catch (err) {
    if (claudeMsg) claudeMsg.textContent = err.message;
  }
  await refreshClaude();
}
```
Remove the old `claudeFocusBtn` const and its listener. Leave the on/off toggle handler calling `claudeAction("on"/"off")` (no session) working.

- [ ] **Step 6: Run tests + manual.** `& .\.venv\Scripts\python.exe -m pytest tests/ -q` (green apart from the env mutex failure). Manual (restart the tray app first — it caches web assets): open the dashboard, confirm the Claude-mode card shows a dropdown listing sessions by folder and selecting one binds the light.

- [ ] **Step 7: Commit**
```bash
git add presence_helper/src/busylight_presence/webui_bridge.py presence_helper/src/busylight_presence/webui/index.html presence_helper/src/busylight_presence/webui/app.js presence_helper/tests/test_bridge_claude.py
git commit -m "feat(claude-mode-v2.1): dashboard session dropdown (focus by project) + bridge focus-by-id"
```

---

## Spec Coverage Check
- Session registry + cwd labels + focus-by-id + aggregate/prune → W1.
- Bridge focus-by-id + dashboard dropdown → W2.

## Notes for the implementer
- Keep `enable`/`disable`/`is_on` names (tray). Do NOT touch `firmware/data/`, the tray suppression logic, `claude_hooks.py`, or the `_state_lock`/atomic-save code (carry it over verbatim in W1).
- Tests must monkeypatch `flag_path`/`state_path`/`_lock_path` to tmp; never touch the real config.
- After merge, the tray app must be restarted to serve the new dashboard (in-process asset cache).
