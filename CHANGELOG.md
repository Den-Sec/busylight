# Changelog

All notable changes to BusyLight are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.2] - 2026-05-25

### Added
- Firmware OTA over USB serial: the presence helper can push a signed `.bin` to the device entirely over the cable (no Wi-Fi required), using the same RSA-2048 / SHA-256 signature check as the HTTP OTA endpoint.
- USB-only setup: host + PIN are now optional in the presence helper. With the cable plugged in the helper authenticates the device implicitly over USB; you don't have to fill in any Wi-Fi info to use it.
- Settings window shows a live banner: green "Device detected over USB" or amber "No USB device detected" so it's obvious whether you need to type anything.

### Fixed
- OTA reliability: the device used to drop the final `ota_complete` ack when async beacons (`wifi_retry`, `ntp_synced`, ...) ate the USB-CDC TX ring while the host was streaming. Background beacons are now suppressed while OTA is active, and the host drains the device between chunks.

## [0.3.1] - 2026-05-24

### Added
- Auto-update via GitHub releases: the tray app checks every 4 hours, notifies when a new version is available, and can download + replace + relaunch itself in one click. Repo is now public (no token required).
- Offline mode for the presence helper: when the BusyLight is plugged into the same machine, the helper talks to it over USB serial as the primary transport and falls back to HTTP only if no compatible USB port is found.
- Firmware runtime serial commands: `{"cmd":"set_state","state":0..5}`, `{"cmd":"get_state"}`, `{"cmd":"get_info"}` (host / fw / wifi / IP).
- Tray icon shows a small white badge when running over USB so it's obvious at a glance which channel is active.
- Distributable single-file Windows executables: `BusyLightSetup.exe` and `BusyLightPresence.exe` (no Python required on the end-user machine).

## [0.3.0] - 2026-05-23

### Added
- Autonomous `ready` beacon from firmware after USB CDC enumeration so wizard handshake never relies on a bare ping.
- AP captive portal fallback (`BusyLight-XXXX-Setup`) when WiFi credentials fail 3 times in a row.
- Factory reset over USB (`{"cmd":"factory_reset","confirm":"YES"}`) and over Web API (`POST /api/device/factory_reset` with `X-Confirm: YES`).
- PBKDF2-HMAC-SHA256 (10000 iterations, 16-byte per-device salt) for PIN storage.
- CSRF double-submit cookie (`BLCSRF`) enforced on every mutating endpoint.
- Multi-session auth, up to 4 concurrent tokens with LRU eviction.
- Unique mDNS hostname `busylight-XXXX.local` using last 4 hex chars of the MAC.
- OTA firmware update via authenticated web upload at `POST /api/firmware/update`.
- LittleFS recovery HTML served when the data partition cannot be mounted.
- Firmware unit tests for auth lockout, session TTL, PBKDF2 RFC 6070 vector, LED blink patterns, config store roundtrip, hostname generation.
- Python wizard tests with `FakeSerial` mock covering handshake, configuration flow, and error paths.
- GitHub Actions: firmware build, wizard build, and tag-triggered release pipeline.
- MIT License, README with hardware BOM and quick start, CONTRIBUTING, SECURITY, CHANGELOG.

### Changed
- WiFi reconnect now uses exponential backoff (1s, 2s, 5s, 10s, 30s, 60s) instead of a fixed 10s loop.
- Status state changes are debounced before persisting to NVS to reduce flash wear.
- `DynamicJsonDocument` replaced by ArduinoJson 7's `JsonDocument` everywhere.
- Wizard auto-detects ESP32 boards by USB VID (0x303A, 0x10C4, 0x1A86) and pre-selects the matching COM port.
- Wizard pre-asserts DTR after opening the port so ESP32-C6 native USB CDC reliably accepts the first bytes.

### Fixed
- Serial handshake silently failed on fresh devices because the firmware emitted output before the host had opened the USB CDC endpoint.
- WiFi reconnect loop re-called `WiFi.mode()` + `WiFi.begin()` every 10 seconds, which could destabilize the WiFi stack.
- `lastState` could persist as `WIFI_ERROR` across reboots; it now coerces to `AVAILABLE`.
- mDNS responder was not restarted after a WiFi disconnect/reconnect cycle.

### Security
- PIN is no longer hashed with bare SHA-256. Legacy v0.1.0 hashes are accepted once and re-hashed with PBKDF2 on the first successful login.
- All state-changing API routes require a CSRF token bound to the session.
- OTA upload requires both a valid session cookie and a CSRF token.

## [0.1.0] - 2026-05-22

Initial prototype.

### Added
- ESP32-C6 firmware with 5 LED states (AVAILABLE, BUSY, IN_CALL, AWAY, WIFI_ERROR).
- HTTP web UI with PIN auth and session cookie.
- USB serial provisioning protocol (JSON over CDC).
- Windows setup wizard (Tkinter + PyInstaller).
- Persistent configuration in NVS (SSID, WiFi password, PIN hash, last state).

[Unreleased]: https://github.com/DennisSepede/busylight/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DennisSepede/busylight/releases/tag/v0.1.0
