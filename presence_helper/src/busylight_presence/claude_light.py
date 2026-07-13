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
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, p)
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
    with _state_lock():
        _save_state({"working": {}, "focus": None})


def mark_working(sid: str) -> None:
    if not is_on():
        return
    with _state_lock():
        st = _load_state()
        st["working"][sid] = _now()
        _save_state(st)
    _apply(st)


def mark_idle(sid: str) -> None:
    if not is_on():
        return
    with _state_lock():
        st = _load_state()
        st["working"].pop(sid, None)
        _save_state(st)
    _apply(st)


def mark_sessionend(sid: str) -> None:
    if not is_on():
        return
    with _state_lock():
        st = _load_state()
        st["working"].pop(sid, None)
        if st.get("focus") == sid:
            st["focus"] = None
        _save_state(st)
    _apply(st)


def set_focus(sid: str | None) -> str | None:
    with _state_lock():
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
    with _state_lock():
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
