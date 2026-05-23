#pragma once

#include <Arduino.h>

#include <vector>

#include "led_engine.h"

struct WifiNetwork {
  String ssid;
  String password;
};

struct MqttConfig {
  bool enabled = false;
  String host;
  uint16_t port = 1883;
  String username;
  String password;
};

struct DeviceConfig {
  // Saved Wi-Fi networks in priority order (best to fall back to last).
  std::vector<WifiNetwork> networks;
  String pinHash;
  BusyStatus lastState;
  // True iff at least one Wi-Fi network is configured.
  bool configured;
  // Set by code paths that modify `networks` and need `main.cpp` to
  // rebuild the WiFiMulti list and re-arm reconnects on the next tick.
  bool wifiListDirty;
  MqttConfig mqtt;
  // Set by api_server when the MQTT settings change so main.cpp can
  // re-initialise the MQTT client.
  bool mqttConfigDirty;
};

class ConfigStore {
 public:
  static constexpr size_t kMaxWifiNetworks = 6;

  bool begin();
  DeviceConfig load();
  // Returns false if the store is full or `ssid` already exists.
  bool addNetwork(const String& ssid, const String& password);
  // Remove by exact ssid. Returns false if not found.
  bool removeNetwork(const String& ssid);
  // Replace the full list (used by the wizard / AP portal which currently
  // hand us a single network; the caller decides to clear-then-add).
  bool saveNetworks(const std::vector<WifiNetwork>& networks);
  std::vector<WifiNetwork> loadNetworks();
  bool savePinHash(const String& pinHash);
  bool saveState(BusyStatus state);
  MqttConfig loadMqtt();
  bool saveMqtt(const MqttConfig& cfg);
  // Wipe every key in our NVS namespace. The device must reboot afterwards.
  bool clear();

 private:
  static String keyForSsid(size_t index);
  static String keyForPwd(size_t index);
};
