#include <unity.h>

#include "auth.h"

namespace {

constexpr unsigned long kAt0 = 1000UL;
constexpr unsigned long k1Min = 61UL * 1000UL;
constexpr unsigned long k9Hours = 9UL * 60UL * 60UL * 1000UL;

void seedAuth(AuthManager& auth, const char* pin = "1234") {
  auth.setPinHash(AuthManager::hashPin(pin));
}

}  // namespace

// ---------- PIN hashing ----------

void test_hash_format_is_pbkdf2() {
  String hash = AuthManager::hashPin("1234");
  TEST_ASSERT_TRUE(hash.startsWith("pbkdf2$10000$"));
  // pbkdf2$10000$<32hex>$<64hex> -> 7 + 5 + 1 + 32 + 1 + 64 = 110
  TEST_ASSERT_EQUAL(110, hash.length());
}

void test_hash_uses_random_salt() {
  String a = AuthManager::hashPin("1234");
  String b = AuthManager::hashPin("1234");
  TEST_ASSERT_FALSE(a == b);
}

void test_verify_pin_accepts_correct() {
  String hash = AuthManager::hashPin("4242");
  TEST_ASSERT_TRUE(AuthManager::verifyPin(hash, "4242"));
}

void test_verify_pin_rejects_wrong() {
  String hash = AuthManager::hashPin("4242");
  TEST_ASSERT_FALSE(AuthManager::verifyPin(hash, "1234"));
}

void test_legacy_sha256_hash_still_verifies() {
  // legacy v0.1.0 hash for "1234" computed offline:
  // sha256("1234") = "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4"
  String legacy =
      "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4";
  TEST_ASSERT_TRUE(AuthManager::isLegacyFormat(legacy));
  TEST_ASSERT_TRUE(AuthManager::verifyPin(legacy, "1234"));
  TEST_ASSERT_FALSE(AuthManager::verifyPin(legacy, "0000"));
}

// ---------- Login + sessions ----------

void test_valid_pin_creates_session() {
  AuthManager auth;
  seedAuth(auth);

  String session;
  String csrf;
  TEST_ASSERT_TRUE(auth.login("1234", session, csrf, kAt0));
  TEST_ASSERT_EQUAL(32, session.length());
  TEST_ASSERT_EQUAL(32, csrf.length());
  TEST_ASSERT_TRUE(auth.isSessionValid(session, kAt0 + 1));
}

void test_invalid_pin_rejected() {
  AuthManager auth;
  seedAuth(auth);

  String session;
  String csrf;
  TEST_ASSERT_FALSE(auth.login("0000", session, csrf, kAt0));
  TEST_ASSERT_EQUAL(0, session.length());
}

void test_session_expires_after_ttl() {
  AuthManager auth;
  seedAuth(auth);

  String session;
  String csrf;
  TEST_ASSERT_TRUE(auth.login("1234", session, csrf, kAt0));
  TEST_ASSERT_TRUE(auth.isSessionValid(session, kAt0 + 1));
  TEST_ASSERT_FALSE(auth.isSessionValid(session, kAt0 + k9Hours));
}

void test_logout_invalidates_session() {
  AuthManager auth;
  seedAuth(auth);

  String session, csrf;
  auth.login("1234", session, csrf, kAt0);
  TEST_ASSERT_TRUE(auth.logout(session));
  TEST_ASSERT_FALSE(auth.isSessionValid(session, kAt0 + 1));
}

// ---------- Lockout ----------

void test_lockout_after_five_failed_attempts() {
  AuthManager auth;
  seedAuth(auth);

  String session, csrf;
  for (int i = 0; i < 5; i++) {
    TEST_ASSERT_FALSE(auth.login("0000", session, csrf, kAt0 + i));
  }
  // 6th attempt: device locked out; even the correct PIN now fails.
  TEST_ASSERT_TRUE(auth.isLockedOut(kAt0 + 5));
  TEST_ASSERT_FALSE(auth.login("1234", session, csrf, kAt0 + 6));
}

void test_lockout_clears_after_window() {
  AuthManager auth;
  seedAuth(auth);

  String session, csrf;
  for (int i = 0; i < 5; i++) {
    auth.login("0000", session, csrf, kAt0 + i);
  }
  TEST_ASSERT_TRUE(auth.isLockedOut(kAt0 + 5));
  TEST_ASSERT_FALSE(auth.isLockedOut(kAt0 + 5 + k1Min + 1));
  TEST_ASSERT_TRUE(auth.login("1234", session, csrf, kAt0 + 5 + k1Min + 2));
}

// ---------- Multi-session + LRU ----------

void test_multi_session_supports_four_concurrent_logins() {
  AuthManager auth;
  seedAuth(auth);

  String sessions[4], csrfs[4];
  for (int i = 0; i < 4; i++) {
    TEST_ASSERT_TRUE(auth.login("1234", sessions[i], csrfs[i], kAt0 + i));
  }
  for (int i = 0; i < 4; i++) {
    TEST_ASSERT_TRUE(auth.isSessionValid(sessions[i], kAt0 + 10));
  }
}

void test_fifth_login_evicts_oldest() {
  AuthManager auth;
  seedAuth(auth);

  String s[5], c[5];
  for (int i = 0; i < 4; i++) {
    auth.login("1234", s[i], c[i], kAt0 + i);
  }
  // Touch all but the first so the first stays the oldest.
  for (int i = 1; i < 4; i++) {
    auth.isSessionValid(s[i], kAt0 + 100);
  }
  // 5th login evicts the LRU slot.
  TEST_ASSERT_TRUE(auth.login("1234", s[4], c[4], kAt0 + 200));
  TEST_ASSERT_FALSE(auth.isSessionValid(s[0], kAt0 + 300));
  TEST_ASSERT_TRUE(auth.isSessionValid(s[4], kAt0 + 300));
}

// ---------- CSRF ----------

void test_csrf_token_valid_for_own_session() {
  AuthManager auth;
  seedAuth(auth);

  String session, csrf;
  auth.login("1234", session, csrf, kAt0);
  TEST_ASSERT_TRUE(auth.isCsrfValid(session, csrf));
}

void test_csrf_token_rejected_for_other_session() {
  AuthManager auth;
  seedAuth(auth);

  String s1, c1, s2, c2;
  auth.login("1234", s1, c1, kAt0);
  auth.login("1234", s2, c2, kAt0 + 1);
  TEST_ASSERT_FALSE(auth.isCsrfValid(s1, c2));
  TEST_ASSERT_FALSE(auth.isCsrfValid(s2, c1));
}

void test_csrf_token_rejected_when_empty() {
  AuthManager auth;
  seedAuth(auth);

  String session, csrf;
  auth.login("1234", session, csrf, kAt0);
  TEST_ASSERT_FALSE(auth.isCsrfValid(session, ""));
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_hash_format_is_pbkdf2);
  RUN_TEST(test_hash_uses_random_salt);
  RUN_TEST(test_verify_pin_accepts_correct);
  RUN_TEST(test_verify_pin_rejects_wrong);
  RUN_TEST(test_legacy_sha256_hash_still_verifies);
  RUN_TEST(test_valid_pin_creates_session);
  RUN_TEST(test_invalid_pin_rejected);
  RUN_TEST(test_session_expires_after_ttl);
  RUN_TEST(test_logout_invalidates_session);
  RUN_TEST(test_lockout_after_five_failed_attempts);
  RUN_TEST(test_lockout_clears_after_window);
  RUN_TEST(test_multi_session_supports_four_concurrent_logins);
  RUN_TEST(test_fifth_login_evicts_oldest);
  RUN_TEST(test_csrf_token_valid_for_own_session);
  RUN_TEST(test_csrf_token_rejected_for_other_session);
  RUN_TEST(test_csrf_token_rejected_when_empty);
  UNITY_END();
}

void loop() {}
