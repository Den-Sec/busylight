#include <unity.h>

#include "led_engine.h"

void test_default_state_is_available() {
  LedEngine engine(4, 5);
  TEST_ASSERT_EQUAL(STATUS_AVAILABLE, engine.currentState());
}

void test_available_lights_green_solid() {
  LedEngine engine(4, 5);
  engine.setState(STATUS_AVAILABLE);
  engine.tick(0);
  TEST_ASSERT_FALSE(engine.redOn());
  TEST_ASSERT_TRUE(engine.greenOn());
}

void test_busy_sets_red_on_green_off() {
  LedEngine engine(4, 5);
  engine.setState(STATUS_BUSY);
  engine.tick(0);
  TEST_ASSERT_TRUE(engine.redOn());
  TEST_ASSERT_FALSE(engine.greenOn());
}

void test_in_call_toggles_red_every_250ms() {
  LedEngine engine(4, 5);
  engine.setState(STATUS_IN_CALL);
  engine.tick(0);
  bool phaseA = engine.redOn();
  engine.tick(260);
  bool phaseB = engine.redOn();
  TEST_ASSERT_NOT_EQUAL(phaseA, phaseB);
  TEST_ASSERT_FALSE(engine.greenOn());
}

void test_away_toggles_green_every_900ms() {
  LedEngine engine(4, 5);
  engine.setState(STATUS_AWAY);
  engine.tick(0);
  bool phaseA = engine.greenOn();
  engine.tick(950);
  bool phaseB = engine.greenOn();
  TEST_ASSERT_NOT_EQUAL(phaseA, phaseB);
  TEST_ASSERT_FALSE(engine.redOn());
}

void test_wifi_error_alternates_red_and_green() {
  LedEngine engine(4, 5);
  engine.setState(STATUS_WIFI_ERROR);
  engine.tick(0);
  bool red0 = engine.redOn();
  bool green0 = engine.greenOn();
  TEST_ASSERT_NOT_EQUAL(red0, green0);
  engine.tick(420);
  bool red1 = engine.redOn();
  bool green1 = engine.greenOn();
  TEST_ASSERT_NOT_EQUAL(red0, red1);
  TEST_ASSERT_NOT_EQUAL(green0, green1);
}

void test_state_change_resets_blink_phase() {
  LedEngine engine(4, 5);
  engine.setState(STATUS_IN_CALL);
  engine.tick(0);
  engine.tick(300);  // mid-blink
  engine.setState(STATUS_AVAILABLE);
  engine.tick(301);
  TEST_ASSERT_FALSE(engine.redOn());
  TEST_ASSERT_TRUE(engine.greenOn());
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_default_state_is_available);
  RUN_TEST(test_available_lights_green_solid);
  RUN_TEST(test_busy_sets_red_on_green_off);
  RUN_TEST(test_in_call_toggles_red_every_250ms);
  RUN_TEST(test_away_toggles_green_every_900ms);
  RUN_TEST(test_wifi_error_alternates_red_and_green);
  RUN_TEST(test_state_change_resets_blink_phase);
  UNITY_END();
}

void loop() {}
