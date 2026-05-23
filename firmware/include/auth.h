#pragma once

#include <Arduino.h>

#include <array>

// Authentication manager.
//
// - PIN storage: PBKDF2-HMAC-SHA256 with a per-device 16-byte random salt,
//   serialised as "pbkdf2$<iter>$<saltHex>$<hashHex>". Legacy bare SHA-256
//   hashes from v0.1.0 are also accepted and silently re-hashed on a
//   successful login (handled by the caller via `pinHash()`).
// - Sessions: up to `kMaxSessions` concurrent tokens, LRU eviction. Each
//   session also carries a CSRF token used by the double-submit cookie
//   pattern.
// - Rate limiting: 5 failed login attempts per minute trigger a 60-second
//   lockout window.

class AuthManager {
 public:
  static constexpr size_t kMaxSessions = 4;
  static constexpr unsigned long kSessionTtlMs = 8UL * 60UL * 60UL * 1000UL;
  static constexpr unsigned long kRateWindowMs = 60UL * 1000UL;
  static constexpr unsigned long kLockoutMs = 60UL * 1000UL;
  static constexpr unsigned int kMaxAttempts = 5;
  static constexpr uint32_t kPbkdf2Iterations = 10000;

  AuthManager();

  // Produces a "pbkdf2$10000$<saltHex>$<hashHex>" string. Salt is random.
  static String hashPin(const String& pin);

  // Verifies plainPin against a stored hash (either PBKDF2 or legacy SHA-256).
  static bool verifyPin(const String& storedHash, const String& plainPin);

  // True if storedHash is the v0.1.0 bare SHA-256 hex.
  static bool isLegacyFormat(const String& storedHash);

  void setPinHash(const String& pinHash);
  String pinHash() const { return pinHash_; }

  // On success populates outSessionToken + outCsrfToken with 32-hex-char
  // tokens, allocates a session slot (evicting the oldest if needed), and
  // returns true. Failures count against the rate limiter.
  bool login(const String& pin,
             String& outSessionToken,
             String& outCsrfToken,
             unsigned long nowMs);

  bool isSessionValid(const String& sessionToken, unsigned long nowMs);
  bool isCsrfValid(const String& sessionToken, const String& csrfToken);
  String csrfTokenFor(const String& sessionToken) const;
  bool logout(const String& sessionToken);
  bool isLockedOut(unsigned long nowMs) const;

 private:
  struct Session {
    String token;
    String csrfToken;
    unsigned long expiresAt = 0;
    unsigned long lastUsedMs = 0;
    bool inUse = false;
  };

  String pinHash_;
  std::array<Session, kMaxSessions> sessions_;
  unsigned long lockoutUntilMs_;
  unsigned int failedCount_;
  unsigned long windowStartMs_;

  static String randomHex(size_t numBytes);
  static String bytesToHex(const uint8_t* data, size_t len);
  static bool hexToBytes(const String& hex, uint8_t* out, size_t outLen);

  Session* findSession(const String& sessionToken);
  Session* allocateSession(unsigned long nowMs);
};
