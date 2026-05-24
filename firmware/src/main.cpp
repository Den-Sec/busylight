#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <WiFiMulti.h>

#include "ap_portal.h"
#include "api_server.h"
#include "auth.h"
#include "config_store.h"
#include "hostname.h"
#include "led_engine.h"
#include "mqtt_bridge.h"
#include "schedule.h"

#include <ctime>
#include <time.h>

namespace {

constexpr int kRedPin = 6;
constexpr int kGreenPin = 23;

constexpr unsigned int kMaxStaFailuresBeforeAp = 3;
constexpr unsigned long kStateDebounceMs = 60UL * 1000UL;
constexpr unsigned long kApPortalTimeoutMs = 10UL * 60UL * 1000UL;

// Exponential backoff between failed WiFi attempts. Capped at 60 s.
constexpr uint32_t kWifiBackoffMs[] = {1000, 2000, 5000, 10000, 30000, 60000};

LedEngine gLed(kRedPin, kGreenPin);
ConfigStore gStore;
DeviceConfig gConfig;
AuthManager gAuth;
ApiServer gApi(&gLed, &gStore, &gAuth, &gConfig);
ApPortal gApPortal;
WiFiMulti gWifiMulti;
MqttBridge gMqtt;
Scheduler gScheduler;
bool gTimeSynced = false;
unsigned long gLastScheduleTickMs = 0;
BusyStatus gLastScheduleApplied = STATUS_AVAILABLE;
bool gScheduleHasApplied = false;
// Europe/Rome with automatic DST. Switch via build flag if you ship
// the device outside Italy.
constexpr const char* kTimezoneSpec =
#ifdef BUSYLIGHT_TZ
    BUSYLIGHT_TZ;
#else
    "CET-1CEST,M3.5.0,M10.5.0/3";
#endif

bool gServerStarted = false;
bool gLittleFsOk = false;
bool gWifiWasConnected = false;

String gDeviceHostname = "busylight";

struct WifiSm {
  uint8_t attemptIndex;
  uint32_t failuresTotal;
  unsigned long nextRetryMs;
  bool kicked;
};
WifiSm gWifi = {0, 0, 0, false};

void emitJson(const char* json) { Serial.println(json); }

void emitJsonFmt(const char* fmt, const char* arg) {
  Serial.printf(fmt, arg);
  Serial.println();
}

void applyDefaultPinIfMissing() {
  if (gConfig.pinHash.length() == 0) {
    gConfig.pinHash = AuthManager::hashPin("1234");
    gStore.savePinHash(gConfig.pinHash);
  }
  gAuth.setPinHash(gConfig.pinHash);
}

void computeHostname() {
  uint64_t mac = ESP.getEfuseMac();
  gDeviceHostname = busylight::makeHostname(mac);
}

// Refresh the WiFiMulti AP list from gConfig.networks. Called once at
// boot and again whenever the web API (or AP captive portal) edits the
// stored list and flags `gConfig.wifiListDirty`.
void rebuildWifiMulti() {
  gWifiMulti.APlistClean();
  for (const auto& net : gConfig.networks) {
    if (net.password.length() == 0) {
      gWifiMulti.addAP(net.ssid.c_str());
    } else {
      gWifiMulti.addAP(net.ssid.c_str(), net.password.c_str());
    }
  }
}

void rebuildScheduler() {
  gScheduler.setEntries(gConfig.schedule);
  // Force re-application of any matching entry next tick.
  gScheduleHasApplied = false;
  gLastScheduleTickMs = 0;
}

void startNtpIfNeeded() {
  if (gTimeSynced) return;
  configTime(0, 0, "pool.ntp.org", "time.cloudflare.com");
  setenv("TZ", kTimezoneSpec, 1);
  tzset();
  // configTime is async. Mark synced when localtime year reaches a sane
  // value (the ESP boots with year 1970 until the SNTP reply lands).
  time_t now = time(nullptr);
  if (now > 1700000000L) {  // > 2023-11-14
    gTimeSynced = true;
    Serial.println("{\"ok\":true,\"event\":\"ntp_synced\"}");
  }
}

void scheduleTick() {
  startNtpIfNeeded();
  if (!gTimeSynced) {
    // Re-check once SNTP eventually responds.
    time_t now = time(nullptr);
    if (now > 1700000000L) {
      gTimeSynced = true;
      Serial.println("{\"ok\":true,\"event\":\"ntp_synced\"}");
    } else {
      return;
    }
  }

  unsigned long ms = millis();
  if (gLastScheduleTickMs != 0 && (ms - gLastScheduleTickMs) < 20000) {
    return;
  }
  gLastScheduleTickMs = ms;

  time_t now = time(nullptr);
  BusyStatus desired;
  if (!gScheduler.currentDesiredState(now, desired)) {
    gScheduleHasApplied = false;
    return;
  }
  if (gScheduleHasApplied && desired == gLastScheduleApplied) return;
  gApi.applyState(desired);
  gLastScheduleApplied = desired;
  gScheduleHasApplied = true;
}

void startServerIfNeeded() {
  if (gServerStarted) return;

  gLittleFsOk = LittleFS.begin(true);
  if (!gLittleFsOk) {
    emitJson("{\"ok\":false,\"event\":\"littlefs_fail\"}");
  }

  if (MDNS.begin(gDeviceHostname.c_str())) {
    MDNS.addService("http", "tcp", 80);
  }

  gApi.begin(gLittleFsOk);
  // Wire MQTT pub on every state change emitted by the API server,
  // and accept inbound MQTT commands as state-change events through
  // the same code path.
  gApi.setOnStateChanged([](BusyStatus s) { gMqtt.publishState(s); });
  gMqtt.begin(gDeviceHostname, &gLed, [](BusyStatus s) { gApi.applyState(s); });
  gMqtt.configure(gConfig.mqtt);

  gLed.setState(gConfig.lastState);
  gServerStarted = true;
  Serial.printf("{\"ok\":true,\"event\":\"server_started\",\"ip\":\"%s\",\"host\":\"%s\"}\n",
                WiFi.localIP().toString().c_str(),
                gDeviceHostname.c_str());
}

void enterApPortal() {
  String apSsid = gDeviceHostname + "-Setup";
  WiFi.disconnect(true, true);
  gApPortal.begin(apSsid);
  gLed.setState(STATUS_WIFI_ERROR);
  Serial.printf("{\"ok\":false,\"event\":\"ap_portal_started\",\"ssid\":\"%s\"}\n",
                apSsid.c_str());
}

void startStationConnection() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(gDeviceHostname.c_str());
  // Kick a fresh association: WiFiMulti picks the strongest AP it
  // remembers and connects. Returns within `timeout_ms` regardless of
  // result, so we keep it short to avoid blocking the LED tick.
  gWifiMulti.run(2000);
  gWifi.kicked = true;
}

void networkingTick() {
  // If the AP portal is up, just service it and check for a fresh config.
  if (gApPortal.isActive()) {
    gApPortal.tick();
    if (gApPortal.hasNewConfig()) {
      String ssid = gApPortal.pendingSsid();
      String password = gApPortal.pendingPassword();
      String pin = gApPortal.pendingPin();
      // Append rather than replace: the user might be adding an extra
      // venue (e.g. a hotel Wi-Fi) without wanting to forget home.
      gStore.addNetwork(ssid, password);
      String newPinHash = AuthManager::hashPin(pin);
      gStore.savePinHash(newPinHash);
      delay(150);
      ESP.restart();
    }
    if (gApPortal.uptimeMs() > kApPortalTimeoutMs) {
      Serial.println(
          "{\"ok\":false,\"event\":\"ap_portal_timeout\"}");
      delay(150);
      ESP.restart();
    }
    return;
  }

  if (!gConfig.configured || gConfig.networks.empty()) {
    gLed.setState(STATUS_WIFI_ERROR);
    return;
  }

  bool isConnected = (WiFi.status() == WL_CONNECTED);

  if (isConnected) {
    if (!gWifiWasConnected) {
      // Fresh connection: reset backoff counter and (re-)init mDNS.
      gWifi.attemptIndex = 0;
      gWifi.failuresTotal = 0;
      gWifi.nextRetryMs = 0;
      MDNS.end();
      MDNS.begin(gDeviceHostname.c_str());
      gWifiWasConnected = true;
    }
    startServerIfNeeded();
    return;
  }

  // Not connected. Either we have not started yet, or we just lost the link.
  if (gWifiWasConnected) {
    Serial.println("{\"ok\":false,\"event\":\"wifi_lost\"}");
    gWifiWasConnected = false;
    gWifi.attemptIndex = 0;
    gWifi.nextRetryMs = 0;
    gWifi.kicked = false;
  }

  gLed.setState(STATUS_WIFI_ERROR);

  unsigned long now = millis();
  if (!gWifi.kicked) {
    startStationConnection();
    gWifi.nextRetryMs =
        now + kWifiBackoffMs[gWifi.attemptIndex %
                             (sizeof(kWifiBackoffMs) / sizeof(uint32_t))];
    Serial.println("{\"ok\":false,\"event\":\"wifi_reconnect\"}");
    return;
  }

  if (now < gWifi.nextRetryMs) return;

  // Backoff elapsed without a successful connection. Count as a failure,
  // bump attempt index, retry.
  gWifi.attemptIndex =
      static_cast<uint8_t>(gWifi.attemptIndex + 1) %
      (sizeof(kWifiBackoffMs) / sizeof(uint32_t));
  gWifi.failuresTotal++;

  if (gWifi.failuresTotal >= kMaxStaFailuresBeforeAp) {
    enterApPortal();
    return;
  }

  startStationConnection();
  gWifi.nextRetryMs =
      now + kWifiBackoffMs[gWifi.attemptIndex %
                           (sizeof(kWifiBackoffMs) / sizeof(uint32_t))];
  Serial.printf("{\"ok\":false,\"event\":\"wifi_retry\",\"attempt\":%u}\n",
                static_cast<unsigned>(gWifi.failuresTotal));
}

void handleSerialFactoryReset() {
  Serial.println("{\"ok\":true,\"event\":\"factory_reset_ok\"}");
  delay(100);
  gStore.clear();
  delay(150);
  ESP.restart();
}

void handleSerialSetConfig(JsonDocument& in) {
  if (!in["ssid"].is<const char*>() || !in["password"].is<const char*>() ||
      !in["pin"].is<const char*>()) {
    emitJson("{\"ok\":false,\"error\":\"missing_fields\"}");
    return;
  }

  String ssid = String(static_cast<const char*>(in["ssid"]));
  String password = String(static_cast<const char*>(in["password"]));
  String pin = String(static_cast<const char*>(in["pin"]));

  if (ssid.length() == 0 || pin.length() < 4 || pin.length() > 8) {
    emitJson("{\"ok\":false,\"error\":\"validation\"}");
    return;
  }
  for (size_t i = 0; i < pin.length(); i++) {
    if (!isDigit(pin[i])) {
      emitJson("{\"ok\":false,\"error\":\"pin_digits_only\"}");
      return;
    }
  }

  // Append-or-update: keep any existing networks the user added from
  // the web UI, just ensure this one is in there too.
  gStore.addNetwork(ssid, password);
  gConfig.networks = gStore.loadNetworks();
  gConfig.configured = !gConfig.networks.empty();

  String pinHash = AuthManager::hashPin(pin);
  gStore.savePinHash(pinHash);
  gConfig.pinHash = pinHash;
  gAuth.setPinHash(pinHash);

  Serial.printf(
      "{\"ok\":true,\"event\":\"config_saved\",\"host\":\"%s\"}\n",
      gDeviceHostname.c_str());
  delay(200);
  ESP.restart();
}

void handleSerialProvisioning() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  JsonDocument in;
  auto err = deserializeJson(in, line);
  if (err || !in["cmd"].is<const char*>()) {
    emitJson("{\"ok\":false,\"error\":\"invalid_json\"}");
    return;
  }

  String cmd = String(static_cast<const char*>(in["cmd"]));
  if (cmd == "ping") {
    emitJson("{\"ok\":true,\"event\":\"pong\"}");
    return;
  }
  if (cmd == "factory_reset") {
    if (!in["confirm"].is<const char*>() ||
        String(static_cast<const char*>(in["confirm"])) != "YES") {
      emitJson("{\"ok\":false,\"error\":\"confirm_required\"}");
      return;
    }
    handleSerialFactoryReset();
    return;
  }
  if (cmd == "set_config") {
    handleSerialSetConfig(in);
    return;
  }
  if (cmd == "set_state") {
    // Runtime command, no auth: USB cable already implies physical
    // access. Accepts an int 0..5 matching BusyStatus.
    if (!in["state"].is<int>()) {
      emitJson("{\"ok\":false,\"error\":\"state_missing\"}");
      return;
    }
    int raw = in["state"].as<int>();
    if (raw < 0 || raw > STATUS_OFF) {
      emitJson("{\"ok\":false,\"error\":\"state_out_of_range\"}");
      return;
    }
    BusyStatus st = static_cast<BusyStatus>(raw);
    gApi.applyState(st);
    char buf[64];
    snprintf(buf, sizeof(buf),
             "{\"ok\":true,\"event\":\"state_set\",\"state\":%d}", raw);
    emitJson(buf);
    return;
  }
  if (cmd == "get_state") {
    char buf[64];
    snprintf(buf, sizeof(buf),
             "{\"ok\":true,\"event\":\"state\",\"state\":%d}",
             static_cast<int>(gConfig.lastState));
    emitJson(buf);
    return;
  }
  if (cmd == "get_info") {
    char buf[192];
    String ip = WiFi.isConnected() ? WiFi.localIP().toString() : String("");
    snprintf(buf, sizeof(buf),
             "{\"ok\":true,\"event\":\"info\",\"host\":\"%s\","
             "\"fw\":\"%s\",\"state\":%d,\"wifi\":%s,\"ip\":\"%s\"}",
             gDeviceHostname.c_str(), BUSYLIGHT_VERSION,
             static_cast<int>(gConfig.lastState),
             WiFi.isConnected() ? "true" : "false", ip.c_str());
    emitJson(buf);
    return;
  }

  emitJson("{\"ok\":false,\"error\":\"unknown_cmd\"}");
}

void persistStateIfDebounced() {
  if (!gApi.isStateDirty()) return;
  unsigned long now = millis();
  if ((now - gApi.stateDirtyAtMs()) < kStateDebounceMs) return;
  gStore.saveState(gConfig.lastState);
  gApi.clearStateDirty();
}

void handlePendingDeviceActions() {
  if (gApi.factoryResetRequested()) {
    gApi.clearFactoryResetRequest();
    delay(200);
    gStore.clear();
    delay(150);
    ESP.restart();
  }
  if (gApi.rebootRequested()) {
    delay(200);
    ESP.restart();
  }
}

}  // namespace

#ifndef UNIT_TEST
void setup() {
  Serial.begin(115200);

  // Wait for USB CDC host enumeration. On ESP32-C6 with native USB CDC,
  // bytes written before the host opens the port are dropped. `Serial`
  // becomes truthy when the host asserts DTR. Bound the wait to 3s so a
  // headless boot (no host attached) still proceeds.
  unsigned long serialT0 = millis();
  while (!Serial && (millis() - serialT0) < 3000) {
    delay(10);
  }
  delay(300);  // settle after host opens port

  // Hostname must be computed before any beacon emission so the wizard can
  // build the correct mDNS URL even if it never sees `server_started`.
  computeHostname();

  // Autonomous ready beacon: the host wizard listens for this AND/OR pong.
  Serial.printf(
      "{\"ok\":true,\"event\":\"ready\",\"fw\":\"%s\",\"host\":\"%s\"}\n",
      BUSYLIGHT_VERSION, gDeviceHostname.c_str());

  gLed.begin();

  gStore.begin();
  gConfig = gStore.load();

  applyDefaultPinIfMissing();

  rebuildWifiMulti();
  rebuildScheduler();

  if (gConfig.configured) {
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(gDeviceHostname.c_str());
    startStationConnection();
    gWifi.nextRetryMs = millis() + kWifiBackoffMs[0];
  } else {
    gLed.setState(STATUS_WIFI_ERROR);
  }
}

void loop() {
  handleSerialProvisioning();

  // API handlers may have edited the saved Wi-Fi list; rebuild the
  // WiFiMulti AP table once per change rather than on every connect
  // attempt.
  if (gConfig.wifiListDirty) {
    gConfig.wifiListDirty = false;
    rebuildWifiMulti();
    // Force a fresh attempt so a new credential takes effect now.
    gWifi.kicked = false;
    gWifi.nextRetryMs = 0;
  }

  if (gConfig.scheduleDirty) {
    gConfig.scheduleDirty = false;
    rebuildScheduler();
  }

  networkingTick();

  if (gServerStarted) {
    gApi.handleClient();
    if (gConfig.mqttConfigDirty) {
      gConfig.mqttConfigDirty = false;
      gMqtt.configure(gConfig.mqtt);
    }
    gMqtt.loop();
    scheduleTick();
    persistStateIfDebounced();
    handlePendingDeviceActions();
  }

  gLed.tick(millis());
  delay(5);
}
#endif
