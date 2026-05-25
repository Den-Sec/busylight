# Changelog

All notable changes to BusyLight are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.19] - 2026-05-25

### Added
- **Update log**: the self-update `.bat` now writes every step (timestamps, `move` errorlevel, retry count, `start` errorlevel, "gave up after 30 retries" if the move never wins) to `%TEMP%\busylight-update.log`. New tray menu entry "View last update log" opens it in Notepad. When the update appears to silently do nothing, the log says exactly why — file lock that never released, antivirus quarantine, missing source path, etc.

## [0.3.18] - 2026-05-25

### Fixed
- **OTA failed with "no JSON reply within timeout" when the dashboard was open in the background**: the bundled web UI polls `/api/state` every couple of seconds. That polling went through the bridge → opened the COM port → raced the live OTA reader for the same handle → OTA `readline()` returned empty → timeout. The presence loop already paused itself during OTA, but the bridge didn't, so anything that polled the dashboard kept opening the port.
  - The bridge now has a `suspended` flag. Both `_firmware_ota_via_usb` and `_factory_reflash` flip it on before they touch the COM port and back off when done. While suspended, every Serial-touching endpoint returns 503 immediately without opening the port, so dashboard polling can't interfere with the OTA stream.

## [0.3.17] - 2026-05-25

### Fixed
- **Auto-update appeared to succeed but the old exe stayed in place**: the `.bat` did a single `move /y` after a 2 s wait. That wasn't enough — Windows can hold the file lock on the just-exited PyInstaller exe for several seconds (bootloader teardown, AV scanning the new file). The single `move` silently failed and the user was left on the previous version with no error. The relaunch then started the still-old exe.
  - The self-replace `.bat` now waits 3 s, then retries `move /y` up to 30 times with 1 s spacing. As soon as the move succeeds it relaunches the new exe; if all 30 retries fail it leaves the new exe in place so the user can swap manually.
  - The Python side now calls `os._exit(0)` instead of `sys.exit(0)`, so daemon threads + pystray's Windows message loop don't keep the file lock alive after the "exit".
  - The tray icon, bridge HTTP server, and presence loop are stopped cleanly before the hard exit.

## [0.3.16] - 2026-05-25

### Fixed
- **PIN change from the web UI didn't actually change the PIN**: the bridge fake-accepted `POST /api/settings/pin` because, by design, the bridge doesn't gate anything (the USB cable is the trust boundary). But the device firmware still held the old PIN in NVS, so the device's own web UI (over Wi-Fi) kept rejecting the new PIN. Now both the bridge and the firmware have a real `set_pin` path: bridge proxies it through serial, firmware validates length/digits, hashes with PBKDF2, and saves to NVS.
- **Firmware artifacts in v0.3.13/14/15 were the v0.3.12 binary repackaged** — the firmware code hadn't changed in those releases. After a successful factory reflash the device kept reading "0.3.12" in the web UI. Rebuilt the firmware fresh with `BUSYLIGHT_VERSION="0.3.16"` so the embedded version matches the release tag.

### Added
- OTA error messages now include the SHA-256 the device computed over the bytes it received: `signature_invalid:received_sha=<hex>`. Compared with the SHA the host signed, this nails down whether the corruption happens on the USB-CDC wire (different SHAs) or in our crypto code (same SHA, signature still fails). Diagnostic step toward fixing the `signature_invalid` Dennis keeps hitting on his PC.

## [0.3.15] - 2026-05-25

### Fixed
- **"Factory reset device" from the tray failed with "no JSON reply within timeout"**: the device acks `cmd:factory_reset` with `event:factory_reset_ok` and then restarts. That event name is in our async-beacon skip list (it can also appear at boot in some recovery paths), so the standard `_roundtrip` flow filtered it out and waited indefinitely for "the real reply" that would never come. `factory_reset` now uses a dedicated fire-and-forget path: write the command, briefly look for the ack with a tight timeout, accept "device is already restarting" as a normal outcome.
- **Web UI "Factory reset" inside the bundled dashboard returned "needs_wifi_or_dedicated_flow"**: the bridge had marked `POST /api/device/factory_reset` as a Wi-Fi-only endpoint. Now it forwards to the serial `factory_reset` cmd just like the tray menu item, so resetting from either the dashboard or the tray works identically.

## [0.3.14] - 2026-05-25

### Fixed
- **Tray menu stopped responding while the dashboard was open**: WebView2 and pystray both want the main thread for their message loop on Windows, so opening the dashboard blocked tray right-clicks until the WebView window closed. The dashboard now runs on a worker thread, leaving the tray reactive. Clicking "Open BusyLight" a second time with the window already open is a no-op (Windows brings the existing one to front).
- **Update flow had almost no feedback**: a single "Downloading…" balloon, then silence, then UAC prompted out of nowhere — easy to read as "nothing happened". Installing now shows a modal progress dialog with a real progress bar, MB-of-MB counter, current step ("Downloading…", "Restarting…"), and an explicit "Approve the Windows UAC prompt when it appears" hint before the relaunch.



### Fixed
- **IN_CALL reverted after ~2s when set manually**: the presence loop unconditionally treated IN_CALL as a mic-driven state. When a user clicked IN_CALL in the web UI and the mic was idle, the next tick pushed `last_manual_state` over the top, reverting the LED. Now the loop distinguishes between "presence-pushed IN_CALL (mic was busy)" and "user-set IN_CALL (anywhere else)" via `last_pushed_state` tracking and only reverts the first kind.

### Added
- Tray menu item **"Factory reset device (clears PIN + Wi-Fi)…"**: sends `cmd:factory_reset` to the device over USB, wiping NVS. After the reset the device boots with PIN = `1234` and no saved networks — the escape hatch when the PIN gets out of sync between the bridge and the firmware (Dennis hit this after several update cycles).

## [0.3.12] - 2026-05-25

### Fixed
- IN_CALL blink interval was 250 ms (4 Hz red). At that rate the eye smooths the oscillation and IN_CALL looked indistinguishable from BUSY (solid red). Slowed to 500 ms (1 Hz), which is clearly distinct from BUSY but still reads as "active / attention" rather than "idle".
- `BUSYLIGHT_VERSION` macro in `platformio.ini` was still "0.3.10" when v0.3.11 firmware artifacts were uploaded (the v0.3.11 release re-used the v0.3.10 binary because only the presence helper had changed). Devices flashed from v0.3.11 reported "0.3.10" in the web UI Settings tab and never stopped seeing "update available" prompts. Bumped to "0.3.12" with a fresh build so the version inside the binary matches the release tag.

### Notes on the `signature_invalid` problem
The embedded public key and the private key used to sign releases are confirmed to be a matched RSA-2048 pair, so the failure is **not** a keypair mismatch. On Dennis's PC it persists across retries on the USB-OTA path, but the factory reflash (esptool write_flash) succeeds — pointing at byte-level corruption somewhere in the USB-CDC stream that only affects the SHA-256 used to verify. The auto-fallback added in v0.3.11 covers it transparently for now; a future release will surface the device-side SHA so we can diagnose without guessing.

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
