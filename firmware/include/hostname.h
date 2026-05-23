#pragma once

#include <Arduino.h>

#include <cstdint>

namespace busylight {

// Returns the canonical device hostname for a given chip MAC.
// Example: `mac = 0xf0f5bd02760cULL` -> `"busylight-760c"`.
//
// This util is split out of `main.cpp` so it can be exercised by the
// `native` PlatformIO env without pulling in WiFi headers.
String makeHostname(uint64_t chipMac);

}  // namespace busylight
