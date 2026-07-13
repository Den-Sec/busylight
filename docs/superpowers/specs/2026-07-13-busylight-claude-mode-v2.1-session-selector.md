# BusyLight "Claude mode v2.1" — session selector

Date: 2026-07-13
Owner: Dennis Sepede
Status: Approved for planning
Depends on: v2 (merged). Branch: `claude-mode-v2.1` off `main`.

## 1. Why
The v2 "Focus current session" button is confusing and usually a no-op: it binds the light to whatever session is working **at the instant you click**, so clicking it from the dashboard (when nothing is mid-work) does nothing, and even when it works it shows an opaque session UUID. Replace it with a real **dropdown selector** of your open Claude Code sessions, **labeled by project folder**, so you can *choose* which session drives the light — with "All sessions (aggregate)" as the default.

Enabled by: Claude Code hooks pass `cwd` (the project folder) on stdin, so we can label sessions meaningfully.

## 2. State model (changed)
`claude_state.json` becomes a **session registry**:
```json
{
  "sessions": {
    "<session_id>": {"cwd": "<abs path>", "status": "working" | "idle", "ts": <epoch>}
  },
  "focus": "<session_id>" | null
}
```
- A session is registered/updated on any hook (working/idle) with its `cwd`.
- Kept while the terminal is open (idle sessions stay listed so they're selectable); removed on `SessionEnd`; pruned when `ts` is older than the TTL (`BUSYLIGHT_CLAUDE_TTL`, default 4 h) to self-heal a crashed session.
- `_load_state` tolerates any old/invalid shape → `{"sessions": {}, "focus": null}` (the state file is ephemeral; no migration needed).

## 3. Light logic
`_desired_state`, after pruning:
- If `focus` is set AND that session is still registered → **red iff its status == "working"**, else green.
- If `focus` is set but the session is gone → fall back to aggregate.
- Aggregate (no focus) → **red iff ANY registered session has status == "working"**, else green.

## 4. Hooks / CLI
- `_read_hook_input() -> (sid, cwd)`: parse `session_id` and `cwd` from stdin JSON; never blocks on a tty (manual → `("manual", None)`).
- `mark_working(sid, cwd)` → upsert session `status="working"`.
- `mark_idle(sid, cwd)` → upsert session `status="idle"` (keep it listed).
- `mark_sessionend(sid)` → remove the session; clear focus if it was focused.
- `set_focus(sid)` → focus a specific session id (the dropdown supplies a real id). `clear_focus()` → aggregate.
- CLI subcommands unchanged in name (`working`/`idle`/`sessionend`/`focus`/`unfocus`/`status`/`on`/`off`/install-hooks/uninstall-hooks); `working`/`idle` now also capture `cwd`. `focus` accepts an optional positional session id for scripting.
- Best-effort / exit-0 / `is_on()`-never-raises invariants preserved; all writes under the existing best-effort file lock + atomic save.

## 5. status() (richer) + labels
`status()` returns:
```json
{
  "on": bool,
  "focus": "<sid>" | null,
  "working": <count of sessions with status "working">,
  "sessions": [
    {"id": "<sid>", "label": "<folder>" or "<folder> (<sid[:4]>)", "cwd": "...", "status": "working"|"idle"}
  ]
}
```
- `label` = the folder basename of `cwd` (or `"session"` if no cwd). If two or more listed sessions share the same basename, disambiguate by appending ` (<sid[:4]>)`. Sessions sorted by `ts` desc (most-recent first).

## 6. Bridge + UI
- `GET /api/claude-mode` → `status()` (now includes `sessions`).
- `POST /api/claude-mode` body `{action, session?}`:
  - `on`/`off` as before.
  - `focus` with `session=<sid>` → `set_focus(sid)`.
  - `unfocus` (or `focus` with empty/absent session) → `clear_focus()`.
- **UI:** replace the "Focus current session" button with a `<select>` in the Claude-mode card:
  - option `""` → "All sessions (aggregate)" (default);
  - one option per session: `<label> — <status>`, `value=<sid>`.
  - On change → POST `focus`(sid) or `unfocus` (empty). `refreshClaude()` repopulates the dropdown from `s.sessions` and sets the selected option to `s.focus`.
  - Remove the old button + its handler.

## 7. Testing
- `claude_light`: two sessions with cwds → aggregate red if either works, green when both idle; focus a specific session → light follows only it; sessionend removes + unfocuses; prune by TTL; label collision (same folder) disambiguated; `_read_hook_input` parses sid+cwd and manual-tty fallback; every subcommand exits 0; no-op when mode off; best-effort lock preserved (mutation under lock).
- Bridge: `status` returns sessions; `focus` action with a session id sets focus; `unfocus`/empty clears; no serial needed.
- Manual: dashboard shows the dropdown with your open sessions by folder; selecting one binds the light; "All" returns to aggregate. (Restart the tray app first — it caches web assets in-process.)

## 8. Risks / notes
- Two sessions in the same folder are disambiguated by a short id suffix; still readable.
- The dashboard's bundled web UI diverges from the firmware copy (intentional, desktop-only) — unchanged from v2.
- The in-process asset cache means the running tray app must be restarted to serve the new dashboard (known; a fresh process/ auto-update relaunch picks it up).

## 9. Acceptance
1. The Claude-mode card shows a **dropdown of open sessions labeled by project folder**, default "All sessions (aggregate)".
2. Selecting a session binds the light to it (red only while THAT session works); "All" restores aggregate.
3. Closing a terminal (SessionEnd) drops it from the list and clears focus if it was focused.
4. Full pytest suite green.
