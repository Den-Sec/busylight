"""HTTP client that talks to a BusyLight device.

Keeps a single session warm: logs in once with the PIN, then reuses the
``BLSESS`` HttpOnly cookie + the ``BLCSRF`` token for subsequent state
changes. Re-authenticates transparently on a 401/403.
"""

from __future__ import annotations

import json
import logging
import urllib.error
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from typing import Optional
from urllib import request

log = logging.getLogger(__name__)


VALID_STATES = ("AVAILABLE", "BUSY", "IN_CALL", "AWAY")


class BusyLightAuthError(RuntimeError):
    """Raised when the PIN is wrong or the device rejects the session."""


class BusyLightNetworkError(RuntimeError):
    """Raised when the device cannot be reached on the network."""


@dataclass
class BusyLightClient:
    """One client per BusyLight host."""

    host: str
    pin: str
    timeout_s: float = 4.0

    _jar: CookieJar = field(default_factory=CookieJar, init=False, repr=False)
    _opener: request.OpenerDirector = field(init=False, repr=False)
    _csrf: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        self._opener = request.build_opener(
            request.HTTPCookieProcessor(self._jar)
        )

    # ---------- public API ----------

    def login(self) -> None:
        self._csrf = ""
        for cookie in list(self._jar):
            self._jar.clear(cookie.domain, cookie.path, cookie.name)
        body = json.dumps({"pin": self.pin}).encode("utf-8")
        status, payload = self._send("POST", "/api/auth/login", body=body)
        if status != 200:
            raise BusyLightAuthError(
                payload.get("error", f"login failed: HTTP {status}")
            )
        # The device puts the CSRF token both in a cookie (for the web UI
        # to read via JS) and in the login response body. Prefer the
        # response field; cookies in the jar are fine too.
        csrf = payload.get("csrf") or self._cookie_value("BLCSRF")
        if not csrf:
            raise BusyLightAuthError("login OK but no CSRF token returned")
        self._csrf = csrf
        log.info("logged in to %s", self.host)

    def set_state(self, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid state {state!r}")
        body = json.dumps({"state": state}).encode("utf-8")
        status, payload = self._send(
            "POST", "/api/state", body=body, csrf=True
        )
        if status == 401 or status == 403:
            log.info("session expired; re-authenticating")
            self.login()
            status, payload = self._send(
                "POST", "/api/state", body=body, csrf=True
            )
        if status != 200:
            raise BusyLightNetworkError(
                payload.get("error", f"HTTP {status}")
            )

    def get_state(self) -> Optional[str]:
        status, payload = self._send("GET", "/api/state")
        if status == 401:
            return None
        if status != 200:
            raise BusyLightNetworkError(f"GET /api/state -> {status}")
        return payload.get("state")

    # ---------- internals ----------

    def _send(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        csrf: bool = False,
    ):
        headers = {"Content-Type": "application/json"}
        if csrf and self._csrf:
            headers["X-CSRF-Token"] = self._csrf
        url = f"http://{self.host.rstrip('/')}{path}"
        req = request.Request(url, data=body, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return resp.status, self._maybe_json(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            return e.code, self._maybe_json(raw)
        except urllib.error.URLError as e:
            raise BusyLightNetworkError(str(e)) from e
        except TimeoutError as e:
            raise BusyLightNetworkError(f"timeout after {self.timeout_s}s") from e

    def _cookie_value(self, name: str) -> str:
        for cookie in self._jar:
            if cookie.name == name:
                return cookie.value
        return ""

    @staticmethod
    def _maybe_json(text: str) -> dict:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
