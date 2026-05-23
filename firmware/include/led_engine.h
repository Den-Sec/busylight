#pragma once

enum BusyStatus {
  STATUS_AVAILABLE = 0,
  STATUS_BUSY = 1,
  STATUS_IN_CALL = 2,
  STATUS_AWAY = 3,
  STATUS_WIFI_ERROR = 4
};

class LedEngine {
 public:
  LedEngine(int redPin, int greenPin);
  void begin();
  void setState(BusyStatus state);
  BusyStatus currentState() const;
  void tick(unsigned long nowMs);
  bool redOn() const;
  bool greenOn() const;

 private:
  int redPin_;
  int greenPin_;
  BusyStatus state_;
  bool redOn_;
  bool greenOn_;
  bool blinkPhase_;
  unsigned long lastToggleMs_;

  void applyOutputs();
};
