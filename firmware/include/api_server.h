#pragma once

#include <WebServer.h>

#include "auth.h"
#include "config_store.h"
#include "led_engine.h"

class ApiServer {
 public:
  ApiServer(LedEngine* led,
            ConfigStore* configStore,
            AuthManager* auth,
            DeviceConfig* config);

  // `littleFsMounted` lets the server serve a recovery HTML inline when the
  // data partition could not be mounted.
  void begin(bool littleFsMounted);
  void handleClient();

  // State debounce: `main.cpp` checks these every loop and persists the
  // current state to NVS once it has been stable for `kStateDebounceMs`.
  bool isStateDirty() const { return stateDirty_; }
  unsigned long stateDirtyAtMs() const { return stateDirtyAtMs_; }
  void clearStateDirty();

  // Set by web handler when the user explicitly asks for a factory reset.
  // `main.cpp` reads it, wipes NVS and reboots.
  bool factoryResetRequested() const { return factoryResetRequested_; }
  void clearFactoryResetRequest() { factoryResetRequested_ = false; }

  // After a successful OTA flash the device must reboot. `main.cpp` polls
  // this so the reboot does not interrupt the HTTP response.
  bool rebootRequested() const { return rebootRequested_; }

 private:
  WebServer server_;
  LedEngine* led_;
  ConfigStore* configStore_;
  AuthManager* auth_;
  DeviceConfig* config_;

  bool stateDirty_;
  unsigned long stateDirtyAtMs_;
  bool factoryResetRequested_;
  bool rebootRequested_;
  bool littleFsOk_;

  // OTA upload state (one upload at a time).
  bool otaAuthOk_;
  bool otaError_;
  String otaErrorMsg_;

  void registerRoutes_();
  bool requireAuth_(String* sessionTokenOut = nullptr);
  bool requireCsrf_(const String& sessionToken);
  String sessionTokenFromCookie_() const;
  String csrfTokenFromHeader_() const;
  String readBody_();
  void sendJson_(int code, const String& json);
  void sendJsonErr_(int code, const char* errCode);

  void serveRoot_();
  void serveRecovery_();
};
