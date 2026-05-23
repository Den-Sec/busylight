# BusyLight Firmware

ESP32-C6 firmware, written in C++ for the Arduino framework via PlatformIO.

## Toolchain

- [PlatformIO Core](https://platformio.org/install/cli) 6.1+
- Python 3.10+ (PlatformIO bootstraps its own venv during the first build)
- Native USB CDC on the ESP32-C6 (no external USB-to-UART chip required)

On first build, PlatformIO will download:

- `platform-espressif32@5x.x.x` (pioarduino fork)
- `framework-arduinoespressif32@3.3.x`
- `toolchain-riscv32-esp@14.x` and `tool-riscv32-esp-elf-gdb`
- `tool-esptoolpy`, `tool-scons`

Expect about 500 MB of downloads the first time.

## Build / flash / monitor

```powershell
# from the firmware/ directory
pio run                  # compile
pio run -t upload        # flash app over USB
pio run -t uploadfs      # flash the LittleFS image (web UI assets)
pio device monitor       # open the JSON-line serial console
```

Specify the port explicitly if PlatformIO autodetect picks the wrong one:

```powershell
pio run -t upload --upload-port COM3
pio device monitor --port COM3
```

## Project layout

```
firmware/
  platformio.ini             - target board, build flags, deps
  src/
    main.cpp                 - setup/loop, WiFi state machine, serial provisioning
    api_server.{h,cpp}       - HTTP API + cookie auth glue
    auth.{h,cpp}             - PBKDF2 PIN, sessions, lockout
    config_store.{h,cpp}     - NVS-backed configuration (SSID, PIN hash, state)
    led_engine.{h,cpp}       - state-machine driving the two LEDs
    ap_portal.{h,cpp}        - captive portal fallback (added in 0.2)
  data/                      - LittleFS image: index.html, app.js, styles.css
  test/                      - Unity unit tests (auth, led, config, hostname)
```

## Serial provisioning protocol

The firmware emits a `ready` beacon on the USB CDC port as soon as the
host enumerates it:

```
{"ok":true,"event":"ready","fw":"0.2.0"}
```

The host wizard can also send `{"cmd":"ping"}` and the device will reply
with `{"event":"pong","ok":true}`.

Commands accepted on the serial line (one JSON object per line, ending in
`\n`):

| Command          | Payload                                       | Response                           |
| ---------------- | --------------------------------------------- | ---------------------------------- |
| `ping`           | -                                             | `{event:pong,ok:true}`             |
| `set_config`     | `{ssid, password, pin}`                       | `{event:config_saved,ok:true}` then reboot |
| `factory_reset`  | `{confirm:"YES"}` (guard against accidents)   | `{event:factory_reset_ok,ok:true}` then reboot |

## OTA update

After provisioning, an authenticated client can upload a new firmware
binary to `POST /api/firmware/update` (multipart, fields: `firmware` =
`.bin`, optional `md5`). The device verifies the size, writes the new image
to the inactive OTA slot, then reboots. Subsequent flashes alternate
between `app0` and `app1`.

## Tests

```powershell
pio test -e esp32c6dev   # on-device Unity tests
pio test -e native       # host-side tests (uses mock NVS / time)
```

CI runs both under `.github/workflows/firmware.yml`.

## Pin map

| Function | GPIO |
| -------- | ---- |
| Red LED  | 4    |
| Green LED| 5    |

If you change the pins, also update `kRedPin` / `kGreenPin` in `main.cpp`.

## Memory footprint reference (v0.2.0)

- RAM: about 46 KB used out of 320 KB (14%).
- Flash: about 1.12 MB used out of the 1.5 MB OTA slot (75%). Adding new
  features should stay under the slot size to keep OTA viable.
