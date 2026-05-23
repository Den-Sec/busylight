#include "api_server.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <LittleFS.h>
#include <Update.h>
#include <WiFi.h>

namespace {

constexpr size_t kOtaMinBytes = 100UL * 1024UL;

const char kRecoveryHtml[] PROGMEM = R"HTML(<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BusyLight Recovery</title>
<style>
body{margin:0;font-family:"Segoe UI",Tahoma,sans-serif;background:#f4f4ef;color:#1f2a2a;padding:24px;}
.card{max-width:480px;margin:0 auto;background:#fff;border:1px solid #d7ddd8;border-radius:14px;padding:18px;}
h1{margin:0 0 6px;}
code{background:#eee;padding:2px 5px;border-radius:4px;}
</style>
</head>
<body>
<div class="card">
<h1>BusyLight is in recovery mode</h1>
<p>The web UI partition could not be mounted. Re-upload the LittleFS image:</p>
<pre><code>cd firmware
pio run -t uploadfs --upload-port COM3</code></pre>
<p>Or factory-reset over USB by sending the following at 115200 baud:</p>
<pre><code>{"cmd":"factory_reset","confirm":"YES"}</code></pre>
</div>
</body>
</html>)HTML";

const char* statusToString(BusyStatus s) {
  switch (s) {
    case STATUS_AVAILABLE:
      return "AVAILABLE";
    case STATUS_BUSY:
      return "BUSY";
    case STATUS_IN_CALL:
      return "IN_CALL";
    case STATUS_AWAY:
      return "AWAY";
    case STATUS_WIFI_ERROR:
      return "WIFI_ERROR";
    default:
      return "AVAILABLE";
  }
}

bool parseStatus(const String& value, BusyStatus& out) {
  if (value == "AVAILABLE") {
    out = STATUS_AVAILABLE;
    return true;
  }
  if (value == "BUSY") {
    out = STATUS_BUSY;
    return true;
  }
  if (value == "IN_CALL") {
    out = STATUS_IN_CALL;
    return true;
  }
  if (value == "AWAY") {
    out = STATUS_AWAY;
    return true;
  }
  return false;
}

}  // namespace

ApiServer::ApiServer(LedEngine* led,
                     ConfigStore* configStore,
                     AuthManager* auth,
                     DeviceConfig* config)
    : server_(80),
      ws_(81),
      led_(led),
      configStore_(configStore),
      auth_(auth),
      config_(config),
      stateDirty_(false),
      stateDirtyAtMs_(0),
      factoryResetRequested_(false),
      rebootRequested_(false),
      littleFsOk_(false),
      otaAuthOk_(false),
      otaError_(false) {}

void ApiServer::begin(bool littleFsMounted) {
  littleFsOk_ = littleFsMounted;
  const char* headerKeys[] = {"Cookie", "X-CSRF-Token", "X-Confirm"};
  server_.collectHeaders(headerKeys, 3);
  registerRoutes_();
  server_.begin();

  // WebSocket lives on a separate port: the stock WebServer doesn't
  // support the protocol upgrade, so we run a dedicated server on :81
  // and push state events to any browser that opens it.
  ws_.begin();
  ws_.onEvent([this](uint8_t num, WStype_t type, uint8_t* /*payload*/,
                     size_t /*length*/) {
    if (type == WStype_CONNECTED) {
      // Send the current state to the just-connected client so it can
      // hydrate the orb without waiting for the next change.
      char buf[80];
      snprintf(buf, sizeof(buf),
               "{\"event\":\"state\",\"state\":\"%s\"}",
               statusToString(led_->currentState()));
      ws_.sendTXT(num, buf);
    }
  });
}

void ApiServer::handleClient() {
  server_.handleClient();
  ws_.loop();
}

void ApiServer::broadcastState() {
  char buf[80];
  snprintf(buf, sizeof(buf),
           "{\"event\":\"state\",\"state\":\"%s\"}",
           statusToString(led_->currentState()));
  ws_.broadcastTXT(buf);
}

void ApiServer::clearStateDirty() {
  stateDirty_ = false;
  stateDirtyAtMs_ = 0;
}

// ---------- Helpers ----------

bool ApiServer::requireAuth_(String* sessionTokenOut) {
  String token = sessionTokenFromCookie_();
  if (!auth_->isSessionValid(token, millis())) {
    sendJsonErr_(401, "unauthorized");
    return false;
  }
  if (sessionTokenOut) *sessionTokenOut = token;
  return true;
}

bool ApiServer::requireCsrf_(const String& sessionToken) {
  String header = csrfTokenFromHeader_();
  if (!auth_->isCsrfValid(sessionToken, header)) {
    sendJsonErr_(403, "csrf_invalid");
    return false;
  }
  return true;
}

String ApiServer::readBody_() { return server_.arg("plain"); }

String ApiServer::sessionTokenFromCookie_() const {
  if (!server_.hasHeader("Cookie")) return "";
  String cookie = server_.header("Cookie");
  int start = cookie.indexOf("BLSESS=");
  if (start < 0) return "";
  start += 7;
  int end = cookie.indexOf(';', start);
  if (end < 0) end = cookie.length();
  return cookie.substring(start, end);
}

String ApiServer::csrfTokenFromHeader_() const {
  if (!server_.hasHeader("X-CSRF-Token")) return "";
  return server_.header("X-CSRF-Token");
}

void ApiServer::sendJson_(int code, const String& json) {
  server_.send(code, "application/json", json);
}

void ApiServer::sendJsonErr_(int code, const char* errCode) {
  String body = "{\"error\":\"";
  body += errCode;
  body += "\"}";
  sendJson_(code, body);
}

// ---------- Static / root ----------

void ApiServer::serveRoot_() {
  if (!littleFsOk_) {
    serveRecovery_();
    return;
  }
  File file = LittleFS.open("/index.html", "r");
  if (!file) {
    serveRecovery_();
    return;
  }
  server_.streamFile(file, "text/html");
  file.close();
}

void ApiServer::serveRecovery_() {
  server_.send_P(200, "text/html", kRecoveryHtml);
}

// ---------- Routes ----------

void ApiServer::registerRoutes_() {
  // Root + static.
  server_.on("/", HTTP_GET, [&]() { serveRoot_(); });
  if (littleFsOk_) {
    server_.serveStatic("/styles.css", LittleFS, "/styles.css");
    server_.serveStatic("/app.js", LittleFS, "/app.js");
  }

  // ----- auth -----
  server_.on("/api/auth/login", HTTP_POST, [&]() {
    JsonDocument in;
    auto err = deserializeJson(in, readBody_());
    if (err || !in["pin"].is<const char*>()) {
      sendJsonErr_(400, "invalid_payload");
      return;
    }
    String pin = String(static_cast<const char*>(in["pin"]));

    String sessionToken;
    String csrfToken;
    bool ok = auth_->login(pin, sessionToken, csrfToken, millis());
    if (!ok) {
      if (auth_->isLockedOut(millis())) {
        sendJsonErr_(429, "locked_out");
      } else {
        sendJsonErr_(401, "invalid_pin");
      }
      return;
    }

    // If the stored hash was legacy SHA-256, transparently upgrade to PBKDF2
    // now that we have the plaintext PIN in hand.
    if (AuthManager::isLegacyFormat(config_->pinHash)) {
      String newHash = AuthManager::hashPin(pin);
      config_->pinHash = newHash;
      configStore_->savePinHash(newHash);
      auth_->setPinHash(newHash);
    }

    server_.sendHeader("Set-Cookie",
                       "BLSESS=" + sessionToken +
                           "; Path=/; HttpOnly; SameSite=Lax",
                       true);
    server_.sendHeader("Set-Cookie",
                       "BLCSRF=" + csrfToken + "; Path=/; SameSite=Lax",
                       false);
    String body = "{\"ok\":true,\"csrf\":\"" + csrfToken + "\"}";
    sendJson_(200, body);
  });

  server_.on("/api/auth/logout", HTTP_POST, [&]() {
    String token = sessionTokenFromCookie_();
    auth_->logout(token);
    server_.sendHeader("Set-Cookie",
                       "BLSESS=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
                       true);
    server_.sendHeader("Set-Cookie",
                       "BLCSRF=; Path=/; Max-Age=0; SameSite=Lax", false);
    sendJson_(200, "{\"ok\":true}");
  });

  // ----- state -----
  server_.on("/api/state", HTTP_GET, [&]() {
    if (!requireAuth_()) return;

    JsonDocument out;
    out["state"] = statusToString(led_->currentState());
    out["uptime_ms"] = static_cast<unsigned long>(millis());

    String response;
    serializeJson(out, response);
    sendJson_(200, response);
  });

  server_.on("/api/state", HTTP_POST, [&]() {
    String sessionToken;
    if (!requireAuth_(&sessionToken)) return;
    if (!requireCsrf_(sessionToken)) return;

    JsonDocument in;
    auto err = deserializeJson(in, readBody_());
    if (err || !in["state"].is<const char*>()) {
      sendJsonErr_(400, "invalid_payload");
      return;
    }

    BusyStatus st;
    if (!parseStatus(String(static_cast<const char*>(in["state"])), st)) {
      sendJson_(400,
                "{\"error\":\"invalid_state\",\"allowed\":[\"AVAILABLE\","
                "\"BUSY\",\"IN_CALL\",\"AWAY\"]}");
      return;
    }

    led_->setState(st);
    if (config_->lastState != st) {
      config_->lastState = st;
      stateDirty_ = true;
      stateDirtyAtMs_ = millis();
    }
    broadcastState();
    sendJson_(200, "{\"ok\":true}");
  });

  // ----- settings -----
  server_.on("/api/settings", HTTP_GET, [&]() {
    if (!requireAuth_()) return;

    JsonDocument out;
    out["hostname"] = WiFi.getHostname() ? WiFi.getHostname() : "busylight";
    String mdns = String("http://") + (WiFi.getHostname() ? WiFi.getHostname() : "busylight") + ".local";
    out["mdns"] = mdns;
    out["ip"] = WiFi.localIP().toString();
    out["rssi"] = WiFi.RSSI();
#ifdef BUSYLIGHT_VERSION
    out["version"] = BUSYLIGHT_VERSION;
#else
    out["version"] = "dev";
#endif

    String response;
    serializeJson(out, response);
    sendJson_(200, response);
  });

  server_.on("/api/settings/pin", HTTP_POST, [&]() {
    String sessionToken;
    if (!requireAuth_(&sessionToken)) return;
    if (!requireCsrf_(sessionToken)) return;

    JsonDocument in;
    auto err = deserializeJson(in, readBody_());
    if (err || !in["current_pin"].is<const char*>() ||
        !in["new_pin"].is<const char*>()) {
      sendJsonErr_(400, "invalid_payload");
      return;
    }

    String currentPin = String(static_cast<const char*>(in["current_pin"]));
    String newPin = String(static_cast<const char*>(in["new_pin"]));

    if (!AuthManager::verifyPin(config_->pinHash, currentPin)) {
      sendJsonErr_(401, "invalid_current_pin");
      return;
    }

    if (newPin.length() < 4 || newPin.length() > 8) {
      sendJsonErr_(422, "pin_length");
      return;
    }
    for (size_t i = 0; i < newPin.length(); i++) {
      if (!isDigit(newPin[i])) {
        sendJsonErr_(422, "pin_digits_only");
        return;
      }
    }

    String newHash = AuthManager::hashPin(newPin);
    config_->pinHash = newHash;
    configStore_->savePinHash(newHash);
    auth_->setPinHash(newHash);
    sendJson_(200, "{\"ok\":true}");
  });

  // ----- wi-fi -----
  server_.on("/api/wifi", HTTP_GET, [&]() {
    if (!requireAuth_()) return;

    String currentSsid = WiFi.SSID();
    String body = "{\"networks\":[";
    bool first = true;
    for (const auto& net : config_->networks) {
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
    sendJson_(200, body);
  });

  server_.on("/api/wifi", HTTP_POST, [&]() {
    String sessionToken;
    if (!requireAuth_(&sessionToken)) return;
    if (!requireCsrf_(sessionToken)) return;

    JsonDocument in;
    auto err = deserializeJson(in, readBody_());
    if (err || !in["ssid"].is<const char*>()) {
      sendJsonErr_(400, "invalid_payload");
      return;
    }

    String ssid = String(static_cast<const char*>(in["ssid"]));
    ssid.trim();
    String password =
        in["password"].is<const char*>()
            ? String(static_cast<const char*>(in["password"]))
            : "";

    if (ssid.length() == 0 || ssid.length() > 32) {
      sendJsonErr_(422, "ssid_length");
      return;
    }
    if (password.length() > 63) {
      sendJsonErr_(422, "password_length");
      return;
    }

    if (config_->networks.size() >= ConfigStore::kMaxWifiNetworks) {
      // Check whether this is an update of an existing entry or a
      // genuine new addition. addNetwork updates in place so the size
      // check is only meaningful when ssid is brand new.
      bool exists = false;
      for (const auto& n : config_->networks) {
        if (n.ssid == ssid) {
          exists = true;
          break;
        }
      }
      if (!exists) {
        sendJsonErr_(409, "wifi_list_full");
        return;
      }
    }

    if (!configStore_->addNetwork(ssid, password)) {
      sendJsonErr_(500, "save_failed");
      return;
    }
    config_->networks = configStore_->loadNetworks();
    config_->configured = !config_->networks.empty();
    config_->wifiListDirty = true;
    sendJson_(200, "{\"ok\":true}");
  });

  server_.on("/api/wifi", HTTP_DELETE, [&]() {
    String sessionToken;
    if (!requireAuth_(&sessionToken)) return;
    if (!requireCsrf_(sessionToken)) return;

    JsonDocument in;
    auto err = deserializeJson(in, readBody_());
    if (err || !in["ssid"].is<const char*>()) {
      sendJsonErr_(400, "invalid_payload");
      return;
    }
    String ssid = String(static_cast<const char*>(in["ssid"]));

    // Refuse to delete the network we are actively connected to unless
    // the client passes force:true. Removing the current Wi-Fi here
    // would maroon the device on the next reboot if no other saved
    // network is in range.
    bool force = in["force"].is<bool>() && in["force"].as<bool>();
    if (!force && WiFi.SSID() == ssid) {
      sendJsonErr_(409, "wifi_in_use");
      return;
    }

    if (!configStore_->removeNetwork(ssid)) {
      sendJsonErr_(404, "wifi_not_found");
      return;
    }
    config_->networks = configStore_->loadNetworks();
    config_->configured = !config_->networks.empty();
    config_->wifiListDirty = true;
    sendJson_(200, "{\"ok\":true}");
  });

  // ----- device -----
  server_.on("/api/device/reboot", HTTP_POST, [&]() {
    String sessionToken;
    if (!requireAuth_(&sessionToken)) return;
    if (!requireCsrf_(sessionToken)) return;

    sendJson_(200, "{\"ok\":true,\"rebooting\":true}");
    rebootRequested_ = true;
  });

  server_.on("/api/device/factory_reset", HTTP_POST, [&]() {
    String sessionToken;
    if (!requireAuth_(&sessionToken)) return;
    if (!requireCsrf_(sessionToken)) return;

    if (!server_.hasHeader("X-Confirm") ||
        server_.header("X-Confirm") != "YES") {
      sendJsonErr_(400, "confirm_required");
      return;
    }

    sendJson_(200, "{\"ok\":true,\"factory_reset\":true}");
    factoryResetRequested_ = true;
  });

  // ----- OTA -----
  server_.on(
      "/api/firmware/update", HTTP_POST,
      [&]() {
        // Called AFTER the upload completes.
        if (!otaAuthOk_) {
          sendJsonErr_(401, "unauthorized");
          return;
        }
        if (otaError_) {
          sendJson_(400,
                    String("{\"error\":\"") + otaErrorMsg_ + "\"}");
          otaAuthOk_ = false;
          otaError_ = false;
          otaErrorMsg_ = "";
          return;
        }
        sendJson_(200, "{\"ok\":true,\"rebooting\":true}");
        rebootRequested_ = true;
        otaAuthOk_ = false;
      },
      [&]() {
        HTTPUpload& upload = server_.upload();
        if (upload.status == UPLOAD_FILE_START) {
          otaError_ = false;
          otaErrorMsg_ = "";
          String sessionToken = sessionTokenFromCookie_();
          if (!auth_->isSessionValid(sessionToken, millis()) ||
              !auth_->isCsrfValid(sessionToken, csrfTokenFromHeader_())) {
            otaAuthOk_ = false;
            otaError_ = true;
            otaErrorMsg_ = "unauthorized";
            return;
          }
          otaAuthOk_ = true;

          if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
            otaError_ = true;
            otaErrorMsg_ = "update_begin_failed";
          }
        } else if (upload.status == UPLOAD_FILE_WRITE && otaAuthOk_ &&
                   !otaError_) {
          if (Update.write(upload.buf, upload.currentSize) !=
              upload.currentSize) {
            otaError_ = true;
            otaErrorMsg_ = "write_failed";
          }
        } else if (upload.status == UPLOAD_FILE_END && otaAuthOk_) {
          if (upload.totalSize < kOtaMinBytes) {
            otaError_ = true;
            otaErrorMsg_ = "image_too_small";
            Update.abort();
          } else if (!Update.end(true)) {
            otaError_ = true;
            otaErrorMsg_ = "update_end_failed";
          }
        }
      });

  // 404 catch-all that does NOT serve recovery HTML for /api/...
  server_.onNotFound([&]() {
    if (server_.uri().startsWith("/api/")) {
      sendJsonErr_(404, "not_found");
      return;
    }
    serveRoot_();
  });
}
