#include "schedule.h"

#include <ctime>

bool Scheduler::currentDesiredState(time_t localTime,
                                    BusyStatus& outState) const {
  if (entries_.empty()) return false;

  struct tm tm;
  localtime_r(&localTime, &tm);

  uint8_t dayBit = static_cast<uint8_t>(1u << tm.tm_wday);
  uint16_t minuteOfDay =
      static_cast<uint16_t>(tm.tm_hour * 60 + tm.tm_min);

  for (const auto& e : entries_) {
    if (!e.enabled) continue;
    if ((e.daysMask & dayBit) == 0) continue;
    bool inside = false;
    if (e.startMinute <= e.endMinute) {
      // Normal range, e.g. 09:00-18:00.
      inside = (minuteOfDay >= e.startMinute &&
                minuteOfDay < e.endMinute);
    } else {
      // Wraps midnight, e.g. 22:00-06:00.
      inside = (minuteOfDay >= e.startMinute ||
                minuteOfDay < e.endMinute);
    }
    if (inside) {
      outState = e.targetState;
      return true;
    }
  }
  return false;
}
