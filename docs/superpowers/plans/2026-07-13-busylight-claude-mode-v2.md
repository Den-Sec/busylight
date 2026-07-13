# BusyLight "Claude mode v2" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make Claude mode session-aware (red if ANY Claude Code session is working, green when all idle, plus an optional `focus`), and add a "Claude mode" card to the desktop-bundled dashboard.

**Architecture:** A JSON state file (`claude_state.json`) holds the set of currently-working sessions (session_id → timestamp) + an optional focus session. The hooks pass their `session_id` on stdin; the CLI updates the state and re-applies the light (best-effort, exit 0). A bridge endpoint + a dashboard card expose the toggle/status.

**Tech Stack:** Python 3.10+, existing `serial_client`/`config`/`webui_bridge`, the bundled `webui/` (HTML/CSS/JS), pytest.

## Global Constraints (from the spec)
- **Every device write is best-effort and the CLI exits 0; `is_on()` and all state reads are exception-guarded** — a hook must never fail a Claude Code turn.
- `working`/`idle`/etc. are **no-ops when the mode flag is off** (the `claude_mode` flag is the master switch).
- Light logic: prune `working` entries older than TTL (`BUSYLIGHT_CLAUDE_TTL`, default 14400 s); if `focus` set → red iff the focused session is working; else aggregate → red iff any session working.
- Reading `session_id`: from stdin JSON when present; **never block on a tty** (manual run → session id `"manual"`).
- Hooks: `UserPromptSubmit`→working, `Stop`→idle, `SessionStart`→idle, `SessionEnd`→sessionend, each with `"timeout": 5`. Installer stays non-destructive/idempotent; uninstall selective.
- Bundled web UI card is desktop-only; do NOT touch `firmware/data/`. Keep the v1 tray checkbox + mic-suppression working. ruff ≤ 100; keep the full suite green.

**Run tests:** from `presence_helper/`, `& .\.venv\Scripts\python.exe -m pytest tests/<file> -q` (baseline currently 54 passed).

---

## Task V1: Session-aware state + CLI (aggregate + focus + staleness)

**Files:**
- Rewrite: `presence_helper/src/busylight_presence/claude_light.py`
- Rewrite/extend: `presence_helper/tests/test_claude_light.py`

**Interfaces produced:** `state_path()`, `is_on()`, `enable()`, `disable()`, `mark_working(sid)`, `mark_idle(sid)`, `mark_sessionend(sid)`, `set_focus(sid)`, `clear_focus()`, `status() -> dict`, `main(argv)`. (Keeps `enable/disable/is_on` for the tray; replaces v1 `set_working/set_idle`.)

- [ ] **Step 1: Write failing tests** — replace the body of `tests/test_claude_light.py` with:

```python
from __future__ import annotations

import json

import busylight_presence.claude_light as cl


def _use_tmp(tmp_path, monkeypatch, *, on=True):
    monkeypatch.setattr(cl, "flag_path", lambda: tmp_path / "claude_mode")
    monkeypatch.setattr(cl, "state_path", lambda: tmp_path / "claude_state.json")
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
    t = iter([10.0, 20.0, 30.0, 30.0, 30.0])
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


def test_cli_all_subcommands_exit_zero(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "_read_session_id", lambda: "A")
    for sub in ["on", "working", "idle", "sessionend", "focus", "unfocus", "status", "off"]:
        assert cl.main([sub]) == 0
    assert cl.main(["bogus"]) == 2
```

- [ ] **Step 2: Run — expect FAIL** (`mark_working` etc. undefined).
Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_light.py -q`

- [ ] **Step 3: Rewrite `claude_light.py`:**

```python
"""Optional session-aware 'Claude mode': the BusyLight shows red while any
Claude Code session is working and green when all are idle (driven by
Claude Code hooks). A JSON state file tracks per-session working status;
an optional focus binds the light to a single session.

Every device write is best-effort and never raises — a hook must not fail
a Claude Code turn.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from .config import _default_config_path
from .serial_client import SerialClient, find_busylight_ports

_WORKING = "BUSY"       # red solid
_IDLE = "AVAILABLE"     # green solid

# Recording sink for tests; real writes go through _best_effort_set.
_applied: list[str] = []


def _ttl_seconds() -> float:
    try:
        return float(os.environ.get("BUSYLIGHT_CLAUDE_TTL", "14400"))
    except (TypeError, ValueError):
        return 14400.0


def _now() -> float:
    return time.time()


def flag_path() -> Path:
    return _default_config_path().parent / "claude_mode"


def state_path() -> Path:
    return _default_config_path().parent / "claude_state.json"


def is_on() -> bool:
    try:
        return flag_path().exists()
    except Exception:  # noqa: BLE001
        return False


def _best_effort_set(state: str) -> bool:
    try:
        ports = find_busylight_ports()
    except Exception:  # noqa: BLE001
        return False
    for port in ports:
        try:
            SerialClient(port=port).set_state(state)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
        working = data.get("working") if isinstance(data, dict) else None
        if not isinstance(working, dict):
            working = {}
        focus = data.get("focus") if isinstance(data, dict) else None
        return {"working": working, "focus": focus}
    except Exception:  # noqa: BLE001
        return {"working": {}, "focus": None}


def _save_state(state: dict) -> None:
    try:
        p = state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _prune(state: dict) -> dict:
    ttl = _ttl_seconds()
    now = _now()
    state["working"] = {
        sid: ts
        for sid, ts in state["working"].items()
        if isinstance(ts, (int, float)) and (now - ts) <= ttl
    }
    return state


def _read_session_id() -> str:
    """session_id from a hook's stdin JSON; never blocks on a manual (tty)
    run."""
    try:
        stdin = sys.stdin
        if stdin is None or stdin.isatty():
            return "manual"
        raw = stdin.read()
    except Exception:  # noqa: BLE001
        return "manual"
    if not raw:
        return "manual"
    try:
        sid = json.loads(raw).get("session_id")
        return sid if isinstance(sid, str) and sid else "manual"
    except Exception:  # noqa: BLE001
        return "manual"


def _desired_state(state: dict) -> str | None:
    if not is_on():
        return None
    state = _prune(state)
    focus = state.get("focus")
    working = state["working"]
    if focus:
        return _WORKING if focus in working else _IDLE
    return _WORKING if working else _IDLE


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
    _save_state({"working": {}, "focus": None})


def mark_working(sid: str) -> None:
    if not is_on():
        return
    st = _load_state()
    st["working"][sid] = _now()
    _save_state(st)
    _apply(st)


def mark_idle(sid: str) -> None:
    if not is_on():
        return
    st = _load_state()
    st["working"].pop(sid, None)
    _save_state(st)
    _apply(st)


def mark_sessionend(sid: str) -> None:
    if not is_on():
        return
    st = _load_state()
    st["working"].pop(sid, None)
    if st.get("focus") == sid:
        st["focus"] = None
    _save_state(st)
    _apply(st)


def set_focus(sid: str | None) -> str | None:
    st = _prune(_load_state())
    if sid and sid != "manual":
        st["focus"] = sid
    elif st["working"]:
        st["focus"] = max(st["working"], key=lambda k: st["working"][k])
    else:
        st["focus"] = None
    _save_state(st)
    _apply(st)
    return st["focus"]


def clear_focus() -> None:
    st = _load_state()
    st["focus"] = None
    _save_state(st)
    _apply(st)


def status() -> dict:
    st = _prune(_load_state())
    return {"on": is_on(), "working": len(st["working"]), "focus": st.get("focus")}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sub = args[0] if args else "status"
    if sub == "on":
        enable()
    elif sub == "off":
        disable()
    elif sub == "working":
        mark_working(_read_session_id())
    elif sub == "idle":
        mark_idle(_read_session_id())
    elif sub == "sessionend":
        mark_sessionend(_read_session_id())
    elif sub == "focus":
        set_focus(_read_session_id())
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

Note: tests monkeypatch `_best_effort_set` to append to `cl._applied`; the real `_apply` calls `_best_effort_set`, so tests observe the applied color.

- [ ] **Step 4: Run green.** `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_light.py tests/ -q` — the whole suite must stay green (v1's old set_working/set_idle tests are replaced by the above). Expected ~ (54 − 7 old + 10 new).

- [ ] **Step 5: Commit**
```bash
git add presence_helper/src/busylight_presence/claude_light.py presence_helper/tests/test_claude_light.py
git commit -m "feat(claude-mode-v2): session-aware state (aggregate + focus + staleness)"
```

---

## Task V2: Hooks installer — add SessionEnd + timeout

**Files:**
- Modify: `presence_helper/src/busylight_presence/claude_hooks.py`
- Modify: `presence_helper/tests/test_claude_hooks.py`

- [ ] **Step 1: Failing test** — append to `tests/test_claude_hooks.py`:

```python
def test_install_adds_sessionend_and_timeout(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(ch, "hook_command", lambda: "busylight-claude")
    ch.install_hooks(settings)
    data = json.loads(settings.read_text(encoding="utf-8"))
    # SessionEnd wired to `sessionend`
    se = [h["command"] for m in data["hooks"]["SessionEnd"] for h in m["hooks"]]
    assert "busylight-claude sessionend" in se
    # every installed hook has a fast timeout
    for event in ("UserPromptSubmit", "Stop", "SessionStart", "SessionEnd"):
        for m in data["hooks"][event]:
            for h in m["hooks"]:
                assert h.get("timeout") == 5
```

- [ ] **Step 2: Run — expect FAIL** (`SessionEnd` KeyError / no `timeout`).

- [ ] **Step 3: Update `claude_hooks.py`:** extend `_EVENTS` and add the timeout to each hook entry.

```python
_EVENTS = {
    "UserPromptSubmit": "working",
    "Stop": "idle",
    "SessionStart": "idle",
    "SessionEnd": "sessionend",
}
```
In `install_hooks`, change the appended matcher to include the timeout:
```python
        if cmd not in existing:
            matchers.append({"hooks": [
                {"type": "command", "command": cmd, "timeout": 5}
            ]})
```
`uninstall_hooks` already matches by command string, so it removes the new `SessionEnd`/`sessionend` entry too (the `_EVENTS` loop now includes `SessionEnd`) — no other change needed.

- [ ] **Step 4: Run green.** `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_hooks.py tests/ -q`

- [ ] **Step 5: Commit**
```bash
git add presence_helper/src/busylight_presence/claude_hooks.py presence_helper/tests/test_claude_hooks.py
git commit -m "feat(claude-mode-v2): install SessionEnd hook + fast timeout"
```

---

## Task V3: Dashboard card + bridge endpoint

**Files:**
- Modify: `presence_helper/src/busylight_presence/webui_bridge.py` (add `/api/claude-mode` GET+POST)
- Modify: `presence_helper/src/busylight_presence/webui/index.html` (card markup)
- Modify: `presence_helper/src/busylight_presence/webui/app.js` (fetch + wire)
- Modify: `presence_helper/src/busylight_presence/webui/styles.css` (only if needed for the card)
- Test: `presence_helper/tests/test_bridge_claude.py`

- [ ] **Step 1: Failing test**

```python
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
```

- [ ] **Step 2: Run — expect FAIL** (`claude_mode_status`/`claude_mode_action` undefined).

- [ ] **Step 3: Implement the endpoint.** In `webui_bridge.py`, add two module-level helpers (pure, testable) and route them:

```python
# module-level, near the top-level helpers
def claude_mode_status() -> dict:
    from . import claude_light
    return claude_light.status()


def claude_mode_action(action: str) -> dict:
    from . import claude_light
    if action == "on":
        claude_light.enable()
    elif action == "off":
        claude_light.disable()
    elif action == "focus":
        claude_light.set_focus(None)   # most-recently-active
    elif action == "unfocus":
        claude_light.clear_focus()
    return claude_light.status()
```

In `_handle_api_get`, before the final 404, add:
```python
        if path == "/api/claude-mode":
            return self._send_json(200, claude_mode_status())
```
In `_handle_api_post`, before the final 404, add:
```python
        if path == "/api/claude-mode":
            body = self._read_json_body()
            action = (body.get("action") or "").strip()
            return self._send_json(200, claude_mode_action(action))
```

- [ ] **Step 4: Add the dashboard card.** In `webui/index.html`, add a card near the other cards:
```html
<section class="card" id="claude-card">
  <div class="card-head">
    <h2>Claude mode</h2>
    <label class="switch">
      <input type="checkbox" id="claude-toggle" />
      <span class="slider"></span>
    </label>
  </div>
  <p id="claude-status" class="muted">—</p>
  <button id="claude-focus" class="btn-secondary" type="button">Focus current session</button>
</section>
```
In `webui/app.js`, add on load + handlers:
```javascript
async function refreshClaude() {
  try {
    const r = await fetch("/api/claude-mode");
    const s = await r.json();
    document.getElementById("claude-toggle").checked = !!s.on;
    const st = s.on
      ? (s.focus ? `focused on ${s.focus.slice(0,8)}…` :
         (s.working ? `${s.working} session(s) working` : "idle"))
      : "off";
    document.getElementById("claude-status").textContent = st;
  } catch (e) { /* best-effort UI */ }
}
async function claudeAction(action) {
  await fetch("/api/claude-mode", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  refreshClaude();
}
document.getElementById("claude-toggle").addEventListener("change", (e) =>
  claudeAction(e.target.checked ? "on" : "off"));
document.getElementById("claude-focus").addEventListener("click", () =>
  claudeAction("focus"));
refreshClaude();
```
Reuse existing `.card`/`.switch`/`.btn-secondary` styles; only add to `styles.css` if a class is missing. Do NOT edit `firmware/data/`.

- [ ] **Step 5: Run tests + manual check.**
Run: `& .\.venv\Scripts\python.exe -m pytest tests/ -q` (all green).
Manual (once, with device on COM3): launch the tray app, open the dashboard, confirm the Claude mode card toggles the mode and shows working/focus.

- [ ] **Step 6: Commit**
```bash
git add presence_helper/src/busylight_presence/webui_bridge.py presence_helper/src/busylight_presence/webui/index.html presence_helper/src/busylight_presence/webui/app.js presence_helper/src/busylight_presence/webui/styles.css presence_helper/tests/test_bridge_claude.py
git commit -m "feat(claude-mode-v2): dashboard Claude-mode card + bridge endpoint"
```

---

## Spec Coverage Check
- Session-aware aggregate + focus + staleness + stdin session_id → Task V1.
- SessionEnd hook + timeout → Task V2.
- Dashboard card + bridge endpoint → Task V3.

## Notes for the implementer
- Keep `enable`/`disable`/`is_on` names (the tray checkbox from v1 depends on them). Don't touch the tray suppression logic or `firmware/data/`.
- The state file and flag file both live in `config._default_config_path().parent`; tests must monkeypatch `flag_path`/`state_path` to a tmp dir and never touch the real ones.
