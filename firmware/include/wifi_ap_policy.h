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
