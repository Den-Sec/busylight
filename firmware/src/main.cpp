#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <WiFiMulti.h>

#include "ap_portal.h"
#include "api_server.h"
#include "ota_serial.h"
#include "auth.h"
#include "config_store.h"
#include "host_presence.h"
#include "wifi_ap_policy.h"
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
HostPresence gHost;
WifiApPolicy gApPolicy;
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
// Tracks whether networkingTick has already pushed the WIFI_ERROR
// overlay onto the LED. We use a guard so the LED engine isn't
// reset on every loop iteration (which would freeze the blink
// pattern and instantly override any user-set state).
bool gErrorLedApplied = false;

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
    // One-shot LED set: networkingTick runs every loop iteration
    // (~200 Hz). Calling `setState(WIFI_ERROR)` here unconditionally
    // hammered the LED engine — `lastToggleMs_` was reset on every
    // call so the blink never advanced (LED stuck solid red),
    // and any user-set state from the web UI / Serial was instantly
    // overridden. Apply WIFI_ERROR once and leave the LED engine
    // alone after that; the engine's `tick()` is what produces the
    // alternating red/green pattern.
    if (!gErrorLedApplied) {
      gLed.setState(STATUS_WIFI_ERROR);
      gErrorLedApplied = true;
    }
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
      // Coming back from a WIFI_ERROR overlay: restore whatever
      // state the user last asked for instead of leaving the
      // LED on the error pattern.
      if (gErrorLedApplied) {
        gLed.setState(gConfig.lastState);
        gErrorLedApplied = false;
      }
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

  if (!gErrorLedApplied) {
    gLed.setState(STATUS_WIFI_ERROR);
    gErrorLedApplied = true;
  }

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
  // Signature collection: 256 raw bytes after ota_begin acknowledged.
  if (ota_serial::isAwaitingSignature()) {
    if (!Serial.available()) return;
    uint8_t buf[256];
    uint32_t remaining = ota_serial::signatureBytesRemaining();
    int toRead = Serial.available();
    if (toRead > static_cast<int>(sizeof(buf))) {
      toRead = sizeof(buf);
    }
    if (toRead > static_cast<int>(remaining)) {
      toRead = remaining;
    }
    int n = Serial.readBytes(buf, toRead);
    if (n <= 0) return;
    String err;
    size_t got = ota_serial::writeSignatureChunk(buf, n, err);
    if (got == 0 || got != static_cast<size_t>(n)) {
      char msg[128];
      snprintf(msg, sizeof(msg),
               "{\"ok\":false,\"event\":\"ota_error\",\"error\":\"%s\"}",
               err.c_str());
      emitJson(msg);
      return;
    }
    // Signature phase done — entering streaming. ack the host so it
    // knows it can start pushing image bytes.
    if (ota_serial::isStreaming()) {
      emitJson("{\"ok\":true,\"event\":\"ota_ready\"}");
    }
    return;
  }

  // Image streaming mode: every byte read here is image payload, not
  // JSON. Pipe it straight into the OTA buffer and auto-finalize
  // when we hit the announced size.
  if (ota_serial::isStreaming()) {
    if (!Serial.available()) return;
    uint8_t buf[2048];
    uint32_t remaining = ota_serial::bytesRemaining();
    int toRead = Serial.available();
    if (toRead > static_cast<int>(sizeof(buf))) {
      toRead = sizeof(buf);
    }
    if (toRead > static_cast<int>(remaining)) {
      toRead = remaining;
    }
    int n = Serial.readBytes(buf, toRead);
    if (n <= 0) return;
    String err;
    if (ota_serial::writeChunk(buf, n, err) != static_cast<size_t>(n)) {
      char msg[128];
      snprintf(msg, sizeof(msg),
               "{\"ok\":false,\"event\":\"ota_error\",\"error\":\"%s\"}",
               err.c_str());
      emitJson(msg);
      return;
    }
    // Diagnostic breadcrumb every ~128 KB so the host (and a human
    // tailing the port) can see the stream is making progress.
    static uint32_t lastReportedBytes = 0;
    uint32_t received = ota_serial::bytesReceived();
    if (received - lastReportedBytes >= 128 * 1024 ||
        ota_serial::bytesRemaining() == 0) {
      lastReportedBytes = received;
      char dbg[80];
      snprintf(dbg, sizeof(dbg),
               "{\"ok\":true,\"event\":\"ota_progress\",\"bytes\":%u}",
               static_cast<unsigned>(received));
      Serial.println(dbg);
    }
    if (ota_serial::bytesRemaining() == 0) {
      // Tell the host we got the last byte, before we start the
      // signature verification + Update.end work which can take a
      // few seconds (and during which we can't write more JSON).
      emitJson("{\"ok\":true,\"event\":\"ota_finalizing\"}");
      Serial.flush();
      String ferr;
      if (ota_serial::finalize(ferr)) {
        emitJson("{\"ok\":true,\"event\":\"ota_complete\"}");
        // ESP.restart() tears down the USB-CDC peripheral, which
        // truncates anything still queued for transmission. Give the
        // host a comfortable window to drain the ack before we kill
        // the link — 1.5 s is well above the typical pyserial poll
        // cadence and short enough that the user doesn't notice it.
        Serial.flush();
        delay(1500);
        ESP.restart();
      } else {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "{\"ok\":false,\"event\":\"ota_error\",\"error\":\"%s\"}",
                 ferr.c_str());
        emitJson(msg);
        Serial.flush();
      }
    }
    return;
  }

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
  if (cmd == "set_pin") {
    if (!in["new_pin"].is<const char*>()) {
      emitJson("{\"ok\":false,\"error\":\"new_pin_missing\"}");
      return;
    }
    String newPin = String(static_cast<const char*>(in["new_pin"]));
    newPin.trim();
    if (newPin.length() < 4 || newPin.length() > 8) {
      emitJson("{\"ok\":false,\"error\":\"pin_length\"}");
      return;
    }
    for (size_t i = 0; i < newPin.length(); i++) {
      if (!isdigit(newPin[i])) {
        emitJson("{\"ok\":false,\"error\":\"pin_not_digits\"}");
        return;
      }
    }
    String h = AuthManager::hashPin(newPin);
    if (!gStore.savePinHash(h)) {
      emitJson("{\"ok\":false,\"error\":\"save_failed\"}");
      return;
    }
    gConfig.pinHash = h;
    gAuth.setPinHash(h);
    emitJson("{\"ok\":true,\"event\":\"pin_changed\"}");
    return;
  }
  if (cmd == "wifi_list") {
    // Mirror of GET /api/wifi: returns the saved networks list with
    // a flag for which (if any) is currently connected.
    String currentSsid = WiFi.SSID();
    String body = "{\"ok\":true,\"event\":\"wifi_list\",\"networks\":[";
    bool first = true;
    for (const auto& net : gConfig.networks) {
      if (!first) body += ",";
      first = false;
      body += "{\"ssid\":\"";
      body += net.ssid;
      body += "\",\"current\":";
      body += (net.ssid == currentSsid) ? "true" : "false";
      body += "}";
    }
    body += "],\"max\":";
    body += String(static_cast<unsigned>(ConfigStore::kMaxWifiNetworks));
    body += "}";
    emitJson(body.c_str());
    return;
  }
  if (cmd == "wifi_remove") {
    if (!in["ssid"].is<const char*>()) {
      emitJson("{\"ok\":false,\"error\":\"ssid_missing\"}");
      return;
    }
    String ssid = String(static_cast<const char*>(in["ssid"]));
    ssid.trim();
    if (!gStore.removeNetwork(ssid)) {
      emitJson("{\"ok\":false,\"error\":\"not_found\"}");
      return;
    }
    gConfig.networks = gStore.loadNetworks();
    gConfig.configured = !gConfig.networks.empty();
    gConfig.wifiListDirty = true;
    emitJson("{\"ok\":true,\"event\":\"wifi_removed\"}");
    return;
  }
  if (cmd == "wifi_add") {
    // Add a Wi-Fi network without resetting other config (PIN,
    // existing networks). Same semantics as POST /api/wifi over
    // HTTP but reachable from the desktop app over USB.
    if (!in["ssid"].is<const char*>()) {
      emitJson("{\"ok\":false,\"error\":\"ssid_missing\"}");
      return;
    }
    String ssid = String(static_cast<const char*>(in["ssid"]));
    ssid.trim();
    String password = in["password"].is<const char*>()
                          ? String(static_cast<const char*>(in["password"]))
                          : "";
    if (ssid.length() == 0 || ssid.length() > 32) {
      emitJson("{\"ok\":false,\"error\":\"ssid_length\"}");
      return;
    }
    if (password.length() > 63) {
      emitJson("{\"ok\":false,\"error\":\"password_length\"}");
      return;
    }
    if (!gStore.addNetwork(ssid, password)) {
      emitJson("{\"ok\":false,\"error\":\"save_failed\"}");
      return;
    }
    gConfig.networks = gStore.loadNetworks();
    gConfig.configured = !gConfig.networks.empty();
    gConfig.wifiListDirty = true;
    emitJson("{\"ok\":true,\"event\":\"wifi_added\"}");
    return;
  }
  if (cmd == "ota_begin") {
    if (!in["size"].is<int>() && !in["size"].is<uint32_t>()) {
      emitJson("{\"ok\":false,\"error\":\"size_missing\"}");
      return;
    }
    uint32_t size = in["size"].as<uint32_t>();
    String err;
    if (ota_serial::begin(size, err)) {
      // Caller must now send 256 raw signature bytes.
      emitJson("{\"ok\":true,\"event\":\"ota_awaiting_sig\"}");
    } else {
      char buf[128];
      snprintf(buf, sizeof(buf),
               "{\"ok\":false,\"error\":\"%s\"}", err.c_str());
      emitJson(buf);
    }
    return;
  }
  if (cmd == "ota_abort") {
    ota_serial::reset();
    emitJson("{\"ok\":true,\"event\":\"ota_aborted\"}");
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
  // Grow the USB-CDC RX buffer before begin() so OTA streaming
  // doesn't drop bytes when the host writes 4 KB chunks. Default is
  // 256 B on ESP32-C6 native USB — fine for JSON commands, not for
  // a megabyte of firmware image.
  Serial.setRxBufferSize(8192);
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

  // While an OTA session is in flight, every async beacon we'd emit
  // (wifi_retry, ntp_synced, server_started, ...) competes for the
  // USB-CDC TX ring that the host needs to receive the final
  // `ota_complete` ack. Skip all background work until OTA finishes
  // or aborts — the device is dedicated to the upload for those few
  // seconds anyway.
  if (ota_serial::isActive()) {
    gLed.tick(millis());
    delay(1);
    return;
  }

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
