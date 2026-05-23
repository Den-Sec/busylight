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


def test_supported_platform_only_true_on_windows() -> None:
    is_windows = platform.system() == "Windows"
    assert mm.supported_platform() is is_windows


def test_microphone_in_use_returns_micusage() -> None:
    usage = mm.microphone_in_use()
    assert isinstance(usage.in_use, bool)
    assert isinstance(usage.apps, tuple)


@pytest.mark.skipif(
    platform.system() != "Linux", reason="Linux stub always reports idle"
)
def test_linux_stub_reports_no_use() -> None:
    assert mm._linux_microphone_in_use().in_use is False


@pytest.mark.skipif(
    platform.system() != "Darwin", reason="macOS stub always reports idle"
)
def test_macos_stub_reports_no_use() -> None:
    assert mm._macos_microphone_in_use().in_use is False
