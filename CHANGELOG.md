# Changelog

All notable changes to BusyLight are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
