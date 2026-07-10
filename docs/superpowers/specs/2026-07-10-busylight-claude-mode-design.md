# BusyLight "Claude mode" Design Spec

Date: 2026-07-10
Owner: Dennis Sepede
Status: Approved for planning
Depends on: the M1 branch (`m1-always-on-roaming`) — this feature branches off it because it touches `presence_helper`.

## 1. Goal and scope

An **optional** mode that turns the BusyLight into a live indicator of **Claude Code activity**: **red while Claude is working, green when Claude is idle/done.**

Owner's key decision: this is a **mode**, mutually exclusive with the normal busy-light behaviour. While Claude mode is ON, the device is dedicated to Claude — the microphone-driven presence does **not** drive the LED. While OFF, everything behaves exactly as today. Opt-in; if you never enable it, nothing changes.

Driven by **Claude Code hooks** (not by "detecting" Claude — there is no reliable signal to spy on): the hooks fire on Claude Code's own lifecycle events and call a tiny CLI that sets the device state over **USB serial** (no Wi-Fi required).

### In scope
- A mode flag + `busylight-claude` CLI (`on` / `off` / `working` / `idle`).
- A tray checkbox "Claude mode" in the desktop app.
- Claude Code hook snippet + an install/uninstall helper.
- Mic-presence suppression while Claude mode is ON.
- Tests + short docs.

### Out of scope
- Detecting claude.ai in a browser or the Claude desktop app (no lifecycle signal). This is Claude **Code** only.
- Reacting to individual tools / streaming tokens. Granularity is per-turn (prompt → working, stop → idle).
- Multi-machine / remote. Local USB serial only (HTTP is a possible later fallback).

## 2. State semantics (owner-approved)

Claude mode is a dedicated mode, so there is **no "restore previous state"**:
- `working` → **BUSY (red solid)**.
- `idle` → **AVAILABLE (green solid)**.
- Turning the mode `on` → set green immediately (idle baseline).
- Turning the mode `off` → remove the flag and hand control back to normal (the mic-presence loop resumes and sets its own state on the next tick). Do not force any state on `off`.

## 3. Components

### 3.1 Mode flag
- A marker file `claude_mode` under the config dir (reuse `config._default_config_path().parent`, i.e. `%APPDATA%\BusyLight\claude_mode` on Windows). **Present = ON.**
- Rationale: a file is trivially shared between the CLI, the hooks, and the tray/poll loop across separate processes, with no IPC.

### 3.2 `busylight-claude` CLI (new module `busylight_presence/claude_light.py`)
Subcommands:
- `on` — create the flag; best-effort set the device **green**.
- `off` — remove the flag. (No device write.)
- `working` — if the flag is present, best-effort set the device **red**; else **no-op** (exit 0).
- `idle` — if the flag is present, best-effort set the device **green**; else **no-op** (exit 0).
- `status` — print `on`/`off` (for scripts).
- `install-hooks` / `uninstall-hooks` — add/remove the two hooks in `~/.claude/settings.json` (see §3.4).

Device access reuses the existing serial transport (`serial_client.find_busylight_ports` + `SerialClient.set_state`, or `BusyLightTransport`). **Every device write is best-effort and swallows all errors** — a hook must never fail a Claude Code turn or print noise. Exit code is always 0 for `working`/`idle`.

Exposed as a console entry point `busylight-claude` in `pyproject.toml`, and reachable in the frozen build via `BusyLightPresence.exe --claude <sub>` (a thin arg path in `main.py`) so distribution doesn't need a second exe.

### 3.3 Tray toggle
- A tray checkbox **"Claude mode"** in `tray.py`.
- `checked` reflects the flag's presence.
- Toggling calls the same on/off logic (`claude_light.enable()` / `disable()`).

### 3.4 Claude Code hooks (opt-in)
Snippet merged into the user's `~/.claude/settings.json`:
```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "<busylight-claude> working" }] }],
    "Stop":             [{ "hooks": [{ "type": "command", "command": "<busylight-claude> idle" }] }],
    "SessionStart":     [{ "hooks": [{ "type": "command", "command": "<busylight-claude> idle" }] }]
  }
}
```
- `<busylight-claude>` resolves to the console entry point (dev venv) or `"<path>\BusyLightPresence.exe" --claude` (frozen).
- `install-hooks` merges these **non-destructively** (preserves any existing hooks/settings; idempotent — running twice does not duplicate). `uninstall-hooks` removes only the entries it added.
- Because `working`/`idle` no-op when the flag is off, **installed hooks are harmless when Claude mode is OFF** — the light only reacts once you toggle the mode on.

### 3.5 Mic-presence suppression
- In the desktop poll loop (`main.py::PresenceLoop.tick` / the `tray._poll_forever` path), when the Claude-mode flag is present, **do not drive the LED from the mic** — skip the mic→state logic but keep the serial **keepalive** alive (so the firmware's host-present signal stays fresh, per M1). This makes the device truly Claude-only while the mode is on.
- When the flag is absent, behaviour is exactly as today.

## 4. Architecture / data flow

```
Claude Code turn ──hook──> busylight-claude working ─┐
                                                     ├─(flag ON?)─> SerialClient.set_state(BUSY/AVAILABLE) ──USB──> device LED
Claude Code stop ──hook──> busylight-claude idle    ─┘
Tray "Claude mode" toggle ──> create/remove flag ──> poll loop stops driving from mic (keepalive only)
```

No new IPC: the flag file is the single shared piece of state; the device is the shared sink (open-write-close serial handles contention with the tray/keepalive).

## 5. Testing

- `claude_light`: `working`/`idle` are no-ops when the flag is absent (no device call); when present they call `set_state` with the right state; all device errors are swallowed and exit code is 0. `on` creates the flag + attempts green; `off` removes it. (Unit tests with a fake transport + tmp flag dir.)
- `install-hooks`/`uninstall-hooks`: merge into a tmp settings.json without clobbering existing keys; idempotent; uninstall removes only what it added. (Unit tests on a tmp file.)
- Tray toggle + mic-suppression: the poll loop, when the flag is present, does not call the mic→state path but still calls keepalive (unit-test the decision, mirroring the M1 keepalive test).
- Manual: install hooks, toggle Claude mode on, run a Claude Code turn → device goes red then green; toggle off → mic-presence resumes.

## 6. Risks / notes

- **Hook command resolution across environments** (dev venv vs frozen exe vs PATH). Mitigation: `install-hooks` writes the concrete command for the current install; docs show the manual snippet for both.
- **Editing the user's `~/.claude/settings.json`** is sensitive. Mitigation: non-destructive JSON merge, back up the file before writing, idempotent, and `uninstall-hooks` restores cleanly; also offer the manual snippet so the user can opt out of auto-editing.
- **Concurrent Claude Code sessions** (e.g. subagents/workflows) each fire Stop/UserPromptSubmit — last-writer-wins on the LED, which is acceptable for an indicator.
- **Contention on COM3** between the hook write, the tray keepalive, and the desktop app: handled by the existing open-write-close + retry model.

## 7. Acceptance

Claude mode is done when:
1. `busylight-claude on` turns the light green and suppresses mic-presence; `off` restores normal behaviour.
2. With the mode on and the hooks installed, a Claude Code turn drives the light **red → green**; with the mode off, the hooks are silent no-ops.
3. The tray "Claude mode" checkbox reflects and flips the mode.
4. `install-hooks`/`uninstall-hooks` edit `~/.claude/settings.json` non-destructively and idempotently.
5. The full `pytest` suite stays green.
