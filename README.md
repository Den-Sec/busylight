# BusyLight

> Open USB / WiFi status light, by D-Enterprise. ESP32-C6 firmware + Windows
> setup wizard. MIT licensed.

BusyLight is a tiny networked desk indicator: a red and a green LED that
broadcast whether you are **available**, **busy**, **in a call**, or **away**
to anyone walking past your desk. A small web UI lets you flip the state from
your phone or laptop; a PIN protects the device on the LAN.

## Features

- ESP32-C6 firmware with five LED states (AVAILABLE / BUSY / IN_CALL / AWAY / WIFI_ERROR).
- Web UI over `http://busylight-XXXX.local` after WiFi is configured.
- USB serial provisioning via the included Windows setup wizard.
- AP captive portal fallback if the WiFi credentials become invalid.
- OTA firmware updates from the web UI.
- PBKDF2 PIN hashing, CSRF protection, rate-limited login, multi-session.

## Hardware bill of materials

| Item                     | Quantity | Notes                              |
| ------------------------ | -------- | ---------------------------------- |
| ESP32-C6-DevKitC-1       | 1        | Native USB CDC, RISC-V             |
| 5 mm LED red             | 1        | Wired to GPIO 4                    |
| 5 mm LED green           | 1        | Wired to GPIO 5                    |
| Resistor 220 ohm 1/4 W   | 2        | Series with each LED               |
| USB-C cable              | 1        | For power and provisioning         |
| Mini breadboard          | 1        | Optional, for the kit assembly     |

### Wiring

```
ESP32-C6 GPIO 4 -----[ 220 ohm ]----+-->|---- GND   (red LED)
ESP32-C6 GPIO 5 -----[ 220 ohm ]----+-->|---- GND   (green LED)
ESP32-C6 5V/USB ---- USB-C ---- host PC
```

GPIO pins are software-defined and can be moved by editing
`firmware/src/main.cpp` (the `kRedPin` / `kGreenPin` constants).

## Quick start

1. **Flash the firmware.** Plug the ESP32-C6 over USB, then from `firmware/`:
   ```powershell
   pio run -t upload
   pio run -t uploadfs   # uploads the embedded web UI
   ```
2. **Run the wizard.** Download `BusyLightSetup.exe` from the latest GitHub
   release, run it, pick the COM port for the BusyLight (auto-detected by USB
   VID), type your WiFi SSID + password + a 4-8 digit PIN.
3. **Open the device.** When the wizard reports success, open
   `http://busylight-XXXX.local` in any browser on the same LAN. Log in with
   your PIN, then click any state.

If `.local` does not resolve on your network, the wizard prints the IP
address as a fallback URL.

## LED states

| State        | Pattern                                  |
| ------------ | ---------------------------------------- |
| AVAILABLE    | Green solid                              |
| BUSY         | Red solid                                |
| IN_CALL      | Red blink, 250 ms                        |
| AWAY         | Green blink, 900 ms                      |
| WIFI_ERROR   | Red/green alternating, 400 ms            |
| AP portal    | Red/green alternating, 200 ms (faster)   |

## Security model

- The PIN is hashed with PBKDF2-HMAC-SHA256 (10 000 iterations, 16-byte
  per-device salt) and stored in NVS.
- Sessions are bound to a `BLSESS` HttpOnly cookie. A separate `BLCSRF`
  cookie is used for double-submit CSRF protection on every mutating
  endpoint.
- The login endpoint rate-limits to 5 failed attempts per minute, with a
  60-second lockout afterward.
- BusyLight assumes a trusted LAN. There is no TLS yet, so do not deploy on
  shared / hostile WiFi. See [SECURITY.md](SECURITY.md) for the full threat
  model.

## Troubleshooting

- **Wizard cannot find COM port.** Make sure the cable carries data (not
  only power), and that no other tool (Arduino IDE serial monitor, esptool)
  is holding the port open.
- **`busylight-XXXX.local` does not resolve.** Most Windows installs need
  Bonjour or the Apple `mDNSResponder` service. As a workaround, look up the
  device IP in your router's DHCP list and browse to `http://<ip>`.
- **WiFi error after a router change.** Wait three minutes; the device
  drops into AP mode under the SSID `BusyLight-XXXX-Setup`. Connect to it
  with any phone/laptop and open `http://192.168.4.1` to reconfigure.
- **Forgotten PIN.** Run the wizard's "Factory reset" button, or send
  `{"cmd":"factory_reset","confirm":"YES"}` over the serial port at
  115200 bps.

## Build from source

- Firmware (PlatformIO 6+, RISC-V toolchain): see [firmware/README.md](firmware/README.md).
- Windows wizard (Python 3.10+): see [windows_setup/README.md](windows_setup/README.md).

## Contributing

Pull requests welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and
keep `pio test` and `pytest` green.

## License

[MIT](LICENSE). Hardware kit designs and 3D-printable enclosures (when
available) are also under MIT unless noted otherwise.
