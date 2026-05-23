"""Unit tests for the BusyLight HTTP client.

The client wraps ``urllib.request.OpenerDirector``. We monkey-patch
``OpenerDirector.open`` to inject canned responses without touching the
network.
"""

from __future__ import annotations

import io
import json
import urllib.error
from http.client import HTTPResponse  # noqa: F401  (only for type clarity)
from typing import Any
from urllib.request import OpenerDirector, Request

import pytest

from busylight_presence import client as client_mod
from busylight_presence.client import (
    BusyLightAuthError,
    BusyLightClient,
    BusyLightNetworkError,
)


class _FakeResponse:
    def __init__(self, status: int, body: dict[str, Any], *, headers=None):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_a) -> None:  # noqa: ANN001
        pass


def _patch_open(monkeypatch: pytest.MonkeyPatch, sequence: list[Any]) -> list[Request]:
    calls: list[Request] = []
    queue = list(sequence)

    def fake_open(self, req, timeout=None):  # noqa: ANN001
        calls.append(req)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(OpenerDirector, "open", fake_open)
    return calls


# ---------- login ----------


def test_login_stores_csrf_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_open(monkeypatch, [
        _FakeResponse(200, {"ok": True, "csrf": "abc123"}),
    ])
    c = BusyLightClient(host="busylight.local", pin="1234")
    c.login()
    assert c._csrf == "abc123"


def test_login_raises_on_wrong_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_open(monkeypatch, [
        urllib.error.HTTPError(
            "url", 401, "Unauthorized", {},
            io.BytesIO(json.dumps({"error": "invalid_pin"}).encode()),
        ),
    ])
    c = BusyLightClient(host="x.local", pin="0000")
    with pytest.raises(BusyLightAuthError, match="invalid_pin"):
        c.login()


def test_login_raises_when_response_lacks_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_open(monkeypatch, [_FakeResponse(200, {"ok": True})])
    c = BusyLightClient(host="x.local", pin="1234")
    with pytest.raises(BusyLightAuthError, match="CSRF"):
        c.login()


# ---------- set_state ----------


def test_set_state_sends_csrf_header(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_open(monkeypatch, [
        _FakeResponse(200, {"ok": True, "csrf": "tok"}),  # login
        _FakeResponse(200, {"ok": True}),                  # set_state
    ])
    c = BusyLightClient(host="x.local", pin="1234")
    c.login()
    c.set_state("BUSY")
    assert calls[1].get_header("X-csrf-token") == "tok"
    assert b'"state": "BUSY"' in calls[1].data or b'"state":"BUSY"' in calls[1].data


def test_set_state_re_logs_in_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_open(monkeypatch, [
        _FakeResponse(200, {"ok": True, "csrf": "tok1"}),  # initial login
        urllib.error.HTTPError(
            "url", 401, "Unauthorized", {},
            io.BytesIO(json.dumps({"error": "unauthorized"}).encode()),
        ),                                                  # expired session
        _FakeResponse(200, {"ok": True, "csrf": "tok2"}),  # re-login
        _FakeResponse(200, {"ok": True}),                  # retried set_state
    ])
    c = BusyLightClient(host="x.local", pin="1234")
    c.login()
    c.set_state("AVAILABLE")
    assert c._csrf == "tok2"


def test_set_state_rejects_invalid_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_open(monkeypatch, [_FakeResponse(200, {"ok": True, "csrf": "x"})])
    c = BusyLightClient(host="x.local", pin="1234")
    c.login()
    with pytest.raises(ValueError, match="invalid state"):
        c.set_state("DISCO")


# ---------- get_state ----------


def test_get_state_returns_state_string(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_open(monkeypatch, [
        _FakeResponse(200, {"ok": True, "csrf": "x"}),
        _FakeResponse(200, {"state": "AVAILABLE", "uptime_ms": 1000}),
    ])
    c = BusyLightClient(host="x.local", pin="1234")
    c.login()
    assert c.get_state() == "AVAILABLE"


def test_get_state_returns_none_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_open(monkeypatch, [
        _FakeResponse(200, {"ok": True, "csrf": "x"}),
        urllib.error.HTTPError(
            "url", 401, "Unauthorized", {},
            io.BytesIO(b"{}"),
        ),
    ])
    c = BusyLightClient(host="x.local", pin="1234")
    c.login()
    assert c.get_state() is None


# ---------- network error path ----------


def test_network_error_propagates_as_busylightnetworkerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_open(monkeypatch, [
        urllib.error.URLError("Connection refused"),
    ])
    c = BusyLightClient(host="dead.local", pin="1234")
    with pytest.raises(BusyLightNetworkError, match="Connection refused"):
        c.login()
