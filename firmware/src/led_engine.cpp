#include "led_engine.h"

#include <Arduino.h>

namespace {
unsigned long intervalFor(BusyStatus state) {
  switch (state) {
    case STATUS_IN_CALL:
      return 250;
    case STATUS_AWAY:
      return 900;
    case STATUS_WIFI_ERROR:
      return 400;
    default:
      return 0;
  }
}
}

LedEngine::LedEngine(int redPin, int greenPin)
    : redPin_(redPin),
      greenPin_(greenPin),
      state_(STATUS_AVAILABLE),
      redOn_(false),
      greenOn_(true),
      blinkPhase_(false),
      lastToggleMs_(0) {}

void LedEngine::begin() {
  pinMode(redPin_, OUTPUT);
  pinMode(greenPin_, OUTPUT);
  applyOutputs();
}

void LedEngine::setState(BusyStatus state) {
  state_ = state;
  lastToggleMs_ = 0;
  blinkPhase_ = false;

  if (state_ == STATUS_AVAILABLE) {
    redOn_ = false;
    greenOn_ = true;
  } else if (state_ == STATUS_BUSY) {
    redOn_ = true;
    greenOn_ = false;
  }

  applyOutputs();
}

BusyStatus LedEngine::currentState() const { return state_; }

void LedEngine::tick(unsigned long nowMs) {
  unsigned long interval = intervalFor(state_);
  if (interval == 0) {
    applyOutputs();
    return;
  }

  if (lastToggleMs_ == 0) {
    lastToggleMs_ = nowMs;
  }

  if (nowMs - lastToggleMs_ < interval) {
    return;
  }

  lastToggleMs_ = nowMs;
  blinkPhase_ = !blinkPhase_;

  switch (state_) {
    case STATUS_IN_CALL:
      redOn_ = blinkPhase_;
      greenOn_ = false;
      break;
    case STATUS_AWAY:
      redOn_ = false;
      greenOn_ = blinkPhase_;
      break;
    case STATUS_WIFI_ERROR:
      redOn_ = blinkPhase_;
      greenOn_ = !blinkPhase_;
      break;
    default:
      break;
  }

  applyOutputs();
}

bool LedEngine::redOn() const { return redOn_; }
bool LedEngine::greenOn() const { return greenOn_; }

void LedEngine::applyOutputs() {
  digitalWrite(redPin_, redOn_ ? HIGH : LOW);
  digitalWrite(greenPin_, greenOn_ ? HIGH : LOW);
}
