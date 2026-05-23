$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt pyinstaller

# --noconsole: the helper is a tray app, the user never needs a console
# window. Logs still go to stdout when launched from a terminal.
& .\.venv\Scripts\pyinstaller.exe `
  --onefile `
  --noconsole `
  --name BusyLightPresence `
  --collect-data pystray `
  src\busylight_presence\main.py

Write-Host ""
Write-Host "Built dist\BusyLightPresence.exe"
Write-Host ""
Write-Host "To auto-launch at login:"
Write-Host "  dist\BusyLightPresence.exe --install-startup"
