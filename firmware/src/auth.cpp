#include "auth.h"

#include <mbedtls/pkcs5.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>

#include <esp_random.h>

namespace {

constexpr size_t kSaltBytes = 16;
constexpr size_t kHashBytes = 32;

}  // namespace

AuthManager::AuthManager()
    : lockoutUntilMs_(0), failedCount_(0), windowStartMs_(0) {}

// ---------- PIN hashing ----------

String AuthManager::hashPin(const String& pin) {
  uint8_t salt[kSaltBytes];
  for (size_t i = 0; i < kSaltBytes; i++) {
    salt[i] = static_cast<uint8_t>(esp_random() & 0xFF);
  }

  uint8_t out[kHashBytes] = {0};
  mbedtls_pkcs5_pbkdf2_hmac_ext(
      MBEDTLS_MD_SHA256,
      reinterpret_cast<const unsigned char*>(pin.c_str()),
      pin.length(),
      salt,
      kSaltBytes,
      kPbkdf2Iterations,
      kHashBytes,
      out);

  String result;
  result.reserve(7 + 6 + 1 + kSaltBytes * 2 + 1 + kHashBytes * 2);
  result = "pbkdf2$";
  result += String(kPbkdf2Iterations);
  result += '$';
  result += bytesToHex(salt, kSaltBytes);
  result += '$';
  result += bytesToHex(out, kHashBytes);
  return result;
}

bool AuthManager::isLegacyFormat(const String& storedHash) {
  if (storedHash.length() != 64) return false;
  for (size_t i = 0; i < storedHash.length(); i++) {
    char c = storedHash[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
          (c >= 'A' && c <= 'F'))) {
      return false;
    }
  }
  return true;
}

bool AuthManager::verifyPin(const String& storedHash, const String& plainPin) {
  if (storedHash.length() == 0) return false;

  // Legacy SHA-256 hex (v0.1.0). Constant-time-ish comparison.
  if (isLegacyFormat(storedHash)) {
    uint8_t digest[kHashBytes] = {0};
    mbedtls_sha256_context sctx;
    mbedtls_sha256_init(&sctx);
    mbedtls_sha256_starts(&sctx, 0);
    mbedtls_sha256_update(
        &sctx, reinterpret_cast<const unsigned char*>(plainPin.c_str()),
        plainPin.length());
    mbedtls_sha256_finish(&sctx, digest);
    mbedtls_sha256_free(&sctx);

    String hex = bytesToHex(digest, kHashBytes);
    if (hex.length() != storedHash.length()) return false;
    uint8_t diff = 0;
    for (size_t i = 0; i < hex.length(); i++) {
      diff |= static_cast<uint8_t>(hex[i]) ^
              static_cast<uint8_t>(storedHash[i]);
    }
    return diff == 0;
  }

  // pbkdf2$<iter>$<saltHex>$<hashHex>
  if (!storedHash.startsWith("pbkdf2$")) return false;

  int p1 = storedHash.indexOf('$', 7);
  if (p1 < 0) return false;
  int p2 = storedHash.indexOf('$', p1 + 1);
  if (p2 < 0) return false;
  int p3 = storedHash.indexOf('$', p2 + 1);
  // p3 may be -1 (no trailing fields), that is fine.

  String iterStr = storedHash.substring(7, p1);
  String saltHex = storedHash.substring(p1 + 1, p2);
  String hashHex = (p3 < 0) ? storedHash.substring(p2 + 1)
                            : storedHash.substring(p2 + 1, p3);

  long iter = iterStr.toInt();
  if (iter <= 0 || iter > 1000000L) return false;
  if (saltHex.length() != kSaltBytes * 2) return false;
  if (hashHex.length() != kHashBytes * 2) return false;

  uint8_t salt[kSaltBytes] = {0};
  if (!hexToBytes(saltHex, salt, kSaltBytes)) return false;

  uint8_t out[kHashBytes] = {0};
  mbedtls_pkcs5_pbkdf2_hmac_ext(
      MBEDTLS_MD_SHA256,
      reinterpret_cast<const unsigned char*>(plainPin.c_str()),
      plainPin.length(),
      salt,
      kSaltBytes,
      static_cast<uint32_t>(iter),
      kHashBytes,
      out);

  String computedHex = bytesToHex(out, kHashBytes);
  if (computedHex.length() != hashHex.length()) return false;
  uint8_t diff = 0;
  for (size_t i = 0; i < computedHex.length(); i++) {
    diff |= static_cast<uint8_t>(computedHex[i]) ^
            static_cast<uint8_t>(hashHex[i]);
  }
  return diff == 0;
}

void AuthManager::setPinHash(const String& pinHash) { pinHash_ = pinHash; }

// ---------- Rate limiter / lockout ----------

bool AuthManager::isLockedOut(unsigned long nowMs) const {
  return lockoutUntilMs_ != 0 && nowMs < lockoutUntilMs_;
}

// ---------- Sessions ----------

AuthManager::Session* AuthManager::findSession(const String& sessionToken) {
  if (sessionToken.length() == 0) return nullptr;
  for (auto& s : sessions_) {
    if (s.inUse && s.token == sessionToken) return &s;
  }
  return nullptr;
}

AuthManager::Session* AuthManager::allocateSession(unsigned long nowMs) {
  Session* oldest = nullptr;
  for (auto& s : sessions_) {
    if (!s.inUse) {
      return &s;
    }
    if (oldest == nullptr || s.lastUsedMs < oldest->lastUsedMs) {
      oldest = &s;
    }
  }
  // All slots full — evict LRU.
  if (oldest) {
    oldest->token = "";
    oldest->csrfToken = "";
    oldest->inUse = false;
  }
  (void)nowMs;
  return oldest;
}

bool AuthManager::login(const String& pin,
                        String& outSessionToken,
                        String& outCsrfToken,
                        unsigned long nowMs) {
  if (isLockedOut(nowMs)) {
    return false;
  }

  if (windowStartMs_ == 0 || (nowMs - windowStartMs_) > kRateWindowMs) {
    windowStartMs_ = nowMs;
    failedCount_ = 0;
  }

  if (!verifyPin(pinHash_, pin)) {
    failedCount_++;
    if (failedCount_ >= kMaxAttempts) {
      lockoutUntilMs_ = nowMs + kLockoutMs;
      failedCount_ = 0;
      windowStartMs_ = nowMs;
    }
    return false;
  }

  failedCount_ = 0;
  windowStartMs_ = nowMs;
  lockoutUntilMs_ = 0;

  Session* slot = allocateSession(nowMs);
  if (slot == nullptr) {
    return false;  // should not happen
  }

  slot->token = randomHex(16);  // 32 hex chars
  slot->csrfToken = randomHex(16);
  slot->expiresAt = nowMs + kSessionTtlMs;
  slot->lastUsedMs = nowMs;
  slot->inUse = true;

  outSessionToken = slot->token;
  outCsrfToken = slot->csrfToken;
  return true;
}

bool AuthManager::isSessionValid(const String& sessionToken,
                                 unsigned long nowMs) {
  Session* s = findSession(sessionToken);
  if (!s) return false;
  if (nowMs >= s->expiresAt) {
    s->inUse = false;
    s->token = "";
    s->csrfToken = "";
    return false;
  }
  s->lastUsedMs = nowMs;
  return true;
}

bool AuthManager::isCsrfValid(const String& sessionToken,
                              const String& csrfToken) {
  if (csrfToken.length() == 0) return false;
  Session* s = findSession(sessionToken);
  if (!s) return false;
  if (s->csrfToken.length() != csrfToken.length()) return false;
  uint8_t diff = 0;
  for (size_t i = 0; i < csrfToken.length(); i++) {
    diff |= static_cast<uint8_t>(s->csrfToken[i]) ^
            static_cast<uint8_t>(csrfToken[i]);
  }
  return diff == 0;
}

String AuthManager::csrfTokenFor(const String& sessionToken) const {
  for (const auto& s : sessions_) {
    if (s.inUse && s.token == sessionToken) {
      return s.csrfToken;
    }
  }
  return "";
}

bool AuthManager::logout(const String& sessionToken) {
  Session* s = findSession(sessionToken);
  if (!s) return false;
  s->inUse = false;
  s->token = "";
  s->csrfToken = "";
  return true;
}

// ---------- Hex helpers ----------

String AuthManager::randomHex(size_t numBytes) {
  String out;
  out.reserve(numBytes * 2);
  static const char hex[] = "0123456789abcdef";
  for (size_t i = 0; i < numBytes; i++) {
    uint8_t b = static_cast<uint8_t>(esp_random() & 0xFF);
    out += hex[(b >> 4) & 0x0F];
    out += hex[b & 0x0F];
  }
  return out;
}

String AuthManager::bytesToHex(const uint8_t* data, size_t len) {
  String out;
  out.reserve(len * 2);
  static const char hex[] = "0123456789abcdef";
  for (size_t i = 0; i < len; i++) {
    out += hex[(data[i] >> 4) & 0x0F];
    out += hex[data[i] & 0x0F];
  }
  return out;
}

bool AuthManager::hexToBytes(const String& hex, uint8_t* out, size_t outLen) {
  if (hex.length() != outLen * 2) return false;
  auto nibble = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  };
  for (size_t i = 0; i < outLen; i++) {
    int hi = nibble(hex[i * 2]);
    int lo = nibble(hex[i * 2 + 1]);
    if (hi < 0 || lo < 0) return false;
    out[i] = static_cast<uint8_t>((hi << 4) | lo);
  }
  return true;
}
