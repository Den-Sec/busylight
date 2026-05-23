"""Unit tests for the cross-platform mic detector.

We can't easily plug a fake registry into ``winreg`` from Python, so we
test the small surface that doesn't need real registry data: the pretty-
name helper and the platform routing.
"""

from __future__ import annotations

import platform

import pytest

from busylight_presence import mic_monitor as mm


def test_pretty_name_strips_nonpackaged_path_prefix() -> None:
    raw = "#C:#Users#Dennis#AppData#Local#zoom.us#bin#Zoom.exe"
    assert mm._pretty_name(raw) == "Zoom.exe"


def test_pretty_name_strips_packaged_publisher_hash() -> None:
    raw = "Microsoft.Teams_8wekyb3d8bbwe"
    assert mm._pretty_name(raw) == "Microsoft.Teams"


def test_pretty_name_handles_unknown_format() -> None:
    assert mm._pretty_name("plainName") == "plainName"


def test_supported_platform_true_on_known_oses() -> None:
    expected = platform.system() in ("Windows", "Darwin", "Linux")
    assert mm.supported_platform() is expected


def test_microphone_in_use_returns_micusage() -> None:
    usage = mm.microphone_in_use()
    assert isinstance(usage.in_use, bool)
    assert isinstance(usage.apps, tuple)


# ---------- macOS lsof parser ----------

_LSOF_HIT = (
    "Zoom       12345 dennis   23u   CHR  19,4 0t0 1234 /dev/null\n"
    "Zoom       12345 dennis   45u  unix 0x123 0t0 1234 ->CoreAudio\n"
    "coreaudiod 5678  _coreaud 12u   CHR  19,4 0t0 9999 /dev/audioCoreAudio\n"
    "Slack      9999 dennis    33u  unix 0x456 0t0 9999 CoreAudio device\n"
)


def test_macos_parser_extracts_apps_and_ignores_system_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompleted:
        returncode = 0
        stdout = _LSOF_HIT

    def fake_run(*args, **kwargs):  # noqa: ANN001
        return FakeCompleted()

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)
    usage = mm._macos_microphone_in_use()
    assert usage.in_use is True
    assert "Zoom" in usage.apps
    assert "Slack" in usage.apps
    # coreaudiod is the always-on system audio server; never reported.
    assert "coreaudiod" not in usage.apps


def test_macos_parser_returns_idle_on_missing_lsof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError("lsof")

    monkeypatch.setattr(subprocess, "run", fake_run)
    usage = mm._macos_microphone_in_use()
    assert usage.in_use is False


# ---------- Linux pactl parser ----------

_PACTL_RUNNING = """\
Source Output #42
\tDriver: protocol-native.c
\tOwner Module: 12
\tClient: 33
\tSource: 0
\tSample Specification: float32le 2ch 48000Hz
\tChannel Map: front-left,front-right
\tFormat: pcm, format.sample_format = "\\"float32le\\""
\tCorked: no
\tMute: no
\tVolume: front-left: 65536 / 100% / 0.00 dB
\t        front-right: 65536 / 100% / 0.00 dB
\t        balance 0.00
\tBuffer Latency: 19957 usec
\tSource Latency: 0 usec
\tResample method: copy
\tProperties:
\t\tmedia.name = "Capture"
\t\tapplication.name = "Zoom"
\t\tapplication.process.id = "12345"
\tState: RUNNING
"""

_PACTL_CORKED = """\
Source Output #1
\tProperties:
\t\tapplication.name = "Firefox"
\tState: CORKED
"""


def test_linux_pactl_running_stream_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompleted:
        returncode = 0
        stdout = _PACTL_RUNNING

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompleted())
    usage = mm._linux_microphone_in_use()
    assert usage.in_use is True
    assert "Zoom" in usage.apps


def test_linux_pactl_corked_stream_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompleted:
        returncode = 0
        stdout = _PACTL_CORKED

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompleted())
    usage = mm._linux_microphone_in_use()
    # No RUNNING stream -> we should not flag the mic as in use.
    # (Without pactl in the response we'd fall through to pw-dump; the
    # fake_run subs both calls in this test, so both return the same
    # empty-ish CORKED response and we expect in_use=False.)
    assert usage.in_use is False
