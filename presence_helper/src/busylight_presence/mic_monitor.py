"""Cross-platform "is any app using the microphone?" detector.

Windows implementation uses the Capability Access Manager registry hive:
when an app starts capturing audio Windows writes a `LastUsedTimeStop=0`
entry under each owning app. When the app releases the device Windows
sets that field to the current FILETIME. Reading the registry is cheap
(microseconds), needs no admin, no extra dependencies, and covers both
Win32 apps (in the ``NonPackaged`` subtree) and Store / UWP apps.

macOS / Linux back-ends are stubbed for now; the helper logs a clear
warning and reports "not in use" so it stays a no-op rather than
flapping the state.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MicUsage:
    in_use: bool
    apps: tuple[str, ...]  # human names of the apps currently capturing


_REGISTRY_PATHS = (
    r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged",
    r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone",
)


def _pretty_name(key_name: str) -> str:
    """Try to extract a human-friendly app name from a registry key name."""
    # NonPackaged entries look like
    #   "#C:#Users#Dennis#AppData#Local#zoom.us#bin#Zoom.exe"
    if "#" in key_name:
        path = key_name.replace("#", "/")
        leaf = path.rsplit("/", 1)[-1]
        return leaf or path
    # Packaged entries are Family Package IDs (e.g.
    # "Microsoft.Teams_8wekyb3d8bbwe"). Strip the publisher hash.
    return key_name.split("_", 1)[0]


def _windows_microphone_in_use() -> MicUsage:
    import winreg

    active: list[str] = []
    for path in _REGISTRY_PATHS:
        try:
            root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            continue

        try:
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    sub = winreg.OpenKey(root, sub_name)
                except FileNotFoundError:
                    continue
                try:
                    stop, _ = winreg.QueryValueEx(sub, "LastUsedTimeStop")
                    if stop == 0:
                        active.append(_pretty_name(sub_name))
                except FileNotFoundError:
                    # Some entries lack the value; skip silently.
                    pass
                finally:
                    winreg.CloseKey(sub)
        finally:
            winreg.CloseKey(root)

    return MicUsage(in_use=bool(active), apps=tuple(active))


def _macos_microphone_in_use() -> MicUsage:
    """macOS: ask ``lsof`` who has Core Audio open right now.

    Apps that capture from the microphone open a file descriptor on
    ``CoreAudio`` (or the device under ``/dev/`` named ``audio*``);
    ``lsof`` lists them. We get the process name out of column 1 of
    the output. Cheap (~10ms) and needs no special permissions for
    the current user's own processes.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["lsof", "-nP", "+c", "0"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return MicUsage(in_use=False, apps=())

    apps: set[str] = set()
    needles = ("CoreAudio", "AppleCameraAssistant", "/dev/audio")
    for line in result.stdout.splitlines():
        if any(n in line for n in needles):
            parts = line.split()
            if parts:
                apps.add(parts[0])

    # Filter out the system-level always-on processes so we don't report
    # "you're in a call" 24/7. coreaudiod always holds Core Audio open.
    SYSTEM_NOISE = {"coreaudiod", "WindowServer", "loginwindow"}
    apps -= SYSTEM_NOISE

    return MicUsage(in_use=bool(apps), apps=tuple(sorted(apps)))


def _linux_microphone_in_use() -> MicUsage:
    """Linux: query the audio server for active capture streams.

    First tries PulseAudio's ``pactl list source-outputs short`` (works
    on PipeWire too via the pipewire-pulse compatibility shim, which
    almost every distro ships). Falls back to ``pw-dump`` for
    PipeWire-native setups without the shim. Returns a hit if any
    capture stream is in the RUNNING state.
    """
    import subprocess

    # --- PulseAudio / PipeWire-Pulse ---
    try:
        result = subprocess.run(
            ["pactl", "list", "source-outputs"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            apps: list[str] = []
            current_running = False
            current_name = ""
            for raw in result.stdout.splitlines():
                line = raw.strip()
                if line.startswith("Source Output #"):
                    if current_running and current_name:
                        apps.append(current_name)
                    current_running = False
                    current_name = ""
                elif line.startswith("State: RUNNING"):
                    current_running = True
                elif line.startswith("application.name "):
                    # `application.name = "Firefox"` (quoted)
                    val = line.split("=", 1)[1].strip()
                    current_name = val.strip('"')
            if current_running and current_name:
                apps.append(current_name)
            return MicUsage(in_use=bool(apps), apps=tuple(sorted(set(apps))))
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    # --- PipeWire native (no pulse shim) ---
    try:
        result = subprocess.run(
            ["pw-dump"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            import json

            data = json.loads(result.stdout)
            apps: list[str] = []
            for obj in data:
                info = obj.get("info", {}) if isinstance(obj, dict) else {}
                props = info.get("props", {}) if isinstance(info, dict) else {}
                media_class = props.get("media.class") or ""
                state = info.get("state") or ""
                if "Stream/Input/Audio" in media_class and state == "running":
                    name = (
                        props.get("application.name")
                        or props.get("node.name")
                        or "unknown"
                    )
                    apps.append(name)
            return MicUsage(in_use=bool(apps), apps=tuple(sorted(set(apps))))
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass

    return MicUsage(in_use=False, apps=())


def microphone_in_use() -> MicUsage:
    """Public entry point. Routes to the platform-specific detector."""
    system = platform.system()
    if system == "Windows":
        return _windows_microphone_in_use()
    if system == "Darwin":
        return _macos_microphone_in_use()
    if system == "Linux":
        return _linux_microphone_in_use()
    return MicUsage(in_use=False, apps=())


def supported_platform() -> bool:
    """Whether the helper has a working detector on this OS."""
    return platform.system() in ("Windows", "Darwin", "Linux")


def _self_test(iterations: int = 10, interval_s: float = 1.5) -> int:
    """Manual smoke test: prints mic usage every interval_s seconds."""
    import time

    print(
        f"Polling microphone state every {interval_s} s "
        f"({iterations} samples). Start a Zoom/Teams/Meet call to see "
        f"the state flip."
    )
    for n in range(iterations):
        usage = microphone_in_use()
        apps = ", ".join(usage.apps) if usage.apps else "—"
        print(f"  [{n+1:>2}] in_use={usage.in_use!s:5}  apps={apps}")
        time.sleep(interval_s)
    return 0


if __name__ == "__main__":
    sys.exit(_self_test())
