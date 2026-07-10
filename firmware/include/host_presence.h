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
