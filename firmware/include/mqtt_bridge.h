#pragma once

#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include <functional>

#include "config_store.h"
#include "led_engine.h"

// Bridge between BusyLight and an external MQTT broker.
//
// Topics (where `<host>` is `busylight-XXXX`):
//   * Publish (retain=true) `busylight/<host>/state` — current state
//     as a small JSON document, fired on connect and whenever the
//     LED flips.
//   * Subscribe              `busylight/<host>/cmd/set` — accepts
//     either a plain state name ("BUSY") or a JSON object
//     {"state":"BUSY"} and applies it through the same path the
//     web API uses.
//   * Publish (retain=true) `homeassistant/select/<host>/status/config`
//     — Home Assistant MQTT discovery payload so the device appears
//     as a select entity in HA without manual YAML.
class MqttBridge {
 public:
  // Wire up dependencies. The bridge does NOT take ownership of `led`;
  // both callbacks must outlive this object.
  void begin(const String& hostname,
             LedEngine* led,
             std::function<void(BusyStatus)> applyState);

  // Re-read the current MqttConfig and (dis)connect accordingly. Safe
  // to call repeatedly.
  void configure(const MqttConfig& cfg);

  // Pump the MQTT client. Cheap when disabled. Call every loop().
  void loop();

  // Fire-and-forget state publish. Cheap when disabled. The bridge
  // also publishes state on its own when it reconnects.
  void publishState(BusyStatus state);

  bool isConnected() const;
  bool isEnabled() const { return cfg_.enabled; }

 private:
  String hostname_;
  LedEngine* led_ = nullptr;
  std::function<void(BusyStatus)> applyState_;

  MqttConfig cfg_;
  WiFiClient wifi_;
  PubSubClient client_{wifi_};

  unsigned long nextAttemptMs_ = 0;
  uint32_t backoffMs_ = 2000;

  String topicState_;
  String topicCmdSet_;
  String topicDiscovery_;

  void recomputeTopics_();
  void onMessage_(char* topic, uint8_t* payload, unsigned int length);
  bool connect_();
  void publishDiscovery_();
  String stateAsJson_(BusyStatus state) const;
};
