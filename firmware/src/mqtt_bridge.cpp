#include "mqtt_bridge.h"

#include <ArduinoJson.h>

namespace {

const char* stateToStr(BusyStatus s) {
  switch (s) {
    case STATUS_AVAILABLE: return "AVAILABLE";
    case STATUS_BUSY:      return "BUSY";
    case STATUS_IN_CALL:   return "IN_CALL";
    case STATUS_AWAY:      return "AWAY";
    case STATUS_OFF:       return "OFF";
    case STATUS_WIFI_ERROR:return "WIFI_ERROR";
    default:               return "AVAILABLE";
  }
}

bool parseState(const String& s, BusyStatus& out) {
  if (s == "AVAILABLE") { out = STATUS_AVAILABLE; return true; }
  if (s == "BUSY")      { out = STATUS_BUSY;      return true; }
  if (s == "IN_CALL")   { out = STATUS_IN_CALL;   return true; }
  if (s == "AWAY")      { out = STATUS_AWAY;      return true; }
  if (s == "OFF")       { out = STATUS_OFF;       return true; }
  return false;
}

}  // namespace

void MqttBridge::begin(const String& hostname,
                       LedEngine* led,
                       std::function<void(BusyStatus)> applyState) {
  hostname_ = hostname;
  led_ = led;
  applyState_ = std::move(applyState);
  client_.setCallback(
      [this](char* topic, uint8_t* payload, unsigned int length) {
        onMessage_(topic, payload, length);
      });
}

void MqttBridge::configure(const MqttConfig& cfg) {
  cfg_ = cfg;
  recomputeTopics_();
  if (client_.connected()) {
    client_.disconnect();
  }
  client_.setServer(cfg_.host.c_str(), cfg_.port);
  backoffMs_ = 2000;
  nextAttemptMs_ = 0;
}

void MqttBridge::recomputeTopics_() {
  topicState_ = "busylight/" + hostname_ + "/state";
  topicCmdSet_ = "busylight/" + hostname_ + "/cmd/set";
  topicDiscovery_ =
      "homeassistant/select/" + hostname_ + "/status/config";
}

bool MqttBridge::isConnected() const {
  return cfg_.enabled && const_cast<PubSubClient&>(client_).connected();
}

void MqttBridge::loop() {
  if (!cfg_.enabled || cfg_.host.length() == 0) return;
  if (WiFi.status() != WL_CONNECTED) return;

  if (!client_.connected()) {
    unsigned long now = millis();
    if (now < nextAttemptMs_) return;
    if (connect_()) {
      backoffMs_ = 2000;
    } else {
      backoffMs_ = (backoffMs_ < 60000) ? backoffMs_ * 2 : 60000;
      nextAttemptMs_ = now + backoffMs_;
    }
  }

  client_.loop();
}

bool MqttBridge::connect_() {
  String clientId = hostname_;
  bool ok;
  if (cfg_.username.length() > 0) {
    ok = client_.connect(clientId.c_str(),
                          cfg_.username.c_str(),
                          cfg_.password.c_str(),
                          topicState_.c_str(),    // LWT topic
                          0,                       // LWT qos
                          true,                    // LWT retain
                          "{\"state\":\"OFFLINE\"}");
  } else {
    ok = client_.connect(clientId.c_str(),
                          nullptr, nullptr,
                          topicState_.c_str(), 0, true,
                          "{\"state\":\"OFFLINE\"}");
  }
  if (!ok) return false;

  client_.subscribe(topicCmdSet_.c_str());
  publishDiscovery_();
  if (led_) publishState(led_->currentState());
  Serial.printf(
      "{\"ok\":true,\"event\":\"mqtt_connected\",\"host\":\"%s\"}\n",
      cfg_.host.c_str());
  return true;
}

void MqttBridge::publishDiscovery_() {
  JsonDocument doc;
  doc["name"] = "Status";
  doc["unique_id"] = hostname_ + "_status";
  doc["object_id"] = hostname_;
  doc["state_topic"] = topicState_;
  doc["command_topic"] = topicCmdSet_;
  doc["value_template"] = "{{ value_json.state }}";
  JsonArray options = doc["options"].to<JsonArray>();
  options.add("AVAILABLE");
  options.add("BUSY");
  options.add("IN_CALL");
  options.add("AWAY");
  options.add("OFF");
  JsonObject device = doc["device"].to<JsonObject>();
  JsonArray ids = device["identifiers"].to<JsonArray>();
  ids.add(hostname_);
  device["name"] = String("BusyLight ") + hostname_;
  device["manufacturer"] = "D-Enterprise";
  device["model"] = "BusyLight (ESP32-C6)";
#ifdef BUSYLIGHT_VERSION
  device["sw_version"] = BUSYLIGHT_VERSION;
#endif
  device["configuration_url"] =
      String("http://") + hostname_ + ".local";

  String payload;
  serializeJson(doc, payload);
  client_.publish(topicDiscovery_.c_str(),
                  payload.c_str(), /*retained=*/true);
}

void MqttBridge::publishState(BusyStatus state) {
  if (!isConnected()) return;
  String payload = stateAsJson_(state);
  client_.publish(topicState_.c_str(),
                  payload.c_str(), /*retained=*/true);
}

String MqttBridge::stateAsJson_(BusyStatus state) const {
  JsonDocument doc;
  doc["state"] = stateToStr(state);
  doc["host"] = hostname_;
#ifdef BUSYLIGHT_VERSION
  doc["fw"] = BUSYLIGHT_VERSION;
#endif
  String out;
  serializeJson(doc, out);
  return out;
}

void MqttBridge::onMessage_(char* topic, uint8_t* payload, unsigned int length) {
  if (!applyState_) return;
  String topicStr(topic);
  if (topicStr != topicCmdSet_) return;

  // Accept either a bare token or a JSON object.
  String body;
  body.reserve(length);
  for (unsigned int i = 0; i < length; i++) {
    body += static_cast<char>(payload[i]);
  }
  body.trim();

  String stateStr;
  if (body.length() > 0 && body[0] == '{') {
    JsonDocument doc;
    if (deserializeJson(doc, body)) return;
    if (!doc["state"].is<const char*>()) return;
    stateStr = String(static_cast<const char*>(doc["state"]));
  } else {
    // strip surrounding quotes if any
    if (body.length() >= 2 && body[0] == '"' &&
        body[body.length() - 1] == '"') {
      stateStr = body.substring(1, body.length() - 1);
    } else {
      stateStr = body;
    }
  }
  stateStr.toUpperCase();

  BusyStatus s;
  if (!parseState(stateStr, s)) return;
  applyState_(s);
}
