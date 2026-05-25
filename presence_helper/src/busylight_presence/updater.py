"""Auto-update via GitHub releases.

Polls the public `Den-Sec/busylight` releases endpoint every few hours
and exposes a tiny API for the tray:

  - `fetch_latest_release()` -> `LatestRelease | None`
  - `is_newer(latest, current)` -> bool
  - `download_exe(release, dest_dir)` -> Path
  - `install_and_restart(new_exe)` -> never returns

The replace-myself dance on Windows uses a one-shot .bat helper:
PyInstaller-frozen exes can't overwrite themselves while running, so
we spawn `cmd.exe /c <bat>` which waits 2 s, moves the new exe into
place, relaunches it, then deletes itself.

No GitHub token is needed because the repo is public (decision logged
2026-05-24).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


GITHUB_OWNER = "Den-Sec"
GITHUB_REPO = "busylight"
RELEASES_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)


@dataclass
class ReleaseAsset:
    name: str
    url: str
    size: int


@dataclass
class LatestRelease:
    tag: str            # e.g. "v0.4.0"
    version: str        # e.g. "0.4.0"
    html_url: str       # release page
    notes: str          # release body / changelog
    exe_asset: Optional[ReleaseAsset]
    firmware_asset: Optional[ReleaseAsset]
    signature_asset: Optional[ReleaseAsset]


def fetch_latest_release(timeout_s: float = 8.0) -> Optional[LatestRelease]:
    """Hit the GitHub releases API. Returns None on network errors."""
    req = urllib.request.Request(
        RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"busylight-presence/{_self_version()}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        log.warning("release check HTTP %s: %s", e.code, e.reason)
        return None
    except urllib.error.URLError as e:
        log.info("release check unavailable: %s", e)
        return None
    except (TimeoutError, OSError, json.JSONDecodeError) as e:
        log.info("release check failed: %s", e)
        return None

    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        return None
    version = tag.lstrip("v")

    exe_asset = _pick_asset(data, lambda n: n.lower() == "busylightpresence.exe")
    fw_asset = _pick_asset(
        data,
        lambda n: n.lower().endswith(".bin") and "firmware" in n.lower(),
    )
    sig_asset = _pick_asset(
        data,
        lambda n: n.lower().endswith(".sig") and "firmware" in n.lower(),
    )

    return LatestRelease(
        tag=tag,
        version=version,
        html_url=str(data.get("html_url") or ""),
        notes=str(data.get("body") or ""),
        exe_asset=exe_asset,
        firmware_asset=fw_asset,
        signature_asset=sig_asset,
    )


def _pick_asset(release_json: dict, match) -> Optional[ReleaseAsset]:
    for a in release_json.get("assets") or []:
        name = a.get("name") or ""
        if match(name):
            return ReleaseAsset(
                name=name,
                url=a.get("browser_download_url") or "",
                size=int(a.get("size") or 0),
            )
    return None


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?")


def is_newer(latest_version: str, current_version: str) -> bool:
    """True iff `latest_version` is strictly greater than `current_version`.

    Handles bare semver `X.Y.Z` plus an optional `-rc1` / `+build` suffix
    by ignoring everything after the patch number. That's good enough for
    BusyLight's release cadence.
    """
    a = _parse_version(latest_version)
    b = _parse_version(current_version)
    return a > b


def _parse_version(s: str) -> tuple[int, int, int]:
    m = _VERSION_RE.search(s)
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# ---------------------------------------------------------------------------
# Download + self-replace
# ---------------------------------------------------------------------------

def download_exe(
    release: LatestRelease,
    dest_dir: Optional[Path] = None,
    progress_cb=None,
) -> Path:
    """Download the BusyLightPresence.exe asset to a temp location.

    `progress_cb(written, total)` is called as bytes arrive, so the
    caller can drive a progress bar. Total is taken from the
    Content-Length header (or the asset metadata as a fallback).
    """
    if release.exe_asset is None:
        raise RuntimeError("release has no BusyLightPresence.exe asset")
    if dest_dir is None:
        dest_dir = Path(tempfile.gettempdir()) / "busylight-update"
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"BusyLightPresence-{release.version}.exe"

    req = urllib.request.Request(
        release.exe_asset.url,
        headers={"User-Agent": f"busylight-presence/{_self_version()}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        # Prefer the server-reported Content-Length; fall back to the
        # asset metadata GitHub provides if it's missing.
        total = (
            int(resp.headers.get("Content-Length") or 0)
            or release.exe_asset.size
            or 0
        )
        written = 0
        with open(target, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                if progress_cb:
                    try:
                        progress_cb(written, total)
                    except Exception:  # noqa: BLE001
                        pass
    log.info("downloaded %s (%d bytes)", target, target.stat().st_size)
    return target


def install_and_restart(new_exe: Path) -> None:
    """Replace the currently-running exe with `new_exe` and relaunch.

    Windows only. Spawns a detached `cmd /c <bat>` and exits the current
    process — the .bat then waits, moves the file, restarts, and deletes
    itself.
    """
    if sys.platform != "win32":
        raise RuntimeError("auto-install is Windows-only")
    current = _running_exe_path()
    if current is None:
        raise RuntimeError(
            "auto-install requires the frozen .exe build, not python -m"
        )

    bat = _write_self_replace_bat(new_exe=new_exe, target=current)
    log.info("spawning installer %s -> %s", new_exe, current)
    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP so the .bat survives
    # our own exit. /c keeps cmd alive only until the bat finishes,
    # which is what we want.
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    # Give the launcher a beat to start, then bow out so the move can
    # actually proceed (Windows holds an exclusive lock on the running
    # exe).
    log.info("exiting current process so updater can take over")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _running_exe_path() -> Optional[Path]:
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return None


def _self_version() -> str:
    try:
        from . import __version__ as v  # local import to avoid cycles
        return v
    except Exception:  # noqa: BLE001
        return "0.0.0"


def _write_self_replace_bat(*, new_exe: Path, target: Path) -> Path:
    """Emit a one-shot .bat that does: wait, move, relaunch, self-delete."""
    bat = Path(tempfile.gettempdir()) / "busylight-update.bat"
    # Use 8.3-safe absolute paths in quotes so spaces don't break the
    # move. `move /y` overwrites; `start ""` keeps the relaunched exe
    # decoupled from the bat's cmd window.
    bat.write_text(
        "@echo off\r\n"
        "rem BusyLight Presence self-updater (auto-generated)\r\n"
        # Wait ~2s for the original process to exit so Windows releases
        # the file lock on the .exe.
        "timeout /t 2 /nobreak >nul\r\n"
        f'move /y "{new_exe}" "{target}" >nul\r\n'
        f'start "" "{target}"\r\n'
        # Delete the bat itself last so its own handle is gone.
        f'del "%~f0"\r\n',
        encoding="ascii",
    )
    return bat
