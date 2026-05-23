#pragma once

#include <WebServer.h>
#include <WebSocketsServer.h>

#include <functional>

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

  // Push the current state to all connected WebSocket clients. Called
  // by every code path that flips the LED (web API, AP portal save,
  // periodic refresh). Cheap when no client is attached.
  void broadcastState();

  // Apply a state change from any source (web API, MQTT command,
  // presence helper, …). Flips the LED, marks the state dirty for
  // NVS persistence, broadcasts on WebSocket, and notifies any
  // listener registered via `setOnStateChanged`.
  void applyState(BusyStatus state);

  // Register a callback fired right after `applyState` mutates the
  // device state. Used by the MQTT bridge so external controllers
  // see live state changes too.
  void setOnStateChanged(std::function<void(BusyStatus)> cb) {
    onStateChanged_ = std::move(cb);
  }

 private:
  WebServer server_;
  WebSocketsServer ws_;
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
  // Decoded RSA-2048 signature received in the X-Firmware-Signature
  // header at upload start. The OTA endpoint refuses the upload if it
  // is missing, malformed, or doesn't verify against the computed
  // SHA-256 of the streamed bytes.
  uint8_t otaSignature_[256];
  size_t otaSignatureLen_;
  // Incremental SHA-256 of everything the client has streamed so far.
  // Opaque pointer to a heap-allocated mbedtls_sha256_context so this
  // header doesn't have to pull in mbedtls.
  void* otaShaCtx_;

  std::function<void(BusyStatus)> onStateChanged_;

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
