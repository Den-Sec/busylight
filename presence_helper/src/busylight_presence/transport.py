"""Unified transport that prefers USB serial when the cable is plugged.

Rationale (decided 2026-05-24): when the BusyLight is connected to the
same machine that runs the helper, Wi-Fi is a needless extra hop and a
single point of failure. The serial bridge always works as long as the
USB cable is in, so we use it as the primary channel and fall back to
HTTP only when no compatible USB port is present (or the port can't be
opened, e.g. because the setup wizard has it).

The transport keeps the `BusyLightClient` API (`login`, `set_state`,
`get_state`) so the rest of the helper doesn't need to know which path
is active. `current_mode` exposes the active channel for the tray icon.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .client import (
    BusyLightAuthError,
    BusyLightClient,
    BusyLightNetworkError,
)
from .serial_client import (
    SerialClient,
    SerialProtocolError,
    SerialUnavailable,
    find_busylight_ports,
)

log = logging.getLogger(__name__)


# How long to trust a previously-failed serial probe before re-scanning.
# 30 s is a compromise: long enough that we don't pay the COM-enum cost
# on every poll (which is ~80 ms on Windows), short enough that plugging
# in the cable mid-session feels responsive.
SERIAL_RESCAN_INTERVAL_S = 30.0


class BusyLightTransport:
    """Drop-in replacement for `BusyLightClient` that picks serial-or-HTTP.

    Construction is lazy: we don't open the serial port or hit the HTTP
    API in __init__. The first `login()` call triggers a probe of both
    channels and picks Serial if reachable.
    """

    def __init__(self, host: str, pin: str, timeout_s: float = 4.0) -> None:
        self.host = host
        self.pin = pin
        self._http = BusyLightClient(host=host, pin=pin, timeout_s=timeout_s)
        self._serial: Optional[SerialClient] = None
        self._serial_port: Optional[str] = None
        self._last_serial_scan: float = 0.0
        self._http_authed: bool = False
        self._last_mode: Optional[str] = None  # "serial" | "http" | None

    # ------------------------------------------------------------------
    # Public surface (mirrors BusyLightClient)
    # ------------------------------------------------------------------
    def login(self) -> None:
        # Always try serial first — it's the cheaper, more reliable path
        # when the cable is in. HTTP login is deferred until we actually
        # need to fall back.
        self._refresh_serial(force=True)
        if self._serial is not None:
            try:
                self._serial.login()
                self._last_mode = "serial"
                log.info("serial transport ready on %s", self._serial_port)
                return
            except SerialUnavailable as e:
                log.info("serial probe failed (%s); trying HTTP", e)
                self._serial = None

        # Fallback: HTTP
        self._http.login()
        self._http_authed = True
        self._last_mode = "http"
        log.info("HTTP transport ready (no USB device found)")

    def set_state(self, state: str) -> None:
        self._maybe_rescan_serial()
        if self._serial is not None:
            try:
                self._serial.set_state(state)
                self._last_mode = "serial"
                return
            except (SerialUnavailable, SerialProtocolError) as e:
                log.warning(
                    "serial set_state failed (%s); falling back to HTTP", e
                )
                self._invalidate_serial()
        self._http_set_state(state)

    def get_state(self) -> Optional[str]:
        self._maybe_rescan_serial()
        if self._serial is not None:
            try:
                s = self._serial.get_state()
                self._last_mode = "serial"
                return s
            except (SerialUnavailable, SerialProtocolError) as e:
                log.debug("serial get_state failed (%s); falling back", e)
                self._invalidate_serial()
        return self._http_get_state()

    # ------------------------------------------------------------------
    # Public extras (for the tray)
    # ------------------------------------------------------------------
    @property
    def current_mode(self) -> Optional[str]:
        return self._last_mode

    @property
    def serial_port(self) -> Optional[str]:
        return self._serial_port

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _refresh_serial(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_serial_scan) < SERIAL_RESCAN_INTERVAL_S:
            return
        self._last_serial_scan = now
        ports = find_busylight_ports()
        if not ports:
            if self._serial is not None:
                log.info("USB device disconnected; switching to HTTP")
            self._serial = None
            self._serial_port = None
            return
        # If the active port is gone but another candidate appeared,
        # switch. If we have no client yet, pick the first.
        chosen = ports[0]
        if self._serial_port != chosen:
            self._serial_port = chosen
            self._serial = SerialClient(port=chosen)
            log.info("serial candidate: %s", chosen)

    def _maybe_rescan_serial(self) -> None:
        if self._serial is not None:
            return  # already have a working channel
        self._refresh_serial(force=False)

    def _invalidate_serial(self) -> None:
        self._serial = None
        self._serial_port = None
        # Force the next call to rescan immediately rather than waiting
        # the full 30 s window.
        self._last_serial_scan = 0.0

    def _http_set_state(self, state: str) -> None:
        if not self._http_authed:
            self._http.login()
            self._http_authed = True
        try:
            self._http.set_state(state)
        except BusyLightAuthError:
            # Session evicted; re-auth and retry once.
            self._http.login()
            self._http.set_state(state)
        self._last_mode = "http"

    def _http_get_state(self) -> Optional[str]:
        if not self._http_authed:
            try:
                self._http.login()
                self._http_authed = True
            except (BusyLightAuthError, BusyLightNetworkError) as e:
                log.debug("HTTP login failed during get_state: %s", e)
                self._last_mode = None
                return None
        try:
            s = self._http.get_state()
            self._last_mode = "http"
            return s
        except BusyLightAuthError:
            self._http_authed = False
            return None
