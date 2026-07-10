# BusyLight M1 — "Always-on + roaming without drops" Design Spec

Date: 2026-07-10
Owner: Dennis Sepede
Status: Approved for planning
Scope: Milestone 1 of the "perfect daily use" roadmap

## 1. Goal and context

Make BusyLight a flawless **daily driver** across the three contexts the owner
actually uses:

- **(a) Office Wi-Fi** and **(b) Home Wi-Fi** — carry the device between the two
  and it reconnects automatically and fast, no re-provisioning.
- **(c) "On the go" = USB-anywhere** — the device travels in a bag with the
  laptop and is used **USB-only** (cafe, client site, train) with **no
  internet**. The desktop tray app must work perfectly over USB alone and
  recover cleanly from unplug/replug and COM-port changes.

Both interfaces stay in scope: the ESP-hosted **web app** and the **desktop
app** (`presence_helper`).

M1 is the "always-on + roaming" milestone: the single most important daily
property — *"it's just always running and always shows the right thing"* — is
currently broken in specific, code-identified ways. M1 fixes exactly those.

### Explicitly OUT of scope
- **Any internet/cloud/remote access** (owner decision). No relays, no
  internet-facing TLS, no remote control. If a subsystem exists only to serve
  remote use (MQTT), it is left untouched here and revisited in M5.
- Milestones **M2–M5** (see §8) — auto-presence quality, release pipeline
  backbone, onboarding roaming UX, dead-weight cleanup. Each gets its own spec.

## 2. What is already good (do not regress)

Grounded in the code audit — these are correct today and M1 must preserve them:

- Firmware stores up to 6 networks and uses `WiFiMulti` to pick the strongest
  remembered AP (`firmware/src/main.cpp:97-106,196-204`). Real roaming exists;
  M1 fixes *when it gives up*, not the picking logic.
- Reboot-free runtime Wi-Fi management already exists over both HTTP and USB
  (`wifi_add` / `wifi_list` / `wifi_remove`, `main.cpp:550-618`).
- USB-first transport with HTTP fallback and open-write-close serial (so the
  port is never held exclusively) — `transport.py`, `serial_client.py`.
- Auth (PBKDF2 / CSRF / rate-limit), LED engine, NVS state persistence.

## 3. Design decisions (approved)

- **AP-portal policy = "last resort" (Option A).** The device retries known
  networks forever with the existing capped backoff; it opens the setup AP
  **only** when BOTH (a) no USB host is attached AND (b) an active scan has seen
  **none** of the saved SSIDs continuously for a grace period (default 5 min).
  This preserves automatic recovery when the home router changes and the laptop
  is not plugged in, while eliminating the false-drops and COM-tearing reboots.
- **No cloud** (see §1 out-of-scope).
- **Windows-only distribution** for the desktop app remains an accepted choice
  for the owner's laptop; M1 does not add cross-platform packaging.
- **Start-at-login is default-on** for the desktop app, via a per-user HKCU Run
  key plus a tray toggle.

## 4. Changes — Firmware (`firmware/`)

Every item lists the current behavior with evidence, the target behavior, and
acceptance criteria.

### F1. Stop abandoning known networks after ~8 s
- **Now:** `kMaxStaFailuresBeforeAp = 3` (`main.cpp:26`) with backoff 1s/2s/5s
  means ~3 failures (~8 s) trigger `enterApPortal()` (`main.cpp:303-306`).
  `WiFiMulti.run(2000)` (`main.cpp:202`) often cannot finish a 2.4 GHz scan in
  2 s, so a present-but-slow AP is wrongly declared unreachable.
- **Target:** Retry known networks indefinitely with the existing backoff
  (`kWifiBackoffMs`, capped 60 s). Give the association a real budget: raise the
  `WiFiMulti.run(...)` timeout to ~6000 ms (or run an explicit `WiFi.scanNetworks`
  and only count a failure when no saved SSID appears in the scan).
- **AP entry** is gated by the new policy (F5), not by a blind failure count.
- **Accept:** With a reachable saved AP that takes 3–6 s to come up (or a router
  that boots after the device), the device connects and never enters the setup
  AP. Reconnect after a link loss uses backoff and eventually rejoins without a
  reboot.

### F2. Never `ESP.restart()` while a USB host is attached
- **Now:** AP-portal timeout reboots after 10 min (`main.cpp:222-227`); the
  post-provision path and pending device actions also `ESP.restart()`
  (`main.cpp:219-220,320-321,668-677`). Any restart tears down USB-CDC → the COM
  port drops → the desktop app momentarily loses the device.
- **Target:** Guard every autonomous/idle restart with "USB host present" (F4).
  While a host is attached: do not enter the AP timeout reboot; defer
  non-user-initiated restarts. **Explicit** user actions (factory reset,
  reboot-from-UI, post-OTA restart) still reboot — those are intentional.
- **Accept:** A device with saved-but-currently-unreachable networks, plugged
  into the laptop at a cafe, never reboots on its own; the COM port stays stable
  for the whole session.

### F3. Keep the LED under USB control when there is no Wi-Fi
- **Now:** `enterApPortal()` and the not-connected path force
  `STATUS_WIFI_ERROR` (`main.cpp:191,240-243,279-282`), overriding a state the
  user set over USB ~8 s earlier.
- **Target:** When a USB host is driving state (a serial `set_state` was
  received), the user-set state owns the LED. The "no Wi-Fi" condition must not
  overwrite it. Wi-Fi-error indication is suppressed (or made subtle) while a
  host is present; it may still be shown when the device is standalone (no host,
  no Wi-Fi) as a genuine error cue.
- **Accept:** Set BUSY over USB at a cafe (no Wi-Fi) → the LED stays BUSY
  indefinitely; it is never flipped to the error/AP pattern while plugged in.

### F4. "USB host present" primitive (new)
- **Target:** A small helper that reports host-present = true when `(bool)Serial`
  (DTR asserted) OR any serial line/command was received within the last N
  seconds (default ~15 s). Used by F1/F2/F3/F5.
- **Accept:** Unit/native-testable decision function; host-present flips true on
  the first serial command and false after N seconds of silence with DTR low.

### F5. Gate AP entry on the approved "last resort" policy
- **Target:** Enter the AP portal only when host-present is false AND an active
  scan has found none of the saved SSIDs continuously for the grace period
  (default 5 min, compile-time constant). Otherwise keep retrying STA.
- **Accept:** Standalone device (no host) whose saved networks are all absent
  opens the AP after ~5 min, not ~8 s. With a host attached it never auto-opens
  the AP.

### F6. Re-register the mDNS HTTP service on every reconnect
- **Now:** On reconnect the code calls `MDNS.end(); MDNS.begin(host)`
  (`main.cpp:255-256`) but does **not** re-add the service; `addService("http",
  "tcp", 80)` runs only once in `startServerIfNeeded()` (`main.cpp:168-170`,
  guarded by `gServerStarted`).
- **Target:** After the reconnect `MDNS.begin()`, also call
  `MDNS.addService("http", "tcp", 80)`.
- **Accept:** After an office→home roam, `busylight-XXXX.local` resolves AND the
  `_http._tcp` service record is present (service-browse clients still find it).

## 5. Changes — Desktop app (`presence_helper/`)

### D1. Drop `--uac-admin`; run per-user
- **Now:** `build_exe.ps1:31` passes `--uac-admin`, embedding a
  `requireAdministrator` manifest. Windows then skips the app when launched from
  the HKCU Run key at login, and prompts UAC on every launch and every
  self-update. Nothing the app does needs admin (WebView2, pystray, esptool over
  an already-enumerated COM port all work unelevated).
- **Target:** Remove `--uac-admin`. Distribute/run per-user (e.g. install path
  under `%LOCALAPPDATA%\Programs\BusyLight`). If any single action ever needs
  elevation, request it just-in-time — never elevate the whole app.
- **Accept:** Double-click launch shows no UAC prompt; the login Run-key entry
  starts the app automatically at next logon.

### D2. Start-at-login: real and default-on
- **Now:** `--install-startup` writes the HKCU Run key (`main.py:237-260`) but
  it is only mentioned in the build script's output; the tray never registers
  it, and with `--uac-admin` Windows would not honor it anyway.
- **Target:** With D1 done, register the Run key on first run by default, and
  add a tray toggle "Start at login" (checked by default) wired to the existing
  `_install_startup` / `_uninstall_startup`.
- **Accept:** After first run, the Run key exists; toggling the tray item
  installs/removes it; the app starts at logon with no prompt.

### D3. Never leave the app dead after a failed update
- **Now:** The self-replace `.bat` give-up branch (`updater.py:327-337`) logs
  "gave up after 120 retries" and `goto :done`, which only self-deletes. The old
  process already `os._exit(0)`'d (`updater.py:270-272`); the move failed, so
  nothing is running.
- **Target:** In the give-up branch, relaunch the still-present old exe
  (`start "" "<target>"`, which after a failed move still holds the old binary)
  before `:done`, so the tray is always running afterward — updated on success,
  the previous version on failure.
- **Accept:** With the new exe held locked so the move never wins, the app is
  running again (old version) after the updater finishes; the update log
  records the fallback.

### D4. Pick the COM port by ping, not by index
- **Now:** `transport._refresh_serial` uses `chosen = ports[0]`
  (`transport.py:146`); `find_busylight_ports()` matches VIDs including generic
  CH340/CP210x (`serial_client.py:83-114`), so an unrelated adapter at a dock can
  become `ports[0]` and mask the BusyLight.
- **Target:** Iterate all VID-matched candidates, `ping()` each
  (`serial_client.py:141-148` already exists), and keep the first that answers
  `pong`; cache it. Fall through to HTTP only if none answer.
- **Accept:** With a decoy CH340 present alongside the BusyLight, the transport
  selects the BusyLight; removing the BusyLight only (decoy still present) yields
  "disconnected", not a false serial bind.

### D5. Fast reacquire when disconnected
- **Now:** `SERIAL_RESCAN_INTERVAL_S = 30.0` flat (`transport.py:40`).
- **Target:** While in the disconnected state, rescan every ~2–3 s; keep a cheap
  cadence when already connected (only rescan on failure). COM enumeration is
  ~80 ms, negligible at 3 s spacing.
- **Accept:** Plugging in the cable makes the tray reflect "connected over USB"
  within ~3 s, not up to 30 s.

### D6. Single-instance guard
- **Now:** No process-level guard exists (`tray.py` has none; the only guard is
  around the WebView window). A login-autostart copy plus a manual launch run
  two trays / mic monitors / updaters that race over the COM port.
- **Target:** Acquire a named mutex (Windows) or lockfile at startup; if already
  held, bring the existing instance to front (or exit quietly).
- **Accept:** Launching a second copy does not create a second tray icon or a
  second updater; only one instance runs.

### D7. Crash-proof config load
- **Now:** `poll_seconds = float(poll)` (`config.py:103`) raises `ValueError` on
  a non-numeric INI value; `main()` then references `cfg` in the except path
  (`main.py:357`) although `cfg` was never assigned (the assignment at
  `main.py:343` threw) → `UnboundLocalError` → the tray never launches → the app
  is dead with no in-app recovery.
- **Target:** In `load_config`, guard `float(poll)` and fall back to the default
  (2.0) on a bad value. In `main()`, pre-bind `cfg` to a safe default before the
  `try`, so a bad config opens the Settings window instead of crashing.
- **Accept:** With a garbage `poll_seconds` in the INI, the tray launches and
  opens Settings; the app is never left dead by a bad config value.

## 6. Verification strategy

Follows the owner's rule: verify in the real device/app, not just tests.

- **Firmware (device on COM3):** build with PlatformIO, flash over USB, then:
  1. No known network → no AP drop within 8 s, no autonomous reboot, `set_state`
     over USB controls the LED and holds (F1/F2/F3/F5).
  2. Two saved SSIDs; toggle the two APs to emulate office→home → auto-reconnect
     without reboot; `busylight-XXXX.local` + `_http._tcp` survive the roam (F6).
  3. Confirm no `ESP.restart()` fires while the port is open (watch the CDC link
     stay up) (F2).
- **Desktop app (real run):**
  1. Unplug/replug the device, and add a decoy CH340 → ping-based selection and
     ~3 s reacquire (D4/D5).
  2. Force a failed self-update (lock the new exe) → the app relaunches (D3).
  3. Put garbage in `presence.ini` → Settings opens, no crash (D7).
  4. Verify the HKCU Run key registers and the app starts at logon with no UAC
     (D1/D2); launch a second copy → single instance (D6).
- **Automated tests (extend existing suites):**
  - `presence_helper`: transport port-selection-by-ping; `load_config` bad-poll
    fallback; give-up-relaunch bat generation.
  - `firmware`: native test for the F4 host-present decision and the F5 AP-gate
    decision; assert `addService` is invoked on the reconnect path where the test
    harness allows.

## 7. Risks and mitigations

- **DTR semantics on ESP32-C6 native USB-CDC** may make `(bool)Serial` flap.
  Mitigation: base host-present primarily on "serial command seen within N s",
  with DTR as a secondary signal; make N and the AP grace period compile-time
  constants for field tuning.
- **Longer scan budget (~6 s) slightly slows first connect.** Mitigation: keep
  the LED responsive (tick runs regardless); the trade is worth it to stop false
  AP drops. Tunable constant.
- **Removing `--uac-admin`** could surface an action that silently relied on
  elevation. Mitigation: audit the esptool/reflash and update paths during
  implementation; add just-in-time elevation only where a concrete need is
  proven.
- **Dropping the 10-min AP reboot** removes a coarse self-heal. Mitigation: the
  indefinite-retry loop plus the last-resort AP (F5) is a strictly better
  self-heal for the target scenarios; standalone devices still recover via the
  AP after the grace period.

## 8. Roadmap context (later milestones, not this spec)

- **M2 — Trustworthy presence:** mic allowlist/denylist of meeting apps,
  on/off debounce, auto-AWAY on session lock / idle.
- **M3 — Release backbone:** single source of truth for version derived from the
  git tag across firmware + both Python packages; CI signs and ships the correct
  (app) image and correctly-named factory asset; version-consistency release
  gate; presence helper + firmware native tests in CI. (Ends the recurring
  `signature_invalid` / version-drift firefights.)
- **M4 — Onboarding roaming UX:** wizard verifies real Wi-Fi association,
  reboot-free add-network, PIN decoupled from provisioning, Wi-Fi-preserving USB
  PIN reset.
- **M5 — Dead-weight cleanup under no-remote scope:** gate/remove MQTT, make the
  on-device scheduler opt-in with a grace window, delete stale artifacts.

## 9. Acceptance for M1

M1 is done when, on the owner's real hardware and laptop:
1. Carrying the device between two saved networks reconnects automatically with
   no re-provision and no self-reboot; `busylight-XXXX.local` keeps working.
2. Used USB-only with no reachable Wi-Fi, the device never drops the COM port,
   never reboots on its own, and the LED obeys USB `set_state`.
3. The tray app starts at login with no UAC, runs as a single instance, reflects
   plug-in within ~3 s, selects the correct COM port among decoys, survives a
   failed update, and survives a bad config file.
