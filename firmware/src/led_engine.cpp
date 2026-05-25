#include "led_engine.h"

#include <Arduino.h>

namespace {
unsigned long intervalFor(BusyStatus state) {
  switch (state) {
    case STATUS_IN_CALL:
      // 500 ms half-cycle => 1 Hz blink. 250 ms was visually almost
      // indistinguishable from BUSY (solid red) because the eye
      // smooths fast red oscillation; users reported "IN_CALL looks
      // the same as BUSY".
      return 500;
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

  // Set initial outputs for every state. Previously only the static
  // states (AVAILABLE/BUSY/OFF) had a branch here, which meant the
  // blinking states (AWAY/IN_CALL/WIFI_ERROR) kept the previous
  // state's red/green flags until the first `tick()` interval
  // elapsed — so switching from BUSY to AWAY visibly stayed red for
  // 900 ms before the green blink started, etc.
  switch (state_) {
    case STATUS_AVAILABLE:
      redOn_ = false;
      greenOn_ = true;
      break;
    case STATUS_BUSY:
      redOn_ = true;
      greenOn_ = false;
      break;
    case STATUS_IN_CALL:
      // Blink red. Start the half-cycle in the ON phase so the user
      // immediately sees the new state instead of a brief off period.
      redOn_ = true;
      greenOn_ = false;
      blinkPhase_ = true;
      break;
    case STATUS_AWAY:
      // Blink green.
      redOn_ = false;
      greenOn_ = true;
      blinkPhase_ = true;
      break;
    case STATUS_WIFI_ERROR:
      redOn_ = true;
      greenOn_ = false;
      blinkPhase_ = true;
      break;
    case STATUS_OFF:
      redOn_ = false;
      greenOn_ = false;
      break;
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
