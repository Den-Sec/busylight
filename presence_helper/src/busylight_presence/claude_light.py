"""Optional session-aware 'Claude mode': the BusyLight shows red while any
Claude Code session is working and green when all are idle (driven by
Claude Code hooks). A JSON state file tracks per-session working status;
an optional focus binds the light to a single session.

Every device write is best-effort and never raises — a hook must not fail
a Claude Code turn.
"""

from __future__ import annotations

import contextlib
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


def _lock_path() -> Path:
    return _default_config_path().parent / "claude_state.lock"


@contextlib.contextmanager
def _state_lock():
    """Best-effort cross-process lock around the state read-modify-write.
    Never blocks a hook: after a short spin it proceeds unlocked, and it
    steals a stale lock (an orphan left by a crashed process)."""
    lock = _lock_path()
    fd = None
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    # Use the wall clock directly (not _now(), which tests monkeypatch to a
    # finite sequence for business-logic timestamps) for lock spin timing.
    deadline = time.time() + 1.0  # spin at most ~1s
    while fd is None and time.time() < deadline:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # Steal a stale lock (older than 10s) left by a dead process.
            try:
                if time.time() - os.path.getmtime(lock) > 10.0:
                    os.unlink(lock)
                    continue
            except OSError:
                pass
            time.sleep(0.02)
        except OSError:
            break  # can't lock here — proceed unlocked (best-effort)
    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(lock)
            except OSError:
                pass


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
        raw = data.get("sessions") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return {"sessions": {}, "focus": None}
        sessions: dict = {}
        for sid, v in raw.items():
            if isinstance(v, dict) and isinstance(v.get("ts"), (int, float)):
                sessions[sid] = {
                    "cwd": v.get("cwd") if isinstance(v.get("cwd"), str) else None,
                    "status": "working" if v.get("status") == "working" else "idle",
                    "ts": v["ts"],
                }
        focus = data.get("focus")
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
