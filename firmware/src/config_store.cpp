#include "config_store.h"

#include <Preferences.h>

namespace {
constexpr const char* kNs = "busylight";
}

bool ConfigStore::begin() {
  Preferences prefs;
  bool ok = prefs.begin(kNs, false);
  prefs.end();
  return ok;
}

DeviceConfig ConfigStore::load() {
  Preferences prefs;
  DeviceConfig cfg{};

  if (!prefs.begin(kNs, true)) {
    cfg.configured = false;
    cfg.lastState = STATUS_AVAILABLE;
    return cfg;
  }

  cfg.ssid = prefs.getString("ssid", "");
  cfg.password = prefs.getString("pwd", "");
  cfg.pinHash = prefs.getString("pin", "");
  unsigned int rawState = prefs.getUInt("state", STATUS_AVAILABLE);
  // WIFI_ERROR is a transient transport state, never a real "last user state".
  // Coerce it (and any out-of-range value) back to AVAILABLE on boot.
  if (rawState > STATUS_AWAY) {
    rawState = STATUS_AVAILABLE;
  }
  cfg.lastState = static_cast<BusyStatus>(rawState);
  cfg.configured = prefs.getBool("configured", false);

  prefs.end();
  return cfg;
}

bool ConfigStore::saveNetwork(const String& ssid, const String& password) {
  Preferences prefs;
  if (!prefs.begin(kNs, false)) {
    return false;
  }

  prefs.putString("ssid", ssid);
  prefs.putString("pwd", password);
  prefs.putBool("configured", true);
  prefs.end();
  return true;
}

bool ConfigStore::savePinHash(const String& pinHash) {
  Preferences prefs;
  if (!prefs.begin(kNs, false)) {
    return false;
  }

  prefs.putString("pin", pinHash);
  prefs.end();
  return true;
}

bool ConfigStore::saveState(BusyStatus state) {
  Preferences prefs;
  if (!prefs.begin(kNs, false)) {
    return false;
  }

  prefs.putUInt("state", static_cast<unsigned int>(state));
  prefs.end();
  return true;
}

bool ConfigStore::clear() {
  Preferences prefs;
  if (!prefs.begin(kNs, false)) {
    return false;
  }
  prefs.clear();
  prefs.end();
  return true;
}
