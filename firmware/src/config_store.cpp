#include "config_store.h"

#include <Preferences.h>

namespace {
constexpr const char* kNs = "busylight";
constexpr const char* kCountKey = "wifi_n";
// Legacy v0.1.0/v0.2.0 keys for the single Wi-Fi network. Migrated to the
// indexed format the first time a v0.3.0+ firmware boots over old NVS.
constexpr const char* kLegacySsid = "ssid";
constexpr const char* kLegacyPwd = "pwd";
constexpr const char* kLegacyConfigured = "configured";
}

bool ConfigStore::begin() {
  Preferences prefs;
  bool ok = prefs.begin(kNs, false);
  prefs.end();
  return ok;
}

String ConfigStore::keyForSsid(size_t index) {
  char buf[16];
  snprintf(buf, sizeof(buf), "ssid_%u", static_cast<unsigned>(index));
  return String(buf);
}

String ConfigStore::keyForPwd(size_t index) {
  char buf[16];
  snprintf(buf, sizeof(buf), "pwd_%u", static_cast<unsigned>(index));
  return String(buf);
}

std::vector<WifiNetwork> ConfigStore::loadNetworks() {
  std::vector<WifiNetwork> result;
  Preferences prefs;
  if (!prefs.begin(kNs, true)) {
    return result;
  }

  unsigned int count = prefs.getUInt(kCountKey, 0);
  // Migration path: if the new "wifi_n" key is missing but the legacy
  // single-network keys are populated, surface them as the first entry.
  if (count == 0 && prefs.isKey(kLegacySsid)) {
    String legacySsid = prefs.getString(kLegacySsid, "");
    if (legacySsid.length() > 0) {
      WifiNetwork net;
      net.ssid = legacySsid;
      net.password = prefs.getString(kLegacyPwd, "");
      result.push_back(net);
    }
  }

  if (count > kMaxWifiNetworks) count = kMaxWifiNetworks;
  for (unsigned int i = 0; i < count; i++) {
    WifiNetwork net;
    net.ssid = prefs.getString(keyForSsid(i).c_str(), "");
    net.password = prefs.getString(keyForPwd(i).c_str(), "");
    if (net.ssid.length() > 0) {
      result.push_back(net);
    }
  }

  prefs.end();
  return result;
}

DeviceConfig ConfigStore::load() {
  Preferences prefs;
  DeviceConfig cfg{};

  if (!prefs.begin(kNs, true)) {
    cfg.configured = false;
    cfg.lastState = STATUS_AVAILABLE;
    return cfg;
  }

  cfg.pinHash = prefs.getString("pin", "");
  unsigned int rawState = prefs.getUInt("state", STATUS_AVAILABLE);
  if (rawState > STATUS_AWAY) {
    rawState = STATUS_AVAILABLE;
  }
  cfg.lastState = static_cast<BusyStatus>(rawState);
  prefs.end();

  cfg.networks = loadNetworks();
  cfg.configured = !cfg.networks.empty();
  cfg.mqtt = loadMqtt();
  return cfg;
}

MqttConfig ConfigStore::loadMqtt() {
  MqttConfig out;
  Preferences prefs;
  if (!prefs.begin(kNs, true)) return out;
  out.enabled = prefs.getBool("mqtt_on", false);
  out.host = prefs.getString("mqtt_host", "");
  out.port = static_cast<uint16_t>(prefs.getUInt("mqtt_port", 1883));
  out.username = prefs.getString("mqtt_user", "");
  out.password = prefs.getString("mqtt_pass", "");
  prefs.end();
  return out;
}

bool ConfigStore::saveMqtt(const MqttConfig& cfg) {
  Preferences prefs;
  if (!prefs.begin(kNs, false)) return false;
  prefs.putBool("mqtt_on", cfg.enabled);
  prefs.putString("mqtt_host", cfg.host);
  prefs.putUInt("mqtt_port", cfg.port);
  prefs.putString("mqtt_user", cfg.username);
  prefs.putString("mqtt_pass", cfg.password);
  prefs.end();
  return true;
}

bool ConfigStore::saveNetworks(const std::vector<WifiNetwork>& networks) {
  Preferences prefs;
  if (!prefs.begin(kNs, false)) {
    return false;
  }

  // Clear the previous slots so deletes actually shrink the list.
  unsigned int oldCount = prefs.getUInt(kCountKey, 0);
  for (unsigned int i = 0; i < kMaxWifiNetworks; i++) {
    String sk = keyForSsid(i);
    String pk = keyForPwd(i);
    if (prefs.isKey(sk.c_str())) prefs.remove(sk.c_str());
    if (prefs.isKey(pk.c_str())) prefs.remove(pk.c_str());
  }
  (void)oldCount;

  size_t n = networks.size();
  if (n > kMaxWifiNetworks) n = kMaxWifiNetworks;
  prefs.putUInt(kCountKey, static_cast<unsigned int>(n));
  for (size_t i = 0; i < n; i++) {
    prefs.putString(keyForSsid(i).c_str(), networks[i].ssid);
    prefs.putString(keyForPwd(i).c_str(), networks[i].password);
  }

  // Once we've written the new shape, also clear the legacy single-key
  // slot so the next boot doesn't synthesise a duplicate.
  if (prefs.isKey(kLegacySsid)) prefs.remove(kLegacySsid);
  if (prefs.isKey(kLegacyPwd)) prefs.remove(kLegacyPwd);
  if (prefs.isKey(kLegacyConfigured)) prefs.remove(kLegacyConfigured);

  prefs.end();
  return true;
}

bool ConfigStore::addNetwork(const String& ssid, const String& password) {
  if (ssid.length() == 0) return false;
  std::vector<WifiNetwork> nets = loadNetworks();
  for (const auto& n : nets) {
    if (n.ssid == ssid) {
      // Already present — update the password in place if it differs.
      // Keeps "scan & save" easier for users who replace a Wi-Fi router.
      if (n.password == password) return true;
      for (auto& m : nets) {
        if (m.ssid == ssid) {
          m.password = password;
          break;
        }
      }
      return saveNetworks(nets);
    }
  }
  if (nets.size() >= kMaxWifiNetworks) {
    return false;
  }
  WifiNetwork added;
  added.ssid = ssid;
  added.password = password;
  nets.push_back(added);
  return saveNetworks(nets);
}

bool ConfigStore::removeNetwork(const String& ssid) {
  std::vector<WifiNetwork> nets = loadNetworks();
  size_t before = nets.size();
  nets.erase(std::remove_if(nets.begin(), nets.end(),
                            [&](const WifiNetwork& n) { return n.ssid == ssid; }),
             nets.end());
  if (nets.size() == before) return false;
  return saveNetworks(nets);
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
