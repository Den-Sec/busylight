#pragma once

#include <Arduino.h>

#include "led_engine.h"

struct DeviceConfig {
  String ssid;
  String password;
  String pinHash;
  BusyStatus lastState;
  bool configured;
};

class ConfigStore {
 public:
  bool begin();
  DeviceConfig load();
  bool saveNetwork(const String& ssid, const String& password);
  bool savePinHash(const String& pinHash);
  bool saveState(BusyStatus state);
  // Wipe every key in our NVS namespace. The device must reboot afterwards.
  bool clear();
};
