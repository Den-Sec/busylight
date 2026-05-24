// OTA over USB serial — same signed-image guarantees as the HTTP OTA
// route, but driven by a stream-based protocol that doesn't need
// Wi-Fi.
//
// Protocol (one BusyLight, one host):
//   1. Host sends JSON: {"cmd":"ota_begin","size":N}
//   2. Firmware replies {"ok":true,"event":"ota_awaiting_sig"} and
//      enters "expect 256 bytes of signature" mode.
//   3. Host writes exactly 256 raw bytes — the RSA-PKCS#1 v1.5
//      signature over SHA-256(image). Sending the signature outside
//      the JSON keeps the JSON line short enough to survive the
//      Arduino USB-CDC RX buffer (which is around 256 B on ESP32-C6).
//   4. Firmware replies {"ok":true,"event":"ota_ready"} and enters
//      "image streaming" mode.
//   5. Host writes exactly N raw bytes. The firmware streams them
//      straight into the OTA partition and updates a running SHA-256.
//   6. After N bytes, the firmware verifies signature, calls
//      Update.end(true), responds {"ok":true,"event":"ota_complete"}
//      (or an error), and reboots.
//
// All state is kept in a single struct so the loop can poll it from
// main.cpp without exposing internals.

#pragma once

#include <Arduino.h>

namespace ota_serial {

// Resets internal state and aborts any half-finished Update session.
// Always safe to call.
void reset();

// Returns true whenever an OTA session is in progress (signature
// collection OR image streaming). Other firmware code should use
// this to suppress async beacons while OTA is active — every byte
// added to the TX ring eats into the budget for the final
// `ota_complete` ack the host needs.
bool isActive();

// Returns true while the firmware is in "image streaming" mode and
// the caller should pipe Serial bytes straight into `writeChunk`
// instead of parsing them as JSON.
bool isStreaming();

// Returns true while the firmware is in "expect 256 bytes of
// signature" mode. The caller pipes raw Serial bytes through
// `writeSignatureChunk` until 256 bytes have been collected.
bool isAwaitingSignature();

// Bytes still expected before signature verification kicks in.
uint32_t bytesRemaining();

// Total image size declared by the host on ota_begin, and bytes
// successfully written so far. Useful for diagnostic progress events.
uint32_t totalSize();
uint32_t bytesReceived();

// Bytes of signature still expected.
uint32_t signatureBytesRemaining();

// Parse + apply an `ota_begin` command. Returns true on success and
// fills `errorOut` on failure (e.g. image too small, Update.begin()
// failed). Does NOT enter streaming mode yet — wait for the
// signature first.
bool begin(uint32_t size, String& errorOut);

// Feed signature bytes. Returns the number of bytes accepted. When
// the signature is complete the next `isStreaming()` call will
// return true so the caller can switch to image streaming.
size_t writeSignatureChunk(const uint8_t* buf, size_t len, String& errorOut);

// Feed raw image bytes into the active OTA session. Returns the
// number of bytes accepted (== `len` on success, 0 on error). On
// error, the session is aborted and `errorOut` is filled.
size_t writeChunk(const uint8_t* buf, size_t len, String& errorOut);

// Verifies the running SHA-256 against the stored signature and
// commits the new image. Returns true on success. Caller is
// responsible for emitting the JSON response and rebooting.
bool finalize(String& errorOut);

}  // namespace ota_serial
