# pip and pyinstaller both emit progress on stderr. With the default
# $ErrorActionPreference="Stop" PowerShell aborts before PyInstaller
# ever runs. Keep "Continue" for the whole script and verify the
# resulting exe path at the end.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip 2>&1 | ForEach-Object { "$_" }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt pyinstaller 2>&1 | ForEach-Object { "$_" }

if (-not (Test-Path ".\.venv\Scripts\pyinstaller.exe")) {
  throw "pip install did not produce .venv\Scripts\pyinstaller.exe"
}

# --noconsole: the helper is a tray app, the user never needs a console
# window. Logs still go to stdout when launched from a terminal.
#
# Build via scripts\_entry.py (absolute imports) instead of pointing at
# busylight_presence/main.py directly — when PyInstaller --onefile runs
# a module file as __main__, relative imports (`from . import ...`)
# break. The entry shim sidesteps that by importing the package by
# name; --paths makes the package discoverable.
& .\.venv\Scripts\pyinstaller.exe `
  --onefile `
  --noconsole `
  --uac-admin `
  --name BusyLightPresence `
  --paths src `
  --add-data "src/busylight_presence/webui;busylight_presence/webui" `
  --collect-data pystray `
  --collect-data customtkinter `
  --collect-data webview `
  --collect-all esptool `
  --collect-submodules serial `
  scripts\_entry.py 2>&1 | ForEach-Object { "$_" }

if (-not (Test-Path "dist\BusyLightPresence.exe")) {
  throw "PyInstaller did not produce dist\BusyLightPresence.exe"
}

Write-Host ""
Write-Host "Built dist\BusyLightPresence.exe"
Write-Host ""
Write-Host "To auto-launch at login:"
Write-Host "  dist\BusyLightPresence.exe --install-startup"
