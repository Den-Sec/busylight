# BusyLight "Claude mode v2" Design Spec

Date: 2026-07-13
Owner: Dennis Sepede
Status: Approved for planning
Depends on: v1 "Claude mode" (merged to `main`). Branch: `claude-mode-v2` off `main`.

## 1. Goal

Fix the two gaps found while using v1:
1. **Multiple concurrent Claude Code sessions** — v1 is *last-writer-wins*: with 2+ chats, one session's `Stop` turns the light green while another is still working. v2 makes the light **session-aware**: **red while ANY session is working, green only when all are idle** (aggregate), with an optional **focus** to bind the light to a single session.
2. **No UI to toggle Claude mode** — v1's toggle lives only in the tray right-click menu. v2 adds a **"Claude mode" card to the dashboard** the desktop app serves locally.

Confirmed hook mechanics (Claude Code docs): every hook receives a JSON object on **stdin** including a unique **`session_id`** (stable across `--resume`); `Stop` fires once per assistant turn; `SessionEnd` exists and carries the session; all concurrent sessions fire hooks independently in parallel. Hooks must exit 0 (non-blocking) and be fast (`UserPromptSubmit` has a 30 s cap → we set `timeout: 5`).

## 2. Approved decisions
- **Multi-session:** aggregate (red if any working) **+ optional `focus`** command.
- **UI home:** a card in the desktop-bundled dashboard (the web UI served by the bridge). The firmware's own web UI copy stays clean — intentional, desktop-only divergence.
- Out of scope for v2 (future nicety): using the `Notification` hook for a distinct "waiting for you" pattern.

## 3. State model

A single JSON state file `%APPDATA%\BusyLight\claude_state.json` (via `config._default_config_path().parent`):
```json
{ "working": { "<session_id>": <epoch_seconds>, ... }, "focus": "<session_id>" | null }
```
- `working` — map of session_id → timestamp of its last `working` event. **Present = that session is currently working.**
- `focus` — optional session id the light is bound to.
- The v1 **mode flag** file `claude_mode` remains the master on/off switch. When the mode is OFF, every command is a no-op (unchanged from v1). The state file is only consulted while the mode is on.

**Staleness self-heal:** when computing the light, ignore `working` entries older than a TTL (`BUSYLIGHT_CLAUDE_TTL`, default 14400 s = 4 h) so a session that crashed without firing `Stop`/`SessionEnd` cannot leave the light stuck red forever.

## 4. CLI (`busylight-claude` / `... --claude`)

Reads `session_id` from stdin JSON **when present** (hook invocation); on a manual run (`sys.stdin.isatty()` or unparseable) falls back to session id `"manual"` and never blocks on stdin.

- `working` — `working[sid] = now`; recompute + apply light.
- `idle` — `working.pop(sid, None)`; recompute + apply.
- `sessionend` — `working.pop(sid, None)`; if `focus == sid`, clear focus; recompute + apply.
- `focus` — set `focus` to the **most-recently-active** session (the `sid` from stdin if present, else the max-timestamp entry in `working`); recompute + apply. If nothing is active, leave `focus = None` and print a hint. (A manually-run command can't know its own session id, so "most-recently-active" is the pragmatic binding — run it right after the chat you care about does something.)
- `unfocus` — `focus = None`; recompute + apply.
- `on` / `off` — create/remove the mode flag (unchanged from v1); `off` also clears the state file. `on` applies green.
- `status` — print `on|off`, working count, focus.
- `install-hooks` / `uninstall-hooks` — see §6.

**All device writes stay best-effort and exit 0; `is_on()` and every state read are exception-guarded** so a hook can never fail a Claude Code turn (v1 invariant preserved).

### Light computation `_desired_state() -> "BUSY" | "AVAILABLE" | None`
1. If `not is_on()` → `None` (no-op).
2. Prune stale `working` entries (older than TTL).
3. If `focus` is set: `BUSY` if `focus` in (pruned) `working` else `AVAILABLE`.
4. Else (aggregate): `BUSY` if any `working` else `AVAILABLE`.
Apply via the existing best-effort serial `set_state`.

## 5. Dashboard card + bridge endpoint

### Bridge (`webui_bridge.py`) — new local endpoint, no serial needed
- `GET /api/claude-mode` → `{ "on": bool, "working": <int>, "focus": <str|null> }` (from `claude_light`).
- `POST /api/claude-mode` with body `{ "action": "on"|"off"|"focus"|"unfocus" }` → performs it via `claude_light` and returns the new status. Routed in `_handle_api_get`/`_handle_api_post` alongside the existing `/api/*` handlers; uses `_send_json`/`_read_json_body`.

### Bundled web UI (`webui/index.html`, `app.js`, `styles.css`) — desktop copy only
- A **"Claude mode" card**: a toggle (on/off), a status line ("N session(s) working" / "idle"), and a **Focus / Unfocus** button. On load it GETs `/api/claude-mode`; the toggle and focus button POST to it, then refresh. Styled to match the existing cards. The firmware's `firmware/data/` copy is **not** touched.

## 6. Hooks (updated installer)

`install-hooks` writes these into `~/.claude/settings.json` (non-destructive/idempotent, as v1), each with `"timeout": 5`:
- `UserPromptSubmit` → `<cmd> working`
- `Stop` → `<cmd> idle`
- `SessionStart` → `<cmd> idle`
- `SessionEnd` → `<cmd> sessionend`  ← new in v2 (cleans up a closed session so the light doesn't stay red)

`uninstall-hooks` removes only the four entries it added (matched by command). Existing/foreign hooks are preserved.

## 7. Testing
- CLI/state (host-only, tmp state dir, fake transport): aggregate red-if-any / green-when-all-idle across 2 sessions; `sessionend` removal; staleness pruning; `focus`/`unfocus` binding; stdin `session_id` parsing vs manual fallback (no block on a tty); every command exits 0 even with no device; mode-off no-ops.
- Hooks: install now includes `SessionEnd` + `timeout:5`; still non-destructive/idempotent; uninstall selective.
- Bridge: `GET/POST /api/claude-mode` return/act correctly with `claude_light` monkeypatched; no serial required.
- Manual: open the dashboard → the card toggles Claude mode and shows working/focus; two real Claude Code sessions → light red while either works, green only when both idle.

## 8. Risks / notes
- **Focus binding** targets the most-recently-active session (a manual command can't self-identify its session). Documented; `SessionEnd` clears a focus whose session closed.
- **Web UI divergence:** the bundled copy gains a card the firmware copy lacks — intentional and one-directional (desktop-only feature).
- **Stuck-red** on a crashed session is bounded by the TTL prune + `SessionEnd`.
- Backward compatible: the v1 tray checkbox (`enable`/`disable`/`is_on`) and mic-suppression are unchanged; v1's `set_working`/`set_idle` are reshaped into the session-aware path (v1 tests updated accordingly).

## 9. Acceptance
1. Two Claude Code sessions: light is red while *either* is working and green only when *both* are idle; closing a terminal (SessionEnd) or a crashed session (TTL) doesn't strand it red.
2. `busylight-claude focus` binds the light to the active session; `unfocus` restores aggregate.
3. The dashboard "Claude mode" card toggles the mode and shows working/focus status.
4. Hooks install with `SessionEnd` + `timeout:5`, non-destructively; every hook exits 0.
5. Full `pytest` suite green.
