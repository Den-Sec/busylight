# BusyLight M1 — Always-on + Roaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BusyLight a flawless daily driver across office Wi-Fi, home Wi-Fi, and USB-anywhere by stopping the firmware from abandoning known networks / rebooting while USB is attached, and making the desktop tray app genuinely always-on and USB-robust.

**Architecture:** Two independent phases. **Phase A (firmware, ESP32-C6/PlatformIO)** extracts the two new decisions — "is a USB host attached?" and "should we fall back to the setup AP?" — into small pure classes (unit-tested off-device), then wires them into `main.cpp`'s networking loop and fixes the mDNS-on-reconnect gap. **Phase B (desktop, Python/pytest)** makes the tray app run per-user without UAC, start at login, run as a single instance, pick the COM port by ping, reacquire fast, and survive both a failed self-update and a bad config file. The phases share no code and can be built, reviewed, and merged independently.

**Tech Stack:** PlatformIO + Arduino (ESP32-C6), Unity for firmware tests; Python 3.10+, pytest, pyserial, pystray, winreg/ctypes for the desktop helper.

## Global Constraints

Copied verbatim from the design spec (`docs/superpowers/specs/2026-07-10-busylight-m1-always-on-roaming-design.md`). Every task's requirements implicitly include these.

- **No internet/cloud/remote access.** Do not add relays, internet TLS, or remote control. MQTT is left untouched in M1 (revisited in M5).
- **AP-portal policy = "last resort" (approved).** Enter the setup AP only when (a) no USB host is attached AND (b) no saved network has been reachable continuously for the grace period. Otherwise retry station mode forever with the existing backoff.
- **Windows-only desktop distribution** is accepted; do not add cross-platform packaging in M1.
- **Start-at-login is default-on**, per-user (HKCU Run key), no admin.
- **Tunable defaults** (compile-time / module constants): USB-host-present window = **15 s**; AP-portal grace period = **5 min** (`5*60*1000` ms); `WiFiMulti.run` association budget = **6000 ms**; desktop serial rescan while disconnected = **3 s**, while connected = **30 s**.
- **Do not regress** the good primitives: `WiFiMulti` 6-network best-RSSI selection, reboot-free `wifi_add`, USB-first open-write-close transport, PBKDF2/CSRF auth.
- Python: `requires-python >=3.10`, ruff `line-length = 100`. Firmware: ArduinoJson `^7`, ESP32-C6, partitions per `partitions.csv`.

**Prerequisites for execution:** PlatformIO Core (`pio`) installed; the ESP32-C6 device connected on **COM3** and **not** held open by a running `BusyLightPresence.exe` or serial monitor; Python venv for `presence_helper` with dev deps.

---

# Phase A — Firmware

## Task A1: `HostPresence` — "is a USB host attached?" decision

Pure, Arduino-free value class with injected time so it unit-tests off the module's own logic. Present = DTR asserted OR a serial command seen within the last 15 s.

**Files:**
- Create: `firmware/include/host_presence.h`
- Test: `firmware/test/test_host_presence/test_main.cpp`

**Interfaces:**
- Produces: `class HostPresence` with `explicit HostPresence(uint32_t windowMs = 15000)`, `void noteSerialActivity(uint32_t nowMs)`, `void noteDtr(bool asserted)`, `bool present(uint32_t nowMs) const`.

- [ ] **Step 1: Write the failing test**

```cpp
// firmware/test/test_host_presence/test_main.cpp
#include <unity.h>

#include "host_presence.h"

void test_absent_before_any_activity() {
  HostPresence h(15000);
  TEST_ASSERT_FALSE(h.present(0));
  TEST_ASSERT_FALSE(h.present(1000000));
}

void test_present_within_window_after_serial() {
  HostPresence h(15000);
  h.noteSerialActivity(1000);
  TEST_ASSERT_TRUE(h.present(1000));
  TEST_ASSERT_TRUE(h.present(1000 + 15000));   // edge of window
}

void test_absent_after_window_elapses() {
  HostPresence h(15000);
  h.noteSerialActivity(1000);
  TEST_ASSERT_FALSE(h.present(1000 + 15001));
}

void test_dtr_keeps_present_regardless_of_time() {
  HostPresence h(15000);
  h.noteDtr(true);
  TEST_ASSERT_TRUE(h.present(999999));
  h.noteDtr(false);
  TEST_ASSERT_FALSE(h.present(999999));
}

void test_unsigned_wraparound_is_safe() {
  HostPresence h(15000);
  h.noteSerialActivity(0xFFFFFFF0u);           // just before wrap
  TEST_ASSERT_TRUE(h.present(0x00000005u));    // 21 ms later across wrap
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_absent_before_any_activity);
  RUN_TEST(test_present_within_window_after_serial);
  RUN_TEST(test_absent_after_window_elapses);
  RUN_TEST(test_dtr_keeps_present_regardless_of_time);
  RUN_TEST(test_unsigned_wraparound_is_safe);
  UNITY_END();
}

void loop() {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pio test -e esp32c6dev -f test_host_presence`
Expected: FAIL — `host_presence.h` not found / `HostPresence` undefined.

- [ ] **Step 3: Write minimal implementation**

```cpp
// firmware/include/host_presence.h
#pragma once

#include <stdint.h>

// Tracks whether a USB host is actively attached. "Present" means the
// host asserted DTR (opened the port) OR sent a serial command within
// the last `windowMs`. Pure logic (no Arduino deps) + injected time so
// it is unit-testable and safe against millis() 32-bit wraparound.
class HostPresence {
 public:
  explicit HostPresence(uint32_t windowMs = 15000)
      : windowMs_(windowMs),
        lastActivityMs_(0),
        sawActivity_(false),
        dtr_(false) {}

  void noteSerialActivity(uint32_t nowMs) {
    lastActivityMs_ = nowMs;
    sawActivity_ = true;
  }

  void noteDtr(bool asserted) { dtr_ = asserted; }

  bool present(uint32_t nowMs) const {
    if (dtr_) return true;
    if (!sawActivity_) return false;
    // Unsigned subtraction wraps correctly across the 49-day millis()
    // rollover, so this stays valid without a special case.
    return (nowMs - lastActivityMs_) <= windowMs_;
  }

 private:
  uint32_t windowMs_;
  uint32_t lastActivityMs_;
  bool sawActivity_;
  bool dtr_;
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pio test -e esp32c6dev -f test_host_presence`
Expected: PASS — 5/5.

- [ ] **Step 5: Commit**

```bash
git add firmware/include/host_presence.h firmware/test/test_host_presence/test_main.cpp
git commit -m "feat(fw): HostPresence — USB-host-attached decision (F4)"
```

---

## Task A2: `WifiApPolicy` — "should we fall back to the setup AP?" decision

Pure class implementing the approved "last resort" policy. The grace clock resets whenever a saved network is reachable; AP is allowed only after the grace period with no host attached.

**Files:**
- Create: `firmware/include/wifi_ap_policy.h`
- Test: `firmware/test/test_wifi_ap_policy/test_main.cpp`

**Interfaces:**
- Produces: `class WifiApPolicy` with `explicit WifiApPolicy(uint32_t graceMs = 5UL*60UL*1000UL)`, `void begin(uint32_t nowMs)`, `void update(bool savedReachable, uint32_t nowMs)`, `bool shouldEnterAp(bool hostPresent, uint32_t nowMs) const`.

- [ ] **Step 1: Write the failing test**

```cpp
// firmware/test/test_wifi_ap_policy/test_main.cpp
#include <unity.h>

#include "wifi_ap_policy.h"

static const uint32_t GRACE = 5UL * 60UL * 1000UL;  // 5 min

void test_no_ap_within_grace() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(false, 1000);
  TEST_ASSERT_FALSE(p.shouldEnterAp(false, GRACE - 1));
}

void test_ap_after_grace_when_no_host() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(false, 1000);
  TEST_ASSERT_TRUE(p.shouldEnterAp(false, GRACE + 1));
}

void test_never_ap_while_host_present() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(false, 1000);
  TEST_ASSERT_FALSE(p.shouldEnterAp(true, GRACE + 100000));
}

void test_reachable_resets_grace_clock() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(true, GRACE - 1);           // saw a saved network late in the window
  TEST_ASSERT_FALSE(p.shouldEnterAp(false, GRACE + 1));  // clock reset
  TEST_ASSERT_TRUE(p.shouldEnterAp(false, (GRACE - 1) + GRACE + 1));
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_no_ap_within_grace);
  RUN_TEST(test_ap_after_grace_when_no_host);
  RUN_TEST(test_never_ap_while_host_present);
  RUN_TEST(test_reachable_resets_grace_clock);
  UNITY_END();
}

void loop() {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pio test -e esp32c6dev -f test_wifi_ap_policy`
Expected: FAIL — `wifi_ap_policy.h` not found.

- [ ] **Step 3: Write minimal implementation**

```cpp
// firmware/include/wifi_ap_policy.h
#pragma once

#include <stdint.h>

// Decides WHEN to fall back to the setup AP portal (approved "last
// resort" policy). The grace clock resets every time a saved network is
// reachable. The AP is allowed only after `graceMs` of no reachable
// saved network AND no USB host attached. Otherwise the caller keeps
// retrying station mode forever.
//
// NOTE: the wiring feeds `savedReachable = (we are currently associated
// to a saved network)`. A successful association is a stronger signal
// than a passive scan hit (a visible SSID you cannot join would still
// leave you stuck), and it needs no separate async scan. This satisfies
// the spec's daily-use intent; see spec F5.
class WifiApPolicy {
 public:
  explicit WifiApPolicy(uint32_t graceMs = 5UL * 60UL * 1000UL)
      : graceMs_(graceMs), lastReachableMs_(0) {}

  // Start the grace clock (call once at boot with millis()).
  void begin(uint32_t nowMs) { lastReachableMs_ = nowMs; }

  void update(bool savedReachable, uint32_t nowMs) {
    if (savedReachable) lastReachableMs_ = nowMs;
  }

  bool shouldEnterAp(bool hostPresent, uint32_t nowMs) const {
    if (hostPresent) return false;
    return (nowMs - lastReachableMs_) >= graceMs_;
  }

 private:
  uint32_t graceMs_;
  uint32_t lastReachableMs_;
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pio test -e esp32c6dev -f test_wifi_ap_policy`
Expected: PASS — 4/4.

- [ ] **Step 5: Commit**

```bash
git add firmware/include/wifi_ap_policy.h firmware/test/test_wifi_ap_policy/test_main.cpp
git commit -m "feat(fw): WifiApPolicy — last-resort AP fallback decision (F5)"
```

---

## Task A3: Wire the two decisions into networking — retry forever, AP only as last resort

Replace the blind 3-failure AP trigger with the policy, feed it association success, give `WiFiMulti.run` a real budget, and track host presence from serial + DTR. This is Arduino glue in `main.cpp`; verification is on-device (the decision logic itself was unit-tested in A1/A2).

**Files:**
- Modify: `firmware/src/main.cpp`

**Interfaces:**
- Consumes: `HostPresence` (A1), `WifiApPolicy` (A2).

- [ ] **Step 1: Add the objects and includes**

At the includes block (near `firmware/src/main.cpp:8-16`) add:

```cpp
#include "host_presence.h"
#include "wifi_ap_policy.h"
```

In the anonymous namespace, next to `WiFiMulti gWifiMulti;` (`main.cpp:39`), add:

```cpp
HostPresence gHost;       // default 15 s window
WifiApPolicy gApPolicy;   // default 5 min grace
```

- [ ] **Step 2: Give association a real budget and start the grace clock**

In `startStationConnection()` (`main.cpp:196-204`), change the run budget from 2000 ms to 6000 ms:

```cpp
  // Was gWifiMulti.run(2000): a 2 s budget often can't finish a 2.4 GHz
  // scan, so a present-but-slow AP was wrongly declared unreachable.
  gWifiMulti.run(6000);
```

In `setup()`, right after `rebuildScheduler();` (`main.cpp:718`), add:

```cpp
  gApPolicy.begin(millis());
```

- [ ] **Step 3: Track host presence (serial activity + DTR)**

In `handleSerialProvisioning()`, immediately after the command line is read and confirmed non-empty (`main.cpp:466-468`, right after `if (line.length() == 0) return;`), add:

```cpp
  gHost.noteSerialActivity(millis());
```

In `loop()`, at the very top of the function (`main.cpp:731`, before `handleSerialProvisioning();`), add:

```cpp
  gHost.noteDtr(static_cast<bool>(Serial));
```

- [ ] **Step 4: Replace the failure-count AP trigger with the policy**

In `networkingTick()`'s connected branch, refresh the grace clock so the AP grace period is measured from the moment the network becomes unreachable (the drop), NOT from first connect. **This must run on EVERY connected tick, not only on the fresh-connection edge** — otherwise an always-on device connected longer than the grace period would false-drop to the AP within one retry cycle the instant Wi-Fi drops while no USB host is present (the exact ~8 s regression F5 exists to kill). Place it in the `if (isConnected) {` branch AFTER the `if (!gWifiWasConnected) { ... }` reset block closes and BEFORE `startServerIfNeeded();`:

```cpp
    gApPolicy.update(true, millis());  // every connected tick: grace measured from the drop (F5)
```

Then replace the **entire failure/retry tail** of `networkingTick()` (`main.cpp:296-313`) — from the comment `// Backoff elapsed without a successful connection.` through the closing `Serial.printf(... "wifi_retry" ...)` call — with the following (this re-includes the `startStationConnection()` + `nextRetryMs` + `wifi_retry` printf, so make sure you delete the originals at 308-313 too, or you will duplicate them):

```cpp
  // Backoff elapsed without a successful connection. Keep retrying the
  // known networks forever with capped backoff; only fall back to the
  // setup AP as a genuine last resort (no USB host + no saved network
  // reachable for the grace period). This replaces the old blind
  // "3 failures in ~8 s -> AP" trigger that false-dropped office->home
  // roaming and USB-anywhere devices.
  gWifi.attemptIndex =
      static_cast<uint8_t>(gWifi.attemptIndex + 1) %
      (sizeof(kWifiBackoffMs) / sizeof(uint32_t));
  gWifi.failuresTotal++;

  // `now` is already `millis()` from the top of this not-connected path
  // (main.cpp:284). Reuse it instead of re-reading the clock.
  gApPolicy.update(false, now);  // still not associated
  if (gApPolicy.shouldEnterAp(gHost.present(now), now)) {
    enterApPortal();
    return;
  }

  startStationConnection();
  gWifi.nextRetryMs =
      now + kWifiBackoffMs[gWifi.attemptIndex %
                           (sizeof(kWifiBackoffMs) / sizeof(uint32_t))];
  Serial.printf("{\"ok\":false,\"event\":\"wifi_retry\",\"attempt\":%u}\n",
                static_cast<unsigned>(gWifi.failuresTotal));
```

Delete the now-unused constant `kMaxStaFailuresBeforeAp` (`main.cpp:26`).

- [ ] **Step 5: Build and flash the real firmware**

Run:
```
pio run -e esp32c6dev -t upload
pio run -e esp32c6dev -t uploadfs
```
Expected: SUCCESS; device reboots and emits `{"event":"ready",...}` then `{"event":"server_started",...}` on the serial monitor (`pio device monitor -b 115200`).

- [ ] **Step 6: On-device verification (roaming + no false AP-drop)**

1. With a valid saved network present, watch the monitor: the device connects (`server_started`) and **never** emits `ap_portal_started` within the first 30 s.
2. Power off the AP (or move out of range) with the USB cable plugged in: observe `wifi_retry` beacons continuing indefinitely and **no** `ap_portal_started` and **no** reboot (`ready` never re-appears) for at least 5 minutes — because a host is present.
3. Confirm office→home style recovery: bring a second saved AP up; the device reconnects and emits `server_started` again without a reboot.
4. **Host-absent grace check (the case that unit/compile tests can't see):** let the device stay connected for **more than 5 minutes**, then **unplug the USB cable** (so no host is present) and only THEN drop the AP. Watch on a separate power source / the router logs: the device must keep emitting `wifi_retry` and **only** open `ap_portal_started` after the full ~5-min grace measured **from the drop** — not within ~8 s. (This is the path the grace-clock-refresh fix protects; with the cable plugged the host-present short-circuit hides it.)

Record the observations in the commit message.

- [ ] **Step 7: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "feat(fw): retry known networks forever; AP only as last resort (F1,F5)"
```

---

## Task A4: Never auto-reboot or hijack the LED while a USB host is attached

Guard the AP-portal timeout reboot with host-presence, and stop the WIFI_ERROR overlay from overriding a USB-set state.

**Files:**
- Modify: `firmware/src/main.cpp`

**Interfaces:**
- Consumes: `HostPresence gHost` (A1/A3).

- [ ] **Step 1: Guard the AP-portal timeout reboot**

In `networkingTick()` the AP branch reboots after the timeout (`main.cpp:222-227`). Replace that `if (gApPortal.uptimeMs() > kApPortalTimeoutMs) { ... ESP.restart(); }` block with:

```cpp
    if (gApPortal.uptimeMs() > kApPortalTimeoutMs &&
        !gHost.present(millis())) {
      Serial.println("{\"ok\":false,\"event\":\"ap_portal_timeout\"}");
      delay(150);
      ESP.restart();
    }
```

- [ ] **Step 2: Keep the LED under USB control when there is no Wi-Fi**

In `networkingTick()`, the "no networks configured" branch forces WIFI_ERROR (`main.cpp:240-243`). Guard it so a USB-set state wins:

```cpp
    if (!gErrorLedApplied && !gHost.present(millis())) {
      gLed.setState(STATUS_WIFI_ERROR);
      gErrorLedApplied = true;
    }
    return;
```

Do the same for the not-connected overlay (`main.cpp:279-282`):

```cpp
  if (!gErrorLedApplied && !gHost.present(millis())) {
    gLed.setState(STATUS_WIFI_ERROR);
    gErrorLedApplied = true;
  }
```

- [ ] **Step 3: Build, flash, and verify on-device**

Run:
```
pio run -e esp32c6dev -t upload
```
Verification (USB-anywhere, no reachable Wi-Fi):
1. With the cable plugged and no saved network reachable, send `{"cmd":"set_state","state":1}` (BUSY) over the serial port at 115200. Expected: LED goes solid red and **stays** red — it is not flipped to the WIFI_ERROR alternating pattern on the next tick.
2. Send `{"cmd":"set_state","state":0}` (AVAILABLE): LED goes green solid and holds.
3. Confirm no autonomous `ESP.restart()` (the `ready` beacon does not re-appear) for at least 5 minutes with the cable in.

- [ ] **Step 4: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "feat(fw): no auto-reboot / no WIFI_ERROR override while USB host attached (F2,F3)"
```

---

## Task A5: Re-register the mDNS HTTP service on reconnect

After an office→home roam the code re-inits mDNS but drops the `_http._tcp` service record.

**Files:**
- Modify: `firmware/src/main.cpp`

- [ ] **Step 1: Add the service on the reconnect path**

In `networkingTick()`, the fresh-connection block calls `MDNS.end(); MDNS.begin(...)` (`main.cpp:255-256`). Add the service registration right after `MDNS.begin(gDeviceHostname.c_str());`:

```cpp
      MDNS.end();
      MDNS.begin(gDeviceHostname.c_str());
      MDNS.addService("http", "tcp", 80);   // was missing: service record
                                            // vanished after the first roam
```

- [ ] **Step 2: Build, flash, and verify on-device**

Run:
```
pio run -e esp32c6dev -t upload
```
Verification:
1. Connect on network #1, confirm `http://busylight-XXXX.local` opens.
2. Force a disconnect/reconnect (toggle the AP, or `wifi_remove` + `wifi_add` a network) so the reconnect path runs.
3. From another device, browse Bonjour/`_http._tcp` (e.g. `dns-sd -B _http._tcp` on macOS, or just reload `http://busylight-XXXX.local`): the BusyLight is still discoverable and the page loads after the roam.

- [ ] **Step 3: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "fix(fw): re-add _http._tcp mDNS service on reconnect (F6)"
```

---

# Phase B — Desktop app

All Phase B commands run from `presence_helper/` with the dev venv active. Tests: `pytest tests/<file> -q`. Windows-only tests use `@pytest.mark.skipif(sys.platform != "win32", ...)`.

## Task B1: Per-user start-at-login (drop UAC, single startup module, tray toggle, default-on)

Centralise the HKCU Run-key logic in one module, delete the `--uac-admin` manifest so Windows actually honours the login entry, add a tray toggle, and enable start-at-login once on first frozen run.

**Files:**
- Create: `presence_helper/src/busylight_presence/startup.py`
- Test: `presence_helper/tests/test_startup.py`
- Modify: `presence_helper/src/busylight_presence/main.py` (delegate the existing `--install-startup` / `--uninstall-startup` flags; call `ensure_default_startup`)
- Modify: `presence_helper/src/busylight_presence/tray.py` (add "Start at login" checkbox item)
- Modify: `presence_helper/scripts/build_exe.ps1` (remove `--uac-admin`)

**Interfaces:**
- Produces: `startup.enable_startup() -> None`, `startup.disable_startup() -> None`, `startup.is_startup_enabled() -> bool`, `startup.ensure_default_startup(sentinel: Path) -> None`. Module constant `_VALUE_NAME` (monkeypatched in tests).

- [ ] **Step 1: Write the failing test**

```python
# presence_helper/tests/test_startup.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from busylight_presence import startup


@pytest.mark.skipif(sys.platform != "win32", reason="HKCU Run key is Windows-only")
def test_enable_disable_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a test-specific value name so we never touch the real entry.
    monkeypatch.setattr(startup, "_VALUE_NAME", "BusyLightPresenceTest")
    try:
        assert startup.is_startup_enabled() is False
        startup.enable_startup()
        assert startup.is_startup_enabled() is True
    finally:
        startup.disable_startup()
    assert startup.is_startup_enabled() is False


@pytest.mark.skipif(sys.platform != "win32", reason="HKCU Run key is Windows-only")
def test_disable_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup, "_VALUE_NAME", "BusyLightPresenceTest")
    startup.disable_startup()  # not present -> no raise
    startup.disable_startup()


def test_ensure_default_startup_noop_when_not_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Not a frozen exe -> ensure_default_startup does nothing and writes
    # no sentinel (dev runs must not register themselves).
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    sentinel = tmp_path / ".startup_configured"
    startup.ensure_default_startup(sentinel)
    assert not sentinel.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_startup.py -q`
Expected: FAIL — `No module named 'busylight_presence.startup'`.

- [ ] **Step 3: Write the module**

```python
# presence_helper/src/busylight_presence/startup.py
"""Per-user 'start at login' via the HKCU Run key.

Windows-only and admin-free: HKCU (not HKLM) needs no elevation, which
is exactly why the presence exe must NOT ship a requireAdministrator
manifest — Windows silently skips elevated apps from the Run key at
logon.
"""

from __future__ import annotations

import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "BusyLightPresence"


def _target_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # Dev runs go through the module so the venv stays in scope.
    return f'"{sys.executable}" -m busylight_presence'


def enable_startup() -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(
            key, _VALUE_NAME, 0, winreg.REG_SZ, _target_command()
        )


def disable_startup() -> None:
    if sys.platform != "win32":
        return
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        pass


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE
        ) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def ensure_default_startup(sentinel: Path) -> None:
    """Enable start-at-login once, on the first frozen run (default-on).

    Respects a later user opt-out: the sentinel file means "we've already
    made the default choice", so we never re-enable after the user
    disables it from the tray.
    """
    if not getattr(sys, "frozen", False):
        return
    if sentinel.exists():
        return
    try:
        if not is_startup_enabled():
            enable_startup()
    finally:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("1", encoding="ascii")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_startup.py -q`
Expected: PASS (Windows) / the two `skipif` tests skipped + the noop test passing (non-Windows).

- [ ] **Step 5: Delegate the CLI flags and wire first-run default**

In `main.py`, replace the bodies of `_install_startup` / `_uninstall_startup` (`main.py:237-280`) and the `_registry_*` helpers (`main.py:229-234`) with delegation to the new module. Replace lines 229-280 with:

```python
def _install_startup() -> int:
    if sys.platform != "win32":
        print("--install-startup is Windows-only.", file=sys.stderr)
        return 2
    from .startup import enable_startup, _target_command
    enable_startup()
    print(f"Registered to launch at login: {_target_command()}")
    return 0


def _uninstall_startup() -> int:
    if sys.platform != "win32":
        print("--uninstall-startup is Windows-only.", file=sys.stderr)
        return 2
    from .startup import disable_startup
    disable_startup()
    print("Removed login auto-start entry.")
    return 0
```

In `main.py::main()`, right after `_setup_logging(args.verbose)` (`main.py:329`), add the default-on first-run hook:

```python
    from .startup import ensure_default_startup
    from .config import _default_config_path
    ensure_default_startup(_default_config_path().parent / ".startup_configured")
```

- [ ] **Step 6: Add the tray toggle**

In `tray.py`, add the import near the other package imports (`tray.py:31-36`):

```python
from .startup import enable_startup, disable_startup, is_startup_enabled
```

In `run()`'s menu (`tray.py:99`, next to the "Settings…" item) add:

```python
            Item(
                "Start at login",
                self._toggle_startup,
                checked=lambda _i: is_startup_enabled(),
            ),
```

Add the handler method to `TrayApp` (near `_toggle_pause`):

```python
    def _toggle_startup(self, _icon, _item) -> None:
        if is_startup_enabled():
            disable_startup()
        else:
            enable_startup()
```

- [ ] **Step 7: Drop the UAC manifest**

In `scripts/build_exe.ps1`, delete the `  --uac-admin `` line (`build_exe.ps1:31`). The app needs no admin.

- [ ] **Step 8: Verify the wiring**

Run: `pytest tests/test_startup.py tests/test_config.py -q`
Expected: PASS.
Manual (frozen build, optional in dev): after `build_exe.ps1`, double-click `dist/BusyLightPresence.exe` — no UAC prompt appears; the tray "Start at login" item shows checked; the HKCU Run key `BusyLightPresence` exists.

- [ ] **Step 9: Commit**

```bash
git add presence_helper/src/busylight_presence/startup.py presence_helper/tests/test_startup.py presence_helper/src/busylight_presence/main.py presence_helper/src/busylight_presence/tray.py presence_helper/scripts/build_exe.ps1
git commit -m "feat(desktop): per-user start-at-login, drop UAC manifest, tray toggle (D1,D2)"
```

---

## Task B2: Single-instance guard

Prevent a login-autostart copy and a manual launch from running two trays / mic monitors / updaters at once.

**Files:**
- Create: `presence_helper/src/busylight_presence/single_instance.py`
- Test: `presence_helper/tests/test_single_instance.py`
- Modify: `presence_helper/src/busylight_presence/main.py` (acquire early in `main()`)

**Interfaces:**
- Produces: `class SingleInstance` with `__init__(self, name: str = ...)`, `acquire() -> bool` (True if we are the first instance), `release() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# presence_helper/tests/test_single_instance.py
from __future__ import annotations

import sys

import pytest

from busylight_presence.single_instance import SingleInstance


def test_non_windows_always_acquires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    a = SingleInstance("busylight-test-nonwin")
    assert a.acquire() is True
    a.release()


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_second_acquire_is_rejected() -> None:
    name = "Global\\BusyLightPresence_Test_Mutex"
    first = SingleInstance(name)
    second = SingleInstance(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False  # already exists -> not first
    finally:
        first.release()
        second.release()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_single_instance.py -q`
Expected: FAIL — `No module named 'busylight_presence.single_instance'`.

- [ ] **Step 3: Write the module**

```python
# presence_helper/src/busylight_presence/single_instance.py
"""Single-instance guard using a Windows named mutex.

A login-autostart copy plus a manual double-click must not run two
trays / mic loops / updaters at once (they would also race over the one
exclusive COM handle). On non-Windows this is a no-op (the desktop app
is Windows-only anyway).
"""

from __future__ import annotations

import sys

_DEFAULT_NAME = "Global\\BusyLightPresence_SingleInstance"


class SingleInstance:
    def __init__(self, name: str = _DEFAULT_NAME) -> None:
        self._name = name
        self._handle = None
        self._already_running = False

    def acquire(self) -> bool:
        """Return True if we are the first instance, False otherwise."""
        if sys.platform != "win32":
            return True
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR
        ]
        ERROR_ALREADY_EXISTS = 183

        self._handle = kernel32.CreateMutexW(None, True, self._name)
        self._already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        return not self._already_running

    def release(self) -> None:
        if self._handle is not None and sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_single_instance.py -q`
Expected: PASS.

- [ ] **Step 5: Acquire early in `main()`**

In `main.py::main()`, immediately after the `ensure_default_startup(...)` call added in Task B1 Step 5, add:

```python
    from .single_instance import SingleInstance
    _guard = SingleInstance()
    if not _guard.acquire():
        log.info("another BusyLight Presence instance is already running; exiting")
        return 0
```

- [ ] **Step 6: Commit**

```bash
git add presence_helper/src/busylight_presence/single_instance.py presence_helper/tests/test_single_instance.py presence_helper/src/busylight_presence/main.py
git commit -m "feat(desktop): single-instance guard via named mutex (D6)"
```

---

## Task B3: Robust USB port selection (ping) + fast reacquire

Pick the COM port by proving it answers `pong` (not by index), and rescan every ~3 s while disconnected instead of a flat 30 s.

**Files:**
- Modify: `presence_helper/src/busylight_presence/transport.py`
- Test: `presence_helper/tests/test_transport.py`

**Interfaces:**
- Consumes: `find_busylight_ports()` and `SerialClient` (with `.ping() -> bool`, `.login()`), from `serial_client.py`.

- [ ] **Step 1: Write the failing test**

```python
# presence_helper/tests/test_transport.py
from __future__ import annotations

import busylight_presence.transport as transport_mod
from busylight_presence.transport import BusyLightTransport


class _FakeSerial:
    """Stands in for SerialClient: answers ping() only for the real port."""

    instances: list[str] = []

    def __init__(self, port: str) -> None:
        self.port = port
        _FakeSerial.instances.append(port)

    def ping(self) -> bool:
        return self.port == "COM_REAL"

    def login(self) -> None:
        if self.port != "COM_REAL":
            raise RuntimeError("decoy should never be logged in")


def test_selects_port_that_answers_pong(monkeypatch) -> None:
    _FakeSerial.instances = []
    # A generic CH340 decoy enumerates before the real BusyLight.
    monkeypatch.setattr(
        transport_mod, "find_busylight_ports", lambda: ["COM_DECOY", "COM_REAL"]
    )
    monkeypatch.setattr(transport_mod, "SerialClient", _FakeSerial)

    t = BusyLightTransport(host="", pin="")
    t._refresh_serial(force=True)

    assert t.serial_port == "COM_REAL"


def test_no_pong_means_no_serial(monkeypatch) -> None:
    monkeypatch.setattr(
        transport_mod, "find_busylight_ports", lambda: ["COM_DECOY"]
    )

    class _NeverPong(_FakeSerial):
        def ping(self) -> bool:
            return False

    monkeypatch.setattr(transport_mod, "SerialClient", _NeverPong)
    t = BusyLightTransport(host="", pin="")
    t._refresh_serial(force=True)
    assert t.serial_port is None


def test_rescan_interval_is_short_while_disconnected() -> None:
    t = BusyLightTransport(host="", pin="")
    t._serial = None
    assert t._rescan_interval() == transport_mod.SERIAL_RESCAN_DISCONNECTED_S
    t._serial = object()  # pretend connected
    assert t._rescan_interval() == transport_mod.SERIAL_RESCAN_CONNECTED_S
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transport.py -q`
Expected: FAIL — `_rescan_interval` missing and `_refresh_serial` still picks `ports[0]` (decoy), so `serial_port == "COM_DECOY"`.

- [ ] **Step 3: Implement ping-selection + adaptive interval**

In `transport.py`, replace the single constant (`transport.py:40`):

```python
SERIAL_RESCAN_CONNECTED_S = 30.0
SERIAL_RESCAN_DISCONNECTED_S = 3.0
```

Add a helper method and rewrite `_refresh_serial` (`transport.py:132-150`):

```python
    def _rescan_interval(self) -> float:
        # Reacquire fast when we have no channel; stay cheap once connected.
        return (
            SERIAL_RESCAN_CONNECTED_S
            if self._serial is not None
            else SERIAL_RESCAN_DISCONNECTED_S
        )

    def _refresh_serial(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_serial_scan) < self._rescan_interval():
            return
        self._last_serial_scan = now
        ports = find_busylight_ports()
        if not ports:
            if self._serial is not None:
                log.info("USB device disconnected; switching to HTTP")
            self._serial = None
            self._serial_port = None
            return
        # Don't trust position: a generic CH340/CP210x at a dock shares
        # our VID list. Probe each candidate and keep the first that
        # actually answers `pong`.
        for port in ports:
            candidate = SerialClient(port=port)
            try:
                if candidate.ping():
                    if self._serial_port != port:
                        log.info("serial candidate confirmed by pong: %s", port)
                    self._serial = candidate
                    self._serial_port = port
                    return
            except Exception as e:  # noqa: BLE001
                log.debug("candidate %s failed ping: %s", port, e)
        # No candidate answered. Drop any stale handle.
        self._serial = None
        self._serial_port = None
```

Update the two `_maybe_rescan_serial` sites already call `_refresh_serial(force=False)` — no change needed; they now use the adaptive interval automatically.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_transport.py -q`
Expected: PASS — 3/3.

- [ ] **Step 5: Regression check + on-device sanity**

Run: `pytest tests/ -q`
Expected: PASS (whole suite).
On-device (optional in dev): with the BusyLight plus a second CH340/CP210x adapter plugged in, run `python -m busylight_presence --no-tray --once -v` and confirm the log shows "serial candidate confirmed by pong: COMx" pointing at the BusyLight, not the decoy.

- [ ] **Step 6: Commit**

```bash
git add presence_helper/src/busylight_presence/transport.py presence_helper/tests/test_transport.py
git commit -m "feat(desktop): pick COM port by pong, fast reacquire while disconnected (D4,D5)"
```

---

## Task B4: Crash-proof config load

A non-numeric `poll_seconds` in the INI must not kill the app. Guard the `float()` and give `main()` a bound fallback config.

**Files:**
- Modify: `presence_helper/src/busylight_presence/config.py`
- Modify: `presence_helper/src/busylight_presence/main.py`
- Test: `presence_helper/tests/test_config.py` (extend)

**Interfaces:**
- Produces: `config._safe_float(value: str, default: float) -> float`; `main._fallback_config(explicit_path) -> PresenceConfig`.

- [ ] **Step 1: Write the failing tests**

Append to `presence_helper/tests/test_config.py`:

```python
def test_bad_poll_seconds_falls_back_to_default(tmp_path: Path) -> None:
    cfg_path = tmp_path / "presence.ini"
    cfg_path.write_text(
        "[busylight]\nhost = x.local\npin = 1234\npoll_seconds = notanumber\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)          # must NOT raise
    assert cfg.poll_seconds == 2.0
```

Create `presence_helper/tests/test_main_fallback.py`:

```python
from __future__ import annotations

from pathlib import Path

from busylight_presence.config import PresenceConfig
from busylight_presence.main import _fallback_config


def test_fallback_config_is_usable(tmp_path: Path) -> None:
    cfg = _fallback_config(tmp_path / "presence.ini")
    assert isinstance(cfg, PresenceConfig)
    # Safe defaults so the tray can launch into Settings.
    assert cfg.host == ""
    assert cfg.pin == ""
    assert cfg.poll_seconds == 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py::test_bad_poll_seconds_falls_back_to_default tests/test_main_fallback.py -q`
Expected: FAIL — `load_config` raises `ValueError`; `_fallback_config` missing.

- [ ] **Step 3: Guard the float in config.py**

In `config.py`, add the helper above `load_config` (`config.py:83`):

```python
def _safe_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
```

Replace `poll_seconds = float(poll) if poll else 2.0` (`config.py:103`) with:

```python
    poll_seconds = _safe_float(poll, 2.0) if poll else 2.0
```

- [ ] **Step 4: Add the bound fallback in main.py**

In `main.py`, add the helper near `main()` (above line 327):

```python
def _fallback_config(explicit_path) -> PresenceConfig:
    """A safe default config so the tray can still launch into Settings
    when the on-disk config is missing or malformed."""
    from .config import _default_config_path
    return PresenceConfig(
        host="", pin="", config_path=explicit_path or _default_config_path()
    )
```

In `main()`, pre-bind `cfg` before the `try` and use the fallback in the except path. Replace the block at `main.py:342-360` with:

```python
    cfg = _fallback_config(args.config)
    try:
        cfg = load_config(args.config)
        cfg.ensure_valid()
    except (FileNotFoundError, ValueError) as e:
        log.error("config: %s", e)
        log.error(
            "Open the tray icon → Settings, or create the config file "
            "manually. Example:\n  [busylight]\n  host = busylight-XXXX.local"
            "\n  pin  = 1234"
        )
        if not args.no_tray:
            loop = PresenceLoop(cfg, BusyLightTransport(host=cfg.host or "x", pin=cfg.pin or "0000"))
            return _run_tray(loop)
        return 2
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py tests/test_main_fallback.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add presence_helper/src/busylight_presence/config.py presence_helper/src/busylight_presence/main.py presence_helper/tests/test_config.py presence_helper/tests/test_main_fallback.py
git commit -m "fix(desktop): survive malformed config (float guard + bound fallback) (D7)"
```

---

## Task B5: Never leave the app dead after a failed update

On the self-replace give-up path, relaunch the still-present old exe so the tray is always running afterward.

**Files:**
- Modify: `presence_helper/src/busylight_presence/updater.py`
- Test: `presence_helper/tests/test_updater_bat.py`

**Interfaces:**
- Consumes: `updater._write_self_replace_bat(*, new_exe: Path, target: Path) -> Path`.

- [ ] **Step 1: Write the failing test**

```python
# presence_helper/tests/test_updater_bat.py
from __future__ import annotations

from pathlib import Path

from busylight_presence.updater import _write_self_replace_bat


def test_give_up_relaunches_old_exe(tmp_path, monkeypatch) -> None:
    # Redirect the bat/log into tmp so we don't touch %TEMP%.
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    new_exe = tmp_path / "BusyLightPresence-0.4.0.exe"
    target = tmp_path / "BusyLightPresence.exe"
    bat_path = _write_self_replace_bat(new_exe=new_exe, target=target)
    text = bat_path.read_text(encoding="ascii")

    relaunch = f'start "" "{target}"'
    # One relaunch on success, one on the give-up path = 2 total.
    assert text.count(relaunch) == 2
    # The give-up relaunch must sit inside the "gave up" branch.
    give_up_idx = text.index("gave up after")
    assert text.index(relaunch, give_up_idx) > give_up_idx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_updater_bat.py -q`
Expected: FAIL — the give-up branch does not relaunch, so `count(relaunch) == 1`.

- [ ] **Step 3: Add the relaunch to the give-up branch**

In `updater.py::_write_self_replace_bat`, the give-up branch currently is (`updater.py:327-330`):

```python
        "  if !attempts! geq 120 (\r\n"
        '    echo [%date% %time%] gave up after 120 retries >> "%LOG%"\r\n'
        "    goto :done\r\n"
        "  )\r\n"
```

Replace it with a version that relaunches the old exe (still in place after a failed move) before giving up:

```python
        "  if !attempts! geq 120 (\r\n"
        '    echo [%date% %time%] gave up after 120 retries >> "%LOG%"\r\n'
        '    echo [%date% %time%] relaunching existing exe so the app is not left dead >> "%LOG%"\r\n'
        f'    start "" "{target}"\r\n'
        "    goto :done\r\n"
        "  )\r\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_updater_bat.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite regression**

Run: `pytest tests/ -q`
Expected: PASS (whole Phase B suite).

- [ ] **Step 6: Commit**

```bash
git add presence_helper/src/busylight_presence/updater.py presence_helper/tests/test_updater_bat.py
git commit -m "fix(desktop): relaunch old exe on failed self-update so app is never left dead (D3)"
```

---

# Spec Coverage Check

- **F1** (stop abandoning networks / bigger scan budget) → Task A3.
- **F2** (no reboot while USB host attached) → Task A4.
- **F3** (LED under USB control without Wi-Fi) → Task A4.
- **F4** (USB-host-present primitive) → Task A1, wired in A3.
- **F5** (last-resort AP policy) → Task A2, wired in A3.
- **F6** (mDNS service on reconnect) → Task A5.
- **D1** (drop `--uac-admin`, per-user) → Task B1.
- **D2** (start-at-login default-on + tray toggle) → Task B1.
- **D3** (never dead after failed update) → Task B5.
- **D4** (COM port by ping) → Task B3.
- **D5** (fast reacquire) → Task B3.
- **D6** (single-instance guard) → Task B2.
- **D7** (crash-proof config) → Task B4.

Verification strategy items map onto the on-device steps in A3/A4/A5 and the pytest suites in B1–B5. No spec requirement is left without a task.

# Notes for the implementer

- **Firmware tests run on-device** under `esp32c6dev` (matching the existing `test_led_engine` pattern) and temporarily replace the running firmware; reflash the real firmware with `pio run -e esp32c6dev -t upload` + `-t uploadfs` after A1/A2, and again at the end of Phase A.
- **Test-harness sanity first:** before A1, run the existing `pio test -e esp32c6dev -f test_led_engine` once. `platformio.ini` has `test_build_src = yes`, so `main.cpp` is compiled into every test build; its `setup()/loop()` are guarded by `#ifndef UNIT_TEST`. If the test link fails with duplicate `setup`/`loop`, PlatformIO on this toolchain defines the macro as `PIO_UNIT_TESTING`, not `UNIT_TEST` — fix it once by either adding `build_flags = ... -D UNIT_TEST` for the test build or changing the guard in `main.cpp:682` to `#if !defined(UNIT_TEST) && !defined(PIO_UNIT_TESTING)`. Do this before writing new tests so A1/A2 have a working harness. (The audit flagged the firmware suite as never actually run in CI, so treat a first green run as part of the deliverable.)
- **A1/A2 are header-only** pure classes (no `.cpp`, no Arduino includes) so they compile identically on-device and — later, in M3 — under a native test env without change.
- **A3 design refinement (recorded):** the "saved network reachable" signal fed to `WifiApPolicy` is *successful association*, not a passive scan hit — simpler, needs no async scan, and is a stronger daily-use signal (a visible-but-unjoinable SSID would otherwise keep you out of the AP forever). This satisfies the spec's F5 intent; the grace period and host window remain the tunables.
- **Windows-only desktop tests** (`test_startup.py`, `test_single_instance.py`) skip on non-Windows CI; run them on the owner's Windows machine for real coverage.
- Keep `pio test` and `pytest` green; frequent commits per task.
