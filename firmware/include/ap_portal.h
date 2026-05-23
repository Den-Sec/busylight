#pragma once

#include <Arduino.h>
#include <DNSServer.h>
#include <WebServer.h>

// Lightweight captive-portal-style WiFi provisioning entry point.
//
// Activated by `main.cpp` when the station-mode reconnect loop has failed
// repeatedly. While active the device exposes an open WiFi network named
// `BusyLight-XXXX-Setup`; any client that joins is redirected (via a DNS
// catch-all) to a one-page web form. Submitting the form stores the new
// SSID/password/PIN and triggers a reboot.
class ApPortal {
 public:
  ApPortal();

  // Bring up the soft-AP, DNS catch-all, and the setup web server.
  // `apSsid` should be a short device-local string (e.g. "BusyLight-760c-Setup").
  void begin(const String& apSsid);

  // Pump the DNS and HTTP servers. Must be called every loop iteration while
  // the portal is active.
  void tick();

  // Tear everything down and free RAM.
  void stop();

  bool isActive() const { return active_; }
  bool hasNewConfig() const { return received_; }

  // Valid only after `hasNewConfig()` returns true.
  const String& pendingSsid() const { return pendingSsid_; }
  const String& pendingPassword() const { return pendingPassword_; }
  const String& pendingPin() const { return pendingPin_; }

  // Milliseconds since `begin()`. Used by the caller to enforce a timeout.
  unsigned long uptimeMs() const;

 private:
  WebServer server_;
  DNSServer dns_;
  bool active_;
  bool received_;
  unsigned long startMs_;

  String pendingSsid_;
  String pendingPassword_;
  String pendingPin_;

  void serveSetupPage_();
  void handleSave_();
  void registerRoutes_();
};
