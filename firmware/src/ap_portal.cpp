#include "ap_portal.h"

#include <WiFi.h>

namespace {

constexpr uint16_t kDnsPort = 53;
constexpr uint16_t kHttpPort = 80;
const IPAddress kApIp(192, 168, 4, 1);
const IPAddress kApGw(192, 168, 4, 1);
const IPAddress kApMask(255, 255, 255, 0);

const char kSetupHtml[] PROGMEM = R"HTML(<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>BusyLight Setup</title>
<style>
:root{--bg:#f4f4ef;--ink:#1f2a2a;--ok:#1f7a47;--border:#d7ddd8;}
body{margin:0;font-family:"Segoe UI",Tahoma,sans-serif;color:var(--ink);background:var(--bg);}
.card{max-width:420px;margin:24px auto;padding:18px;background:#fff;border:1px solid var(--border);border-radius:14px;}
h1{margin:0 0 6px;font-size:1.4rem;}
p{color:#556;margin-top:4px;}
label{display:block;margin:10px 0 4px;font-size:.92rem;}
input{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--border);font-size:1rem;box-sizing:border-box;}
button{margin-top:14px;width:100%;padding:11px;border:0;border-radius:10px;background:var(--ok);color:#fff;font-size:1rem;cursor:pointer;}
.hint{color:#778;font-size:.85rem;}
</style>
</head>
<body>
<div class="card">
  <h1>BusyLight Setup</h1>
  <p class="hint">Connect this BusyLight to your WiFi. The device will reboot when you save.</p>
  <form method="POST" action="/save" autocomplete="off">
    <label for="ssid">WiFi SSID</label>
    <input id="ssid" name="ssid" maxlength="32" required>
    <label for="password">WiFi password</label>
    <input id="password" name="password" type="password" maxlength="63">
    <label for="pin">PIN (4-8 digits)</label>
    <input id="pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{4,8}" required>
    <button type="submit">Save and reboot</button>
  </form>
</div>
</body>
</html>)HTML";

const char kSavedHtml[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta charset="utf-8"><title>Saved</title>
<style>body{font-family:"Segoe UI",Tahoma,sans-serif;background:#f4f4ef;color:#1f2a2a;padding:24px;}</style>
</head><body>
<h1>Saved.</h1>
<p>BusyLight is rebooting and will try to join the WiFi you just provided.</p>
<p>Watch the LED. Green/red alternating means BusyLight is still failing to connect.</p>
</body></html>)HTML";

}  // namespace

ApPortal::ApPortal()
    : server_(kHttpPort), active_(false), received_(false), startMs_(0) {}

void ApPortal::begin(const String& apSsid) {
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(kApIp, kApGw, kApMask);
  WiFi.softAP(apSsid.c_str());  // open network, no password

  dns_.setErrorReplyCode(DNSReplyCode::NoError);
  dns_.start(kDnsPort, "*", kApIp);

  registerRoutes_();
  server_.begin();

  active_ = true;
  received_ = false;
  startMs_ = millis();
  pendingSsid_ = "";
  pendingPassword_ = "";
  pendingPin_ = "";
}

void ApPortal::tick() {
  if (!active_) return;
  dns_.processNextRequest();
  server_.handleClient();
}

void ApPortal::stop() {
  if (!active_) return;
  server_.stop();
  dns_.stop();
  WiFi.softAPdisconnect(true);
  active_ = false;
}

unsigned long ApPortal::uptimeMs() const {
  return active_ ? (millis() - startMs_) : 0;
}

void ApPortal::registerRoutes_() {
  // Captive portal: every URL serves the same setup page until the user
  // submits the form. This is how phones detect that "no internet" and
  // pop the captive UI.
  auto setup = [this]() { this->serveSetupPage_(); };
  server_.on("/", HTTP_GET, setup);
  server_.on("/setup", HTTP_GET, setup);
  server_.on("/generate_204", HTTP_GET, setup);     // Android
  server_.on("/hotspot-detect.html", HTTP_GET, setup);  // iOS / macOS
  server_.on("/save", HTTP_POST, [this]() { this->handleSave_(); });
  server_.onNotFound(setup);
}

void ApPortal::serveSetupPage_() {
  server_.send_P(200, "text/html", kSetupHtml);
}

void ApPortal::handleSave_() {
  if (!server_.hasArg("ssid") || !server_.hasArg("pin")) {
    server_.send(400, "text/plain", "Missing fields.");
    return;
  }
  String ssid = server_.arg("ssid");
  String password = server_.arg("password");  // may be empty for open WiFi
  String pin = server_.arg("pin");

  ssid.trim();
  pin.trim();
  if (ssid.length() == 0 || ssid.length() > 32) {
    server_.send(400, "text/plain", "SSID must be 1-32 characters.");
    return;
  }
  if (password.length() > 63) {
    server_.send(400, "text/plain", "Password must be at most 63 characters.");
    return;
  }
  if (pin.length() < 4 || pin.length() > 8) {
    server_.send(400, "text/plain", "PIN must be 4-8 digits.");
    return;
  }
  for (size_t i = 0; i < pin.length(); i++) {
    if (!isDigit(pin[i])) {
      server_.send(400, "text/plain", "PIN must be digits only.");
      return;
    }
  }

  pendingSsid_ = ssid;
  pendingPassword_ = password;
  pendingPin_ = pin;
  received_ = true;

  server_.send_P(200, "text/html", kSavedHtml);
}
