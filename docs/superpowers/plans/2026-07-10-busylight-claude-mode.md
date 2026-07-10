# BusyLight "Claude mode" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** An optional mode that makes the BusyLight show red while Claude Code is working and green when it's idle, driven by Claude Code hooks over USB serial, mutually exclusive with the mic-presence.

**Architecture:** A marker file (`claude_mode` in the config dir) is the single shared state. A new `claude_light` module + `busylight-claude` CLI reads it and best-effort sets the device via the existing serial client. Claude Code hooks call `busylight-claude working|idle`. The tray gains a "Claude mode" checkbox, and the poll loop stops driving the LED from the mic while the flag is on (keepalive still runs).

**Tech Stack:** Python 3.10+, existing `serial_client`/`config`, pystray tray, pytest.

## Global Constraints
- Copied from the spec (`docs/superpowers/specs/2026-07-10-busylight-claude-mode-design.md`):
- **`working`/`idle` MUST be best-effort and swallow ALL device errors, exit code 0** — a hook must never fail a Claude Code turn or print noise.
- **`working`/`idle` are no-ops when the flag is absent** — installed hooks are harmless when the mode is OFF.
- State mapping: `working` → `BUSY` (red), `idle` → `AVAILABLE` (green), `on` → set green, `off` → no device write.
- Flag = the file's presence. Location: `config._default_config_path().parent / "claude_mode"`.
- Mutual exclusion: while the flag is present, the poll loop does NOT drive the LED from the mic, but still runs the M1 keepalive.
- `install-hooks` edits `~/.claude/settings.json` non-destructively (back up first, idempotent merge) and `uninstall-hooks` removes only what it added.
- Windows-only desktop; no cloud/remote. ruff line-length ≤ 100. Keep the full `pytest` suite green.

**Run tests:** from `presence_helper/`, `& .\.venv\Scripts\python.exe -m pytest tests/<file> -q` (full suite currently 42 passed).

---

## Task 1: `claude_light` core module + CLI

**Files:**
- Create: `presence_helper/src/busylight_presence/claude_light.py`
- Modify: `presence_helper/src/busylight_presence/main.py` (a `--claude` shortcut for the frozen exe)
- Modify: `presence_helper/pyproject.toml` (console entry point)
- Test: `presence_helper/tests/test_claude_light.py`

**Interfaces produced:** `claude_light.flag_path() -> Path`, `is_on() -> bool`, `enable() -> None`, `disable() -> None`, `set_working() -> None`, `set_idle() -> None`, `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing tests**

```python
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


def test_cli_working_exits_zero_even_with_no_device(tmp_path, monkeypatch):
    _point_flag_at(tmp_path, monkeypatch)
    monkeypatch.setattr(cl, "find_busylight_ports", lambda: [])
    cl.enable()
    assert cl.main(["working"]) == 0
    assert cl.main(["idle"]) == 0
    assert cl.main(["status"]) == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_light.py -q`
Expected: FAIL — `No module named 'busylight_presence.claude_light'`.

- [ ] **Step 3: Implement the module**

```python
# presence_helper/src/busylight_presence/claude_light.py
"""Optional 'Claude mode': the BusyLight shows red while Claude Code is
working and green when it's idle, driven by Claude Code hooks.

A marker file (its presence = mode ON) is the single shared state between
the CLI, the hooks, and the tray/poll loop. Every device write is
best-effort and never raises — a hook must not fail a Claude Code turn.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import _default_config_path
from .serial_client import SerialClient, find_busylight_ports

_WORKING = "BUSY"       # red solid
_IDLE = "AVAILABLE"     # green solid


def flag_path() -> Path:
    return _default_config_path().parent / "claude_mode"


def is_on() -> bool:
    return flag_path().exists()


def _best_effort_set(state: str) -> bool:
    """Set the device state over USB serial. Never raises. Returns True on
    a confirmed set. Iterates candidate ports and takes the first that
    accepts the command (a non-BusyLight adapter rejects it)."""
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


def set_working() -> None:
    if is_on():
        _best_effort_set(_WORKING)


def set_idle() -> None:
    if is_on():
        _best_effort_set(_IDLE)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sub = args[0] if args else "status"
    if sub == "on":
        enable()
    elif sub == "off":
        disable()
    elif sub == "working":
        set_working()
    elif sub == "idle":
        set_idle()
    elif sub == "status":
        print("on" if is_on() else "off")
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

(`claude_hooks` is created in Task 3; the two `install-hooks`/`uninstall-hooks` branches import it lazily so Task 1's tests don't need it.)

- [ ] **Step 4: Wire the frozen-exe shortcut in main.py**

Add these as the **first lines of `main(argv)`**, BEFORE the argument parser runs (so the main parser never sees `--claude`). `sys` is already imported in `main.py`:

```python
    _argv = list(sys.argv[1:] if argv is None else argv)
    if _argv and _argv[0] == "--claude":
        from .claude_light import main as _claude_main
        return _claude_main(_argv[1:])
```

- [ ] **Step 5: Add the console entry point**

In `pyproject.toml` under `[project.scripts]`, add:

```toml
busylight-claude = "busylight_presence.claude_light:main"
```

- [ ] **Step 6: Run tests green + commit**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_light.py tests/ -q`
Expected: PASS (47 = 42 + 5).

```bash
git add presence_helper/src/busylight_presence/claude_light.py presence_helper/src/busylight_presence/main.py presence_helper/pyproject.toml presence_helper/tests/test_claude_light.py
git commit -m "feat(claude-mode): claude_light module + busylight-claude CLI"
```

---

## Task 2: Tray toggle + mic-presence suppression

**Files:**
- Modify: `presence_helper/src/busylight_presence/tray.py` (menu item + poll-loop gate)
- Test: `presence_helper/tests/test_claude_suppression.py`

**Interfaces consumed:** `claude_light.is_on/enable/disable` (Task 1).

- [ ] **Step 1: Write the failing test**

Refactor the poll-loop decision into a tiny pure helper so it's testable, then test it.

```python
# presence_helper/tests/test_claude_suppression.py
from __future__ import annotations

from busylight_presence.tray import _should_drive_from_mic


def test_drives_from_mic_when_normal():
    assert _should_drive_from_mic(paused=False, claude_on=False) is True


def test_no_mic_drive_when_paused():
    assert _should_drive_from_mic(paused=True, claude_on=False) is False


def test_no_mic_drive_in_claude_mode():
    assert _should_drive_from_mic(paused=False, claude_on=True) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_suppression.py -q`
Expected: FAIL — `_should_drive_from_mic` not defined.

- [ ] **Step 3: Implement**

In `tray.py`, add the import near the others:

```python
from . import claude_light
```

Add a module-level pure helper (above the class):

```python
def _should_drive_from_mic(*, paused: bool, claude_on: bool) -> bool:
    # The mic drives the LED only in normal mode: not while paused and not
    # while Claude mode owns the light.
    return not paused and not claude_on
```

Rewrite the `_poll_forever` loop body so it uses the helper and keeps the keepalive alive in both the paused and Claude-mode cases:

```python
        while not self._stop_event.is_set():
            if _should_drive_from_mic(paused=self._paused, claude_on=claude_light.is_on()):
                try:
                    self._loop.tick()
                except Exception as e:  # noqa: BLE001
                    log.exception("tick error: %s", e)
            elif not WebUiBridge.suspended:
                # Paused or Claude mode: don't drive from the mic, but keep
                # the firmware's host-present signal alive. Never during OTA.
                self._loop.keepalive()
            self._refresh_icon()
            <keep the existing sleep/wait line unchanged>
```

Add the tray menu item (next to the "Start at login" item in `run()`):

```python
            Item(
                "Claude mode",
                self._toggle_claude,
                checked=lambda _i: claude_light.is_on(),
            ),
```

Add the handler method to `TrayApp`:

```python
    def _toggle_claude(self, _icon, _item) -> None:
        if claude_light.is_on():
            claude_light.disable()
        else:
            claude_light.enable()
```

- [ ] **Step 4: Run tests green + commit**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (50 = 47 + 3).

```bash
git add presence_helper/src/busylight_presence/tray.py presence_helper/tests/test_claude_suppression.py
git commit -m "feat(claude-mode): tray toggle + suppress mic-presence while Claude mode is on"
```

---

## Task 3: Hook install/uninstall + docs

**Files:**
- Create: `presence_helper/src/busylight_presence/claude_hooks.py`
- Test: `presence_helper/tests/test_claude_hooks.py`
- Modify: `presence_helper/README.md` (Claude mode section with the manual snippet)

**Interfaces produced:** `claude_hooks.settings_path() -> Path`, `hook_command() -> str`, `install_hooks(path: Path | None = None) -> None`, `uninstall_hooks(path: Path | None = None) -> None`.

- [ ] **Step 1: Write failing tests**

```python
# presence_helper/tests/test_claude_hooks.py
from __future__ import annotations

import json

import busylight_presence.claude_hooks as ch


def test_install_is_idempotent_and_nondestructive(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "sonnet", "hooks": {}}), encoding="utf-8")
    monkeypatch.setattr(ch, "hook_command", lambda: "busylight-claude")

    ch.install_hooks(settings)
    ch.install_hooks(settings)  # twice -> no duplicates

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["model"] == "sonnet"                       # preserved
    ups = data["hooks"]["UserPromptSubmit"]
    cmds = [h["command"] for m in ups for h in m["hooks"]]
    assert cmds.count("busylight-claude working") == 1     # idempotent
    assert (settings.parent / "settings.json.busylight.bak").exists()  # backup


def test_uninstall_removes_only_our_hooks(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "other-tool"}]}]
    }}), encoding="utf-8")
    monkeypatch.setattr(ch, "hook_command", lambda: "busylight-claude")

    ch.install_hooks(settings)
    ch.uninstall_hooks(settings)

    data = json.loads(settings.read_text(encoding="utf-8"))
    stop_cmds = [h["command"] for m in data["hooks"].get("Stop", []) for h in m["hooks"]]
    assert "other-tool" in stop_cmds                       # foreign hook kept
    assert "busylight-claude idle" not in stop_cmds        # ours removed
    assert "UserPromptSubmit" not in data["hooks"] or not data["hooks"]["UserPromptSubmit"]
```

- [ ] **Step 2: Run to verify failure**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_claude_hooks.py -q`
Expected: FAIL — `No module named 'busylight_presence.claude_hooks'`.

- [ ] **Step 3: Implement**

```python
# presence_helper/src/busylight_presence/claude_hooks.py
"""Install/uninstall the Claude Code hooks that drive Claude mode.

Non-destructive: backs up settings.json, merges idempotently, and only
removes the entries it added.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# event -> the busylight-claude subcommand it runs
_EVENTS = {
    "UserPromptSubmit": "working",
    "Stop": "idle",
    "SessionStart": "idle",
}


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def hook_command() -> str:
    """The command a hook runs, resolved for this install."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --claude'
    return f'"{sys.executable}" -m busylight_presence.claude_light'


def _full_command(sub: str) -> str:
    return f"{hook_command()} {sub}"


def _load(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def install_hooks(path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        (path.parent / (path.name + ".busylight.bak")).write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    for event, sub in _EVENTS.items():
        cmd = _full_command(sub)
        matchers = hooks.setdefault(event, [])
        existing = [h["command"] for m in matchers for h in m.get("hooks", [])]
        if cmd not in existing:
            matchers.append({"hooks": [{"type": "command", "command": cmd}]})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def uninstall_hooks(path: Path | None = None) -> None:
    path = path or settings_path()
    data = _load(path)
    hooks = data.get("hooks", {})
    ours = {_full_command(sub) for sub in _EVENTS.values()}
    for event in list(_EVENTS):
        matchers = hooks.get(event)
        if not matchers:
            continue
        kept = []
        for m in matchers:
            m["hooks"] = [h for h in m.get("hooks", []) if h.get("command") not in ours]
            if m["hooks"]:
                kept.append(m)
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Docs**

Add a "Claude mode (optional)" section to `presence_helper/README.md` describing: `busylight-claude on/off`, the tray toggle, `busylight-claude install-hooks` (and the manual settings.json snippet), and that red=working / green=idle over USB.

- [ ] **Step 5: Run tests green + commit**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (52 = 50 + 2).

```bash
git add presence_helper/src/busylight_presence/claude_hooks.py presence_helper/tests/test_claude_hooks.py presence_helper/README.md
git commit -m "feat(claude-mode): install/uninstall Claude Code hooks + docs"
```

---

## Spec Coverage Check
- CLI on/off/working/idle/status → Task 1. Frozen `--claude` + entry point → Task 1.
- Best-effort/no-op/exit-0 semantics → Task 1 (tests).
- Tray toggle + mic-suppression (keepalive preserved) → Task 2.
- Hook install/uninstall (non-destructive, idempotent) + docs → Task 3.

## Notes for the implementer
- The device serial round-trip needs a real BusyLight on COM3 to *see* the LED, but all tests are host-only (fakes/tmp) — no device required. Manual verification (hooks → red/green) is a follow-up once the device is on hand.
- Do not change the M1 keepalive/OTA-suspend logic; Task 2 only adds `claude_light.is_on()` to the existing gate and keeps the keepalive path.
