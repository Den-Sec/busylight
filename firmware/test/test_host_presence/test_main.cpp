// firmware/test/test_host_presence/test_main.cpp
#include <unity.h>

#include "host_presence.h"

void test_absent_before_any_activity() {
  HostPresence h(15000);
  TEST_ASSERT_FALSE(h.present(0));
  TEST_ASSERT_FALSE(h.present(1000000));
}

void test_present_within_window_after_serial() {
  HostPresence h(15000);
  h.noteSerialActivity(1000);
  TEST_ASSERT_TRUE(h.present(1000));
  TEST_ASSERT_TRUE(h.present(1000 + 15000));   // edge of window
}

void test_absent_after_window_elapses() {
  HostPresence h(15000);
  h.noteSerialActivity(1000);
  TEST_ASSERT_FALSE(h.present(1000 + 15001));
}

void test_dtr_keeps_present_regardless_of_time() {
  HostPresence h(15000);
  h.noteDtr(true);
  TEST_ASSERT_TRUE(h.present(999999));
  h.noteDtr(false);
  TEST_ASSERT_FALSE(h.present(999999));
}

void test_unsigned_wraparound_is_safe() {
  HostPresence h(15000);
  h.noteSerialActivity(0xFFFFFFF0u);           // just before wrap
  TEST_ASSERT_TRUE(h.present(0x00000005u));    // 21 ms later across wrap
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_absent_before_any_activity);
  RUN_TEST(test_present_within_window_after_serial);
  RUN_TEST(test_absent_after_window_elapses);
  RUN_TEST(test_dtr_keeps_present_regardless_of_time);
  RUN_TEST(test_unsigned_wraparound_is_safe);
  UNITY_END();
}

void loop() {}
