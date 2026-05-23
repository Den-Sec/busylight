#pragma once

#include <Arduino.h>

#include <ctime>
#include <vector>

#include "led_engine.h"

struct ScheduleEntry {
  bool enabled = true;
  // bit0 = Sunday, bit1 = Monday, ..., bit6 = Saturday.
  // 0b01111110 (0x7e) is Mon-Fri, 0b01000001 (0x41) is weekends.
  uint8_t daysMask = 0;
  // Minutes from midnight local time. End is exclusive. Ranges that
  // wrap midnight (start > end) are supported, e.g. 22:00 -> 06:00.
  uint16_t startMinute = 0;
  uint16_t endMinute = 0;
  BusyStatus targetState = STATUS_AVAILABLE;
};

// Pure function over a list of schedule entries: at `localTime`, which
// state should the device be in?
class Scheduler {
 public:
  static constexpr size_t kMaxEntries = 4;

  void setEntries(const std::vector<ScheduleEntry>& entries) {
    entries_ = entries;
  }
  const std::vector<ScheduleEntry>& entries() const { return entries_; }

  // Looks up the first entry whose mask + time window contains
  // `localTime`. Writes the target state into `outState` and returns
  // true. Returns false if no entry applies right now (the caller
  // should leave the LED at the user's manual choice).
  bool currentDesiredState(time_t localTime, BusyStatus& outState) const;

 private:
  std::vector<ScheduleEntry> entries_;
};
