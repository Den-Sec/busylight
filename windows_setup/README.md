# BusyLight Setup Wizard (Windows)

A single-file Tkinter GUI that provisions a fresh BusyLight over USB:
choose a COM port, type your WiFi SSID + password + a PIN, click
**Configure BusyLight**.

## End-user

Download `BusyLightSetup.exe` from the latest GitHub release and run it.
No installation needed. The first time you launch it, Windows SmartScreen
may warn that the publisher is unknown (the binary is currently not signed
with an EV certificate): pick **More info** -> **Run anyway**.

## Developer setup

```powershell
# from the windows_setup/ directory
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m busylight_setup.main
```

`scripts\run_wizard.ps1` automates the same thing and turns on a verbose
debug log (path printed at startup, under `windows_setup/logs/`). Use the
debug log when reporting a handshake issue.

## Build the installer

```powershell
.\scripts\build_exe.ps1
```

This regenerates `.venv` if missing, installs PyInstaller, ensures the
TCL/TK runtime is locatable, and produces `dist\BusyLightSetup.exe`
(about 12 MB). The PyInstaller `.spec` file is regenerated on every
build, so do not commit it.

## Tests

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/ --cov
```

Coverage targets: `serial_protocol.py` and `validation.py` >= 70 %.
`app.py` (Tk UI) is exercised by manual smoke tests, not unit tests.

## How the wizard talks to the device

1. Open the COM port at 115200 8N1, `dsrdtr=False`, `rtscts=False`.
2. Pre-assert `DTR=True` / `RTS=False` so the ESP32-C6 native USB CDC
   reports the host as "connected". Without this step the firmware never
   sees the first JSON line.
3. Wait up to 12 s for either a `{"event":"ready"}` beacon (sent by the
   firmware right after `Serial.begin`) or a `{"event":"pong"}` reply to
   the wizard's periodic ping.
4. Send `{"cmd":"set_config","ssid":...,"password":...,"pin":...}` and
   wait for `{"event":"config_saved"}` followed (optionally) by
   `{"event":"server_started","ip":"..."}`.
5. Show `http://busylight-XXXX.local` (and the IP if available) to the
   user.

The corresponding firmware code lives in `firmware/src/main.cpp`
(`handleSerialProvisioning`).

## Debug log

Set `BUSYLIGHT_DEBUG_LOG` to an absolute file path before running the
wizard to capture every handshake step:

```powershell
$env:BUSYLIGHT_DEBUG_LOG = "$pwd\logs\setup-$(Get-Date -Format yyyyMMdd-HHmmss).log"
.\.venv\Scripts\python.exe -m busylight_setup.main
```

`scripts\run_wizard.ps1` sets it automatically.

## Troubleshooting

- **Wizard hangs on "Handshaking with BusyLight"**: most often a host
  application (Arduino IDE, Termite, esptool) is holding the COM port.
  Close it and retry. If the issue persists with a fresh device, factory
  reset over USB by sending `{"cmd":"factory_reset","confirm":"YES"}\n`
  from any serial terminal.
- **TCL/TK not found** when running from a vanilla Python install: the
  `run_wizard.ps1` and `build_exe.ps1` scripts try several locations under
  `%LOCALAPPDATA%\Programs\Python` and `C:\Python3xx`. If yours is
  elsewhere, set `TCL_LIBRARY` and `TK_LIBRARY` manually.
- **SmartScreen blocks the exe**: build is unsigned until v1.0. Use the
  bypass described in the end-user section, or build locally from source.
