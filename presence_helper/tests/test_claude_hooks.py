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
