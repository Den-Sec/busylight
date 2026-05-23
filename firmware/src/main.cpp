#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <LittleFS.h>
#include <WiFi.h>

#include "ap_portal.h"
#include "api_server.h"
#include "auth.h"
#include "config_store.h"
#include "hostname.h"
#include "led_engine.h"

namespace {

constexpr int kRedPin = 4;
constexpr int kGreenPin = 5;

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

void leaveApPortal() {
  gApPortal.stop();
  gWifi.attemptIndex = 0;
  gWifi.failuresTotal = 0;
  gWifi.nextRetryMs = 0;
  gWifi.kicked = false;
  gServerStarted = false;
  gWifiWasConnected = false;
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(gDeviceHostname.c_str());
  if (gConfig.configured) {
    WiFi.begin(gConfig.ssid.c_str(), gConfig.password.c_str());
  }
}

void startStationConnection() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(gDeviceHostname.c_str());
  WiFi.disconnect(true, false);
  WiFi.begin(gConfig.ssid.c_str(), gConfig.password.c_str());
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
      gStore.saveNetwork(ssid, password);
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

  if (!gConfig.configured || gConfig.ssid.length() == 0) {
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

  gStore.saveNetwork(ssid, password);
  gConfig.ssid = ssid;
  gConfig.password = password;
  gConfig.configured = true;

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
  networkingTick();

  if (gServerStarted) {
    gApi.handleClient();
    persistStateIfDebounced();
    handlePendingDeviceActions();
  }

  gLed.tick(millis());
  delay(5);
}
#endif
