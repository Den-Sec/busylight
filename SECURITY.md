# Security Policy

## Reporting a Vulnerability

If you believe you have found a security issue in BusyLight, please report it
privately to **info@securitixsolutions.com**. Do not open a public GitHub issue
for security reports.

You will receive an acknowledgement within 5 working days. A fix or mitigation
plan will follow within 30 working days for issues confirmed to be valid.

## Supported Versions

| Version | Status      |
| ------- | ----------- |
| 0.2.x   | Supported   |
| 0.1.x   | End of life |

Older firmware can be updated over USB or, starting with 0.2.0, over the
authenticated web OTA endpoint.

## Threat Model

BusyLight is designed for use on a trusted LAN. The current threat model
assumes:

- **Physical access is privileged.** Anyone with USB access to the device can
  reprovision it (factory reset + new WiFi/PIN). Flash encryption is not
  enabled by default; do not store secrets you would not write on a sticker
  applied to the device.
- **LAN is trusted enough for HTTP.** The web UI runs on plain HTTP. PINs and
  CSRF tokens travel in clear text over the local network. Do not deploy a
  BusyLight on a shared WiFi where you cannot trust other clients.
- **The PIN is the only secret protecting the API.** PINs are 4 to 8 digits,
  stored as PBKDF2-HMAC-SHA256 (10000 iterations, per-device 16-byte salt). A
  rate limiter blocks login attempts after 5 failures in one minute.
- **OTA updates are not signed.** Anyone authenticated with the PIN can flash
  arbitrary firmware over the network. Signed OTA is on the roadmap.

If your use case requires a stronger model (untrusted network, untrusted
physical access, signed firmware), please open a discussion before deploying.

## Hardening Recommendations

- Change the default PIN (`1234`) on first boot.
- Place the device on a dedicated VLAN if your home network mixes guests with
  trusted devices.
- Disable mDNS broadcasting if you only ever reach the device by IP.
- Run a factory reset before disposing of a device.
