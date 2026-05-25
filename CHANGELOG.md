# Changelog

All notable changes to BusyLight are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.11] - 2026-05-25

### Changed
- Auto-update check now fires ~3 seconds after launch (down from 20 s) and then every **1 hour** (down from 4 h). A user who downloads a slightly-stale exe sees the "Update available" prompt immediately. The periodic interval is short enough that releases pushed during a working day get picked up by the next coffee break.
- The same background loop now also probes the device's firmware version over USB and compares it to the latest GitHub release. If the device is behind, a tray balloon notifies and a new dynamic menu item enables itself: **"Install device firmware vX.Y.Z…"**.

### Added
- One-click firmware update from the dynamic menu item: triggers the existing USB-OTA flow, and if the device rejects the signature (`signature_invalid` — old / mismatched public key embedded), **automatically falls back to factory reflash via esptool** without making the user pick a different menu item.

### Why this matters now
v0.3.5..0.3.10 ran the update check every 4 hours after a 20 s warm-up, so anyone restarting the exe (e.g. to test a new build) effectively never got a check in. Combined with the fact that the firmware update was a separate manual action, the helper kept the same firmware on the device through 5+ releases. v0.3.11 makes both updates immediate at launch and gives them a single one-click button.

## [0.3.10] - 2026-05-25

### Fixed (the actual LED bug)
- **`networkingTick` was hammering the LED with `setState(WIFI_ERROR)` on every loop iteration** (~200 Hz). Two effects:
  1. The LED blink pattern never advanced — every iteration reset `lastToggleMs_` to 0, so the engine never finished the 400 ms interval needed to toggle. Result: solid red instead of the alternating red/green WIFI_ERROR pattern.
  2. Any user-set state from the web UI or Serial was instantly overwritten on the next loop tick — so clicking AVAILABLE in the web UI flashed the LED green for a few ms before networkingTick reverted it to (solid) WIFI_ERROR red.
- Fix: track whether the overlay has already been applied (`gErrorLedApplied`) and only call `setState` once per transition. On reconnect, restore `gConfig.lastState` from NVS instead of leaving the LED on the error pattern.
- The v0.3.9 LED initial-outputs fix was correct but insufficient on its own — the real fault was the per-tick re-apply in networkingTick.

## [0.3.9] - 2026-05-25

### Fixed
- Firmware LED: AWAY / IN_CALL / WIFI_ERROR didn't reset the red/green output flags on `setState`, so switching from BUSY to AWAY/IN_CALL kept the device looking like BUSY (red solid) for one blink interval before the new pattern kicked in. Dennis reported the worst case: the LED appeared stuck red even after the web UI confirmed the state change. Fixed by setting the correct initial outputs for every state branch and starting the blink phase in the "on" half-cycle so the new colour shows immediately.
- Firmware version embedded in the binary was still "0.3.6" from v0.3.5 / v0.3.6 builds — every v0.3.7 / v0.3.8 firmware artifact reported `"version":"0.3.6"` in the web UI even though the GitHub release was labelled differently. Bumped to "0.3.9".

## [0.3.8] - 2026-05-25

### Added
- Tray menu item **"Reflash from factory (USB)…"**: bundles `esptool` and writes the combined `firmware.factory.bin` (bootloader + partitions + app) over the USB cable. Bypasses the running app's OTA signature check, so this is the escape hatch when the device's embedded public key doesn't match the one used to sign current releases. NVS (PIN, saved Wi-Fi, schedule) is preserved.
- GitHub release assets now include `firmware-X.Y.Z.factory.bin` next to the OTA pair.

### Why this exists
A device flashed with a different / older signing key will reject every OTA update with `signature_invalid`. The OTA path can't fix itself because the signature check runs *before* the new image is committed. The factory reflash writes the new firmware (with the current public key embedded) directly to flash, after which OTA updates work normally again.

## [0.3.7] - 2026-05-25

### Added
- Tray menu item "Update firmware via USB…". Pulls the latest signed `.bin` + `.sig` from the GitHub release, streams it to the device over USB serial, and waits for the post-OTA reboot. Works without Wi-Fi, no manual `.bin` download / web UI upload step. Useful when the device is on an older firmware that doesn't have the new `wifi_list` / `wifi_remove` runtime commands and the bridge can't show saved networks correctly.

## [0.3.6] - 2026-05-25

### Changed
- **The desktop app now hosts the firmware's own web UI locally and serves it over USB.** The presence helper bundles the same `index.html` / `styles.css` / `app.js` the firmware ships, spins up a local HTTP server on `127.0.0.1:<random>`, and proxies `/api/*` requests to the device over USB serial. The tray click opens that local URL inside a WebView2 window. End result: identical look and feel to opening the device's `busylight-xxxx.local` page in the browser, but it works without Wi-Fi.
- Login on the bridge accepts any PIN (or none) — a connected USB cable already implies physical access, same trust model the wizard uses for provisioning.

### Added
- Firmware: `{"cmd":"wifi_list"}` and `{"cmd":"wifi_remove","ssid":"..."}` runtime commands, mirroring `GET /api/wifi` and `DELETE /api/wifi` over the existing USB JSON protocol. Lets the bundled web UI manage Wi-Fi networks even when the device itself has no network.

### Removed
- Custom `dashboard_window.py` (the new bridge + WebView gives the exact web UI the firmware already designed; no need for a parallel one in CTk).

### Known limitations in bridge mode
- Schedule / MQTT / firmware OTA / device reboot via the web UI return 503 from the bridge (they need the live device state Wi-Fi provides). The dedicated USB OTA path from the presence menu remains.

## [0.3.5] - 2026-05-25

### Changed
- **Dashboard is now the default landing page again** (back from the WebView-as-default detour). Tray click always opens the dashboard, which works whether or not the device is on Wi-Fi. No more being forced into the setup wizard when Wi-Fi isn't configured.

### Added
- "Add Wi-Fi" button right on the dashboard: opens a small dialog (SSID + password) that posts the new network to the device over USB via the new firmware `wifi_add` command. Adds to the saved list, doesn't reset anything else.
- "Open device web UI" button on the dashboard: enabled only when the device's `get_info` reports `wifi=true` and an IP. Opens the WebView (or the system browser as fallback). Pure opt-in, never forced.
- Firmware: new `{"cmd":"wifi_add","ssid":"...","password":"..."}` runtime command — same semantics as `POST /api/wifi` but reachable over USB.

### Fixed
- Custom dashboard was removed in 0.3.4 in favour of a WebView-only flow that forced the user into the setup wizard when Wi-Fi wasn't configured. That UX was wrong: the desktop app must work via USB alone, with Wi-Fi being an optional convenience. Restored the dashboard and made Wi-Fi-adding a button rather than a forced flow.

## [0.3.4] - 2026-05-25

### Changed
- The presence app no longer ships a custom dashboard. Tray click now opens the **device's own web UI inside a native WebView2 window** — same Wi-Fi card, schedule, MQTT, OTA, etc. that you already use from a browser, just framed in a desktop window. Decision: rebuilding every card in customtkinter was visibly inferior to the web UI, and missing the Wi-Fi-add flow entirely.
- Both `BusyLightSetup.exe` and `BusyLightPresence.exe` now ship with a UAC manifest (`--uac-admin`) so Windows prompts for elevation automatically on first launch instead of failing silently when the user double-clicks without "Run as administrator".

### Added
- WebView fallback when the device is reachable over USB but has no Wi-Fi network configured: small customtkinter window explaining the situation with a one-click "Launch setup wizard" button that spawns `BusyLightSetup.exe`.
- Graceful "Open in browser" fallback if WebView2 runtime isn't available on the host.

### Removed
- `dashboard_window.py` (custom CTk dashboard, superseded by WebView).

## [0.3.3] - 2026-05-25

### Added
- Premium presence app UI: tray click now opens a dashboard window with a live LED bead (160 px, same Pillow renderer the tray icon uses), the current state in large type, a connection banner ("Connected over USB · COM3" / "Connected over Wi-Fi · busylight-xxxx.local"), one-tap state buttons (Available / Busy / In call / Away / Off), and per-state time-spent-today stats.
- Settings window rebuilt in customtkinter: small LED bead header, live USB-detection banner, "Wi-Fi (optional)" card, polling slider with live value, "Default state" segmented control. Visual language matches the web UI (iOS-like palette, soft grey cards, JetBrains Mono for PIN/IP).
- Shared `bead.py` Pillow renderer so the tray icon, settings header, and dashboard hero all draw the same LED bead at any size.

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
