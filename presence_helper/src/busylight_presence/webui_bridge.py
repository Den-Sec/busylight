"""Local HTTP bridge that lets the firmware's web UI run inside the
presence app without needing the device to be on Wi-Fi.

We host the same `index.html` / `styles.css` / `app.js` the firmware
ships at `firmware/data/`, then implement the `/api/*` endpoints
locally by proxying them to the device over USB serial. The web UI
itself doesn't know it's not talking to a real ESP — every fetch
just goes to `http://127.0.0.1:<port>/api/...` and looks normal.

What works over the serial bridge:
  - Login (any PIN accepted — USB cable already implies physical access)
  - Get / set state
  - List / add / delete saved Wi-Fi networks
  - Read device info (hostname, fw version, ip, rssi)

What does NOT work without Wi-Fi (those endpoints return 503 with a
clear error code):
  - Schedule list/save  — needs SNTP, needs Wi-Fi anyway
  - MQTT settings
  - Firmware OTA over HTTP (use the dedicated USB OTA from the
    presence app menu or `serial_client.update_firmware`)
  - Device reboot / factory reset

The bridge listens on a port chosen at startup (random ephemeral) and
returns it via `start()` so the caller can open a WebView pointed at
it.
"""

from __future__ import annotations

import json
import logging
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .serial_client import (
    SerialClient,
    SerialProtocolError,
    SerialUnavailable,
    find_busylight_ports,
)

log = logging.getLogger(__name__)


def _webui_dir() -> Path:
    """Where the bundled web UI assets live.

    PyInstaller --collect-data puts package data under
    `sys._MEIPASS/busylight_presence/webui/`. From the source tree
    it's right next to this file.
    """
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS"))
        candidate = meipass / "busylight_presence" / "webui"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "webui"


# Cached so we don't re-read the static files for every request.
_ASSETS_CACHE: dict[str, bytes] = {}


def _load_asset(name: str) -> Optional[bytes]:
    if name in _ASSETS_CACHE:
        return _ASSETS_CACHE[name]
    path = _webui_dir() / name
    if not path.is_file():
        return None
    data = path.read_bytes()
    _ASSETS_CACHE[name] = data
    return data


def claude_mode_status() -> dict:
    """Pure, testable helper: current Claude-mode status (no HTTP)."""
    from . import claude_light
    return claude_light.status()


def claude_mode_action(action: str) -> dict:
    """Pure, testable helper: apply a Claude-mode action, return new status."""
    from . import claude_light
    if action == "on":
        claude_light.enable()
    elif action == "off":
        claude_light.disable()
    elif action == "focus":
        claude_light.set_focus(None)  # most-recently-active
    elif action == "unfocus":
        claude_light.clear_focus()
    return claude_light.status()


def _content_type(filename: str) -> str:
    if filename.endswith(".html"):
        return "text/html; charset=utf-8"
    if filename.endswith(".css"):
        return "text/css; charset=utf-8"
    if filename.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if filename.endswith(".json"):
        return "application/json; charset=utf-8"
    return "application/octet-stream"


# ---------------------------------------------------------------------------
# Bridge handler
# ---------------------------------------------------------------------------

class _BridgeHandler(BaseHTTPRequestHandler):
    """Maps HTTP requests from the web UI to serial commands."""

    # Quiet the default access log — we run as a hidden service.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        log.debug("bridge: " + format, *args)

    # ----- static assets ----------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._serve_asset("index.html")
        if path in ("/index.html", "/app.js", "/styles.css"):
            return self._serve_asset(path.lstrip("/"))
        if path.startswith("/api/"):
            return self._handle_api_get(path)
        return self._send(404, "text/plain", b"not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/"):
            return self._handle_api_post(path)
        return self._send(404, "text/plain", b"not found")

    def do_DELETE(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/"):
            return self._handle_api_delete(path)
        return self._send(404, "text/plain", b"not found")

    # ----- helpers ----------------------------------------------------------
    def _serve_asset(self, name: str) -> None:
        data = _load_asset(name)
        if data is None:
            return self._send(404, "text/plain", b"asset not found")
        self._send(200, _content_type(name), data)

    def _send(self, status: int, content_type: str, body: bytes,
              headers: Optional[dict] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, status: int, payload: dict,
                   headers: Optional[dict] = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send(status, "application/json", body, headers=headers)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _serial(self) -> Optional[SerialClient]:
        if WebUiBridge.suspended:
            # An OTA stream is in flight on the COM port; refusing to
            # open it here keeps the dashboard's auto-refresh polling
            # from racing the OTA reader on the same handle.
            return None
        ports = find_busylight_ports()
        if not ports:
            return None
        return SerialClient(port=ports[0])

    # ----- API: GET ---------------------------------------------------------
    def _handle_api_get(self, path: str) -> None:
        if path == "/api/state":
            return self._api_get_state()
        if path == "/api/wifi":
            return self._api_get_wifi()
        if path == "/api/settings":
            return self._api_get_settings()
        if path == "/api/schedule":
            return self._send_json(503, {"error": "schedule_needs_wifi"})
        if path == "/api/mqtt":
            return self._send_json(503, {"error": "mqtt_needs_wifi"})
        if path == "/api/claude-mode":
            return self._send_json(200, claude_mode_status())
        self._send_json(404, {"error": "not_found"})

    def _api_get_state(self) -> None:
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            info = sc.get_info()
        except (SerialUnavailable, SerialProtocolError) as e:
            return self._send_json(502, {"error": str(e)})
        state_int = info.get("state")
        from .serial_client import STATE_INT_TO_NAME
        state = STATE_INT_TO_NAME.get(state_int, "AVAILABLE")
        # Web UI also expects `uptime_ms`. We don't have it over serial
        # yet — fake an increasing value with `monotonic` * 1000 so the
        # UI doesn't break.
        import time
        self._send_json(200, {"state": state,
                              "uptime_ms": int(time.monotonic() * 1000)})

    def _api_get_wifi(self) -> None:
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            resp = sc.wifi_list()
        except (SerialUnavailable, SerialProtocolError) as e:
            return self._send_json(502, {"error": str(e)})
        self._send_json(200, resp)

    def _api_get_settings(self) -> None:
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            info = sc.get_info()
        except (SerialUnavailable, SerialProtocolError) as e:
            return self._send_json(502, {"error": str(e)})
        host = info.get("host", "busylight")
        ip = info.get("ip", "")
        self._send_json(200, {
            "hostname": host,
            "mdns": f"http://{host}.local",
            "ip": ip,
            "rssi": -50,  # Not available over serial yet; UI tolerates it.
            "version": info.get("fw", "?"),
        })

    # ----- API: POST --------------------------------------------------------
    def _handle_api_post(self, path: str) -> None:
        if path == "/api/auth/login":
            # USB cable already implies physical access — skip auth.
            # Set a dummy CSRF cookie so the JS continues normally.
            return self._send_json(
                200,
                {"ok": True, "csrf": "usb-trusted"},
                headers={"Set-Cookie": "BLCSRF=usb-trusted; Path=/; SameSite=Lax"},
            )
        if path == "/api/auth/logout":
            return self._send_json(200, {"ok": True})
        if path == "/api/state":
            return self._api_post_state()
        if path == "/api/wifi":
            return self._api_post_wifi()
        if path == "/api/settings/pin":
            return self._api_post_pin()
        if path == "/api/device/factory_reset":
            return self._api_post_factory_reset()
        if path in ("/api/schedule", "/api/mqtt",
                    "/api/device/reboot",
                    "/api/firmware/update"):
            return self._send_json(503, {"error": "needs_wifi_or_dedicated_flow"})
        if path == "/api/claude-mode":
            body = self._read_json_body()
            action = (body.get("action") or "").strip()
            return self._send_json(200, claude_mode_action(action))
        self._send_json(404, {"error": "not_found"})

    def _api_post_pin(self) -> None:
        body = self._read_json_body()
        new_pin = (body.get("new_pin") or "").strip()
        current_pin = (body.get("current_pin") or "").strip()
        if not new_pin:
            return self._send_json(400, {"error": "invalid_payload"})
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            sc.set_pin(new_pin, current_pin)
        except (SerialUnavailable, SerialProtocolError) as e:
            return self._send_json(502, {"error": str(e)})
        self._send_json(200, {"ok": True})

    def _api_post_factory_reset(self) -> None:
        # The web UI guards this with a confirm header; the firmware
        # also requires `confirm:"YES"` in the serial cmd body, which
        # SerialClient.factory_reset() always passes. So we just
        # need a USB device and we're good.
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            sc.factory_reset()
        except (SerialUnavailable, SerialProtocolError) as e:
            return self._send_json(502, {"error": str(e)})
        self._send_json(200, {"ok": True, "rebooting": True})

    def _api_post_state(self) -> None:
        body = self._read_json_body()
        state = body.get("state")
        if not isinstance(state, str):
            return self._send_json(400, {"error": "invalid_payload"})
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            sc.set_state(state)
        except (SerialUnavailable, SerialProtocolError, ValueError) as e:
            return self._send_json(502, {"error": str(e)})
        self._send_json(200, {"ok": True})

    def _api_post_wifi(self) -> None:
        body = self._read_json_body()
        ssid = (body.get("ssid") or "").strip()
        password = body.get("password") or ""
        if not ssid:
            return self._send_json(400, {"error": "invalid_payload"})
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            sc.wifi_add(ssid, password)
        except (SerialUnavailable, SerialProtocolError) as e:
            return self._send_json(502, {"error": str(e)})
        self._send_json(200, {"ok": True})

    # ----- API: DELETE ------------------------------------------------------
    def _handle_api_delete(self, path: str) -> None:
        if path == "/api/wifi":
            return self._api_delete_wifi()
        self._send_json(404, {"error": "not_found"})

    def _api_delete_wifi(self) -> None:
        body = self._read_json_body()
        ssid = (body.get("ssid") or "").strip()
        if not ssid:
            return self._send_json(400, {"error": "invalid_payload"})
        sc = self._serial()
        if sc is None:
            return self._send_json(503, {"error": "no_usb_device"})
        try:
            sc.wifi_remove(ssid)
        except (SerialUnavailable, SerialProtocolError) as e:
            return self._send_json(502, {"error": str(e)})
        self._send_json(200, {"ok": True})


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

class WebUiBridge:
    """Spin up the bridge HTTP server on `127.0.0.1:<ephemeral>`."""

    # Class-level flag because BaseHTTPRequestHandler instances are
    # short-lived (one per request) and have no clean way to reach an
    # instance attribute. Setting this to True makes every Serial-
    # touching endpoint reply 503 instantly without grabbing the COM
    # port — useful while an OTA stream is in flight.
    suspended: bool = False

    def __init__(self) -> None:
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0

    @classmethod
    def set_suspended(cls, value: bool) -> None:
        cls.suspended = bool(value)

    def start(self) -> str:
        if self._server is not None:
            return f"http://127.0.0.1:{self.port}/"
        # Ask the OS for a free port by binding to 0.
        addr = ("127.0.0.1", 0)
        self._server = ThreadingHTTPServer(addr, _BridgeHandler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="webui-bridge"
        )
        self._thread.start()
        url = f"http://127.0.0.1:{self.port}/"
        log.info("web UI bridge listening on %s", url)
        return url

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._server.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._server = None
            self._thread = None
