// firmware/test/test_wifi_ap_policy/test_main.cpp
#include <unity.h>

#include "wifi_ap_policy.h"

static const uint32_t GRACE = 5UL * 60UL * 1000UL;  // 5 min

void test_no_ap_within_grace() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(false, 1000);
  TEST_ASSERT_FALSE(p.shouldEnterAp(false, GRACE - 1));
}

void test_ap_after_grace_when_no_host() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(false, 1000);
  TEST_ASSERT_TRUE(p.shouldEnterAp(false, GRACE + 1));
}

void test_never_ap_while_host_present() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(false, 1000);
  TEST_ASSERT_FALSE(p.shouldEnterAp(true, GRACE + 100000));
}

void test_reachable_resets_grace_clock() {
  WifiApPolicy p(GRACE);
  p.begin(0);
  p.update(true, GRACE - 1);           // saw a saved network late in the window
  TEST_ASSERT_FALSE(p.shouldEnterAp(false, GRACE + 1));  // clock reset
  TEST_ASSERT_TRUE(p.shouldEnterAp(false, (GRACE - 1) + GRACE + 1));
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_no_ap_within_grace);
  RUN_TEST(test_ap_after_grace_when_no_host);
  RUN_TEST(test_never_ap_while_host_present);
  RUN_TEST(test_reachable_resets_grace_clock);
  UNITY_END();
}

void loop() {}
