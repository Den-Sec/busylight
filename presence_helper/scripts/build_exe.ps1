$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt pyinstaller

# console=true so users can see the helper's logs in a terminal window.
# When we add the tray icon we'll flip this to noconsole and surface
# a log file instead.
& .\.venv\Scripts\pyinstaller.exe --onefile --name BusyLightPresence src\busylight_presence\main.py

Write-Host "Built dist\BusyLightPresence.exe"
