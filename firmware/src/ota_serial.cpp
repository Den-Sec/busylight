#include "ota_serial.h"

#include <Update.h>
#include <mbedtls/pk.h>
#include <mbedtls/sha256.h>

#include "signing_pubkey.h"

namespace {

constexpr size_t kOtaMinBytes = 100UL * 1024UL;
constexpr size_t kOtaSignatureBytes = 256;  // RSA-2048

enum class Phase : uint8_t {
  Idle,
  AwaitingSignature,
  Streaming,
};

struct State {
  Phase phase = Phase::Idle;
  uint32_t totalSize = 0;
  uint32_t bytesReceived = 0;
  uint8_t signature[kOtaSignatureBytes] = {0};
  size_t signatureBytesGot = 0;
  mbedtls_sha256_context shaCtx;
  bool shaInited = false;
};

State g_state;

void resetState_() {
  if (g_state.shaInited) {
    mbedtls_sha256_free(&g_state.shaCtx);
    g_state.shaInited = false;
  }
  g_state.phase = Phase::Idle;
  g_state.totalSize = 0;
  g_state.bytesReceived = 0;
  g_state.signatureBytesGot = 0;
}

}  // namespace

namespace ota_serial {

void reset() {
  if (g_state.phase != Phase::Idle) {
    Update.abort();
  }
  resetState_();
}

bool isActive() {
  return g_state.phase != Phase::Idle;
}

bool isStreaming() {
  return g_state.phase == Phase::Streaming;
}

bool isAwaitingSignature() {
  return g_state.phase == Phase::AwaitingSignature;
}

uint32_t bytesRemaining() {
  if (g_state.phase != Phase::Streaming) return 0;
  if (g_state.bytesReceived >= g_state.totalSize) return 0;
  return g_state.totalSize - g_state.bytesReceived;
}

uint32_t totalSize() { return g_state.totalSize; }
uint32_t bytesReceived() { return g_state.bytesReceived; }

uint32_t signatureBytesRemaining() {
  if (g_state.phase != Phase::AwaitingSignature) return 0;
  return kOtaSignatureBytes - g_state.signatureBytesGot;
}

bool begin(uint32_t size, String& errorOut) {
  // Always start clean — any leftover state from a previous failure
  // would taint the SHA context.
  reset();

  if (size < kOtaMinBytes) {
    errorOut = "image_too_small";
    return false;
  }

  mbedtls_sha256_init(&g_state.shaCtx);
  mbedtls_sha256_starts(&g_state.shaCtx, 0);
  g_state.shaInited = true;

  if (!Update.begin(size)) {
    resetState_();
    errorOut = "update_begin_failed";
    return false;
  }

  g_state.totalSize = size;
  g_state.bytesReceived = 0;
  g_state.signatureBytesGot = 0;
  g_state.phase = Phase::AwaitingSignature;
  return true;
}

size_t writeSignatureChunk(const uint8_t* buf, size_t len, String& errorOut) {
  if (g_state.phase != Phase::AwaitingSignature) {
    errorOut = "not_awaiting_sig";
    return 0;
  }
  size_t remaining = kOtaSignatureBytes - g_state.signatureBytesGot;
  size_t toCopy = len > remaining ? remaining : len;
  memcpy(g_state.signature + g_state.signatureBytesGot, buf, toCopy);
  g_state.signatureBytesGot += toCopy;
  if (g_state.signatureBytesGot == kOtaSignatureBytes) {
    g_state.phase = Phase::Streaming;
  }
  return toCopy;
}

size_t writeChunk(const uint8_t* buf, size_t len, String& errorOut) {
  if (g_state.phase != Phase::Streaming) {
    errorOut = "not_streaming";
    return 0;
  }
  if (len == 0) return 0;

  uint32_t remaining = bytesRemaining();
  if (remaining == 0) {
    errorOut = "overrun";
    return 0;
  }
  size_t toWrite = len > remaining ? remaining : len;

  if (Update.write(const_cast<uint8_t*>(buf), toWrite) != toWrite) {
    Update.abort();
    resetState_();
    errorOut = "write_failed";
    return 0;
  }
  mbedtls_sha256_update(&g_state.shaCtx, buf, toWrite);
  g_state.bytesReceived += toWrite;
  return toWrite;
}

bool finalize(String& errorOut) {
  if (g_state.phase != Phase::Streaming) {
    errorOut = "not_streaming";
    return false;
  }
  if (g_state.bytesReceived != g_state.totalSize) {
    Update.abort();
    resetState_();
    errorOut = "size_mismatch";
    return false;
  }
  if (!g_state.shaInited) {
    Update.abort();
    resetState_();
    errorOut = "hash_state_lost";
    return false;
  }

  uint8_t digest[32] = {0};
  mbedtls_sha256_finish(&g_state.shaCtx, digest);

  mbedtls_pk_context pk;
  mbedtls_pk_init(&pk);
  int rcPk = mbedtls_pk_parse_public_key(
      &pk, kSigningPublicKeyDer, kSigningPublicKeyDerLen);
  int rcVerify = -1;
  if (rcPk == 0) {
    rcVerify = mbedtls_pk_verify(
        &pk, MBEDTLS_MD_SHA256,
        digest, sizeof(digest),
        g_state.signature, kOtaSignatureBytes);
  }
  mbedtls_pk_free(&pk);

  if (rcPk != 0) {
    Update.abort();
    resetState_();
    errorOut = "pubkey_parse_failed";
    return false;
  }
  if (rcVerify != 0) {
    // Surface the digest we computed over what was actually
    // received, so the host can compare it with the digest it
    // signed and tell whether the corruption happened on the wire.
    char hex[65];
    for (int i = 0; i < 32; i++) {
      snprintf(hex + i * 2, 3, "%02x", digest[i]);
    }
    hex[64] = 0;
    Update.abort();
    resetState_();
    errorOut = String("signature_invalid:received_sha=") + hex;
    return false;
  }

  if (!Update.end(true)) {
    resetState_();
    errorOut = "update_end_failed";
    return false;
  }
  resetState_();
  return true;
}

}  // namespace ota_serial
