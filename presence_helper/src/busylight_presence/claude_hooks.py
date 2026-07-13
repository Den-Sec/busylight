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
    "SessionEnd": "sessionend",
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
            matchers.append({"hooks": [{"type": "command", "command": cmd, "timeout": 5}]})
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
