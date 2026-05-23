#include "hostname.h"

namespace busylight {

String makeHostname(uint64_t chipMac) {
  char suffix[5];
  snprintf(suffix, sizeof(suffix), "%04x",
           static_cast<uint16_t>(chipMac & 0xFFFFULL));
  return String("busylight-") + suffix;
}

}  // namespace busylight
