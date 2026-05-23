from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Callable

from serial import Serial, SerialTimeoutException
from serial.tools import list_ports


@dataclass(frozen=True)
class SetupResult:
    mdns_url: str
    ip_url: str | None


def _debug_log(message: str) -> None:
    log_path = os.getenv("BUSYLIGHT_DEBUG_LOG", "").strip()
    if not log_path:
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")


ESPRESSIF_VIDS: frozenset[int] = frozenset(
    {
        0x303A,  # Espressif Systems (native USB CDC on ESP32-C3/C6/S2/S3)
        0x10C4,  # Silicon Labs CP210x (older dev boards)
        0x1A86,  # WCH CH340 (cheap clone dev boards)
    }
)


def available_ports() -> list[str]:
    """All serial ports currently visible to the OS."""
    return [p.device for p in list_ports.comports()]


def available_busylight_ports() -> list[tuple[str, str]]:
    """Ports that look like an ESP-based BusyLight, with a human description.

    Falls back to every port if no recognised USB VID is found, so users with
    unusual adapters can still pick one manually.
    """
    matches: list[tuple[str, str]] = []
    all_ports: list[tuple[str, str]] = []
    for p in list_ports.comports():
        description = p.description or p.device
        all_ports.append((p.device, description))
        if p.vid in ESPRESSIF_VIDS:
            matches.append((p.device, description))
    return matches if matches else all_ports


def build_config_packet(ssid: str, password: str, pin: str) -> dict:
    return {
        "cmd": "set_config",
        "ssid": ssid,
        "password": password,
        "pin": pin,
    }


def _encode_json_line(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


def _read_json_line(ser: Serial) -> dict | None:
    raw = ser.readline()
    if not raw:
        return None
    try:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
    except json.JSONDecodeError:
        return None


_HANDSHAKE_OK_EVENTS = {"pong", "ready"}


def _wait_for_pong(ser: Serial, *, timeout_s: float = 12.0) -> str:
    """Wait for the device to acknowledge either a 'ready' beacon or 'pong'.

    The firmware emits a `{event:ready}` line autonomously after USB CDC
    enumeration completes; this is the fastest possible signal. Pings are
    still sent every second in case the wizard attached after the beacon
    was already flushed.

    Returns the device hostname (e.g. ``busylight-f5f0``) if the firmware
    advertised one in the ready beacon, or ``""`` otherwise. The caller can
    use this to build the correct mDNS URL even if the wizard never sees
    a `server_started` line (which is the common case when the device
    re-enumerates USB during reboot).
    """
    deadline = time.time() + timeout_s
    next_ping_at = 0.0

    _debug_log("wait_for_pong:start")
    while time.time() < deadline:
        now = time.time()
        if now >= next_ping_at:
            try:
                ser.write(_encode_json_line({"cmd": "ping"}))
                ser.flush()
                _debug_log("wait_for_pong:ping_sent")
            except SerialTimeoutException:
                _debug_log("wait_for_pong:write_timeout")
            next_ping_at = now + 1.0

        msg = _read_json_line(ser)
        if not msg:
            continue
        _debug_log(f"wait_for_pong:rx={msg}")
        if msg.get("event") in _HANDSHAKE_OK_EVENTS and msg.get("ok") is True:
            host = str(msg.get("host", "")).strip()
            _debug_log(f"wait_for_pong:ok event={msg.get('event')} host={host}")
            return host

    _debug_log("wait_for_pong:timeout")
    raise RuntimeError("BusyLight did not respond to handshake (ready/pong).")


def _emit_progress(callback: Callable[[str], None] | None, text: str) -> None:
    if callback:
        callback(text)


def configure_device(
    port: str,
    ssid: str,
    password: str,
    pin: str,
    *,
    timeout_s: float = 45.0,
    on_progress: Callable[[str], None] | None = None,
) -> SetupResult:
    _debug_log(f"configure:start port={port} ssid_len={len(ssid)} pin_len={len(pin)}")
    payload = build_config_packet(ssid, password, pin)
    deadline = time.time() + timeout_s
    saw_config_saved = False
    config_saved_at: float | None = None
    ip_url: str | None = None
    device_host: str = ""  # captured from ready/config_saved/server_started

    _debug_log("configure:opening_serial")
    _emit_progress(on_progress, "Opening serial port...")
    with Serial(
        port=port,
        baudrate=115200,
        timeout=1.2,
        write_timeout=1.5,
        rtscts=False,
        dsrdtr=False,
        xonxoff=False,
    ) as ser:
        _debug_log("configure:serial_opened")
        _emit_progress(on_progress, "Serial port opened. Handshaking with BusyLight...")

        # Assert DTR before doing anything else. ESP32-C6 with native USB CDC
        # holds Serial as 'not connected' until the host raises DTR; without
        # this the device drops every byte the wizard sends.
        try:
            ser.dtr = True
            ser.rts = False
        except Exception as ex:  # noqa: BLE001
            _debug_log(f"configure:dtr_set_failed={ex}")

        # Let the USB CDC endpoint settle before handshake traffic.
        time.sleep(0.5)
        ser.reset_input_buffer()
        _debug_log("configure:buffers_reset")

        device_host = _wait_for_pong(ser)
        _emit_progress(on_progress, "Handshake OK. Sending Wi-Fi configuration...")

        ser.write(_encode_json_line(payload))
        ser.flush()
        _debug_log("configure:set_config_sent")
        _emit_progress(on_progress, "Configuration sent. Waiting for device confirmation...")

        while time.time() < deadline:
            # Short-circuit: once the device has confirmed config_saved we
            # cannot rely on `server_started` arriving (USB CDC re-enumerates
            # on reboot, so the wizard typically loses the serial sync).
            # Wait at most 8 s for it, then exit cleanly with whatever
            # hostname/IP we managed to capture.
            if (
                saw_config_saved
                and config_saved_at is not None
                and (time.time() - config_saved_at) > 8
            ):
                _debug_log("configure:config_saved_no_server_started_break")
                break

            msg = _read_json_line(ser)
            if not msg:
                continue
            _debug_log(f"configure:rx={msg}")

            # Distinguish command rejections from autonomous status events:
            # rejections always carry an explicit `error` field. Lines with
            # `ok=false` but only an `event` (e.g. `wifi_retry` while the
            # device is still in AP mode) are informational; ignore them.
            if msg.get("ok") is False:
                err = msg.get("error")
                if err is not None:
                    _debug_log(f"configure:device_error={err}")
                    raise RuntimeError(f"Device rejected configuration: {err}")
                # autonomous status, ignore.
                continue

            event = msg.get("event")
            host = str(msg.get("host", "")).strip()
            if host:
                device_host = host

            if event == "config_saved":
                saw_config_saved = True
                config_saved_at = time.time()
                _emit_progress(on_progress, "Configuration saved. Finalizing BusyLight startup...")
            elif event == "server_started":
                ip = msg.get("ip")
                if ip:
                    ip_url = f"http://{ip}"
                break

        if not saw_config_saved:
            _debug_log("configure:missing_config_saved")
            raise RuntimeError(
                "BusyLight did not confirm configuration save. Check USB cable/COM port and retry."
            )

    mdns_url = f"http://{device_host}.local" if device_host else "http://busylight.local"
    _debug_log(f"configure:done host={device_host} mdns={mdns_url} ip={ip_url}")
    return SetupResult(mdns_url=mdns_url, ip_url=ip_url)
