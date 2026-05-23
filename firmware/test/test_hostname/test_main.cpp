#include <unity.h>

#include "hostname.h"

void test_hostname_uses_last_four_mac_bytes() {
  // efuseMac is little-endian; the production code masks the low 16 bits.
  uint64_t mac = 0xf0f5bd02760cULL;
  String host = busylight::makeHostname(mac);
  TEST_ASSERT_EQUAL_STRING("busylight-760c", host.c_str());
}

void test_hostname_pads_short_low_bytes_with_zeros() {
  uint64_t mac = 0x0001ULL;
  TEST_ASSERT_EQUAL_STRING("busylight-0001",
                           busylight::makeHostname(mac).c_str());
}

void test_hostname_truncates_to_low_16_bits() {
  uint64_t mac = 0xffffffffff0042ULL;
  TEST_ASSERT_EQUAL_STRING("busylight-0042",
                           busylight::makeHostname(mac).c_str());
}

void test_hostname_uses_lowercase_hex() {
  uint64_t mac = 0xabcdULL;
  TEST_ASSERT_EQUAL_STRING("busylight-abcd",
                           busylight::makeHostname(mac).c_str());
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_hostname_uses_last_four_mac_bytes);
  RUN_TEST(test_hostname_pads_short_low_bytes_with_zeros);
  RUN_TEST(test_hostname_truncates_to_low_16_bits);
  RUN_TEST(test_hostname_uses_lowercase_hex);
  UNITY_END();
}

void loop() {}
