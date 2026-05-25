# pip and pyinstaller both write progress to stderr; with the default
# $ErrorActionPreference="Stop" PowerShell aborts the script before the
# build step ever runs. Keep it on "Continue" for the whole script and
# check exit codes / output paths explicitly at the end.
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

if (-not $env:TCL_LIBRARY -or -not $env:TK_LIBRARY) {
  $candidates = @()
  $pyLocal = Join-Path $env:LOCALAPPDATA "Programs\Python"
  if (Test-Path $pyLocal) {
    $candidates += Get-ChildItem $pyLocal -Directory -Filter "Python3*" | Select-Object -ExpandProperty FullName
  }
  $candidates += "C:\Python313"
  $candidates += "C:\Python312"
  $candidates += "C:\Python311"

  foreach ($base in $candidates) {
    $tcl = Join-Path $base "tcl\tcl8.6"
    $tk = Join-Path $base "tcl\tk8.6"
    if ((Test-Path $tcl) -and (Test-Path $tk)) {
      $env:TCL_LIBRARY = $tcl
      $env:TK_LIBRARY = $tk
      break
    }
  }
}

if ($env:TCL_LIBRARY -and $env:TK_LIBRARY) {
  Write-Host "Using TCL_LIBRARY=$env:TCL_LIBRARY"
  Write-Host "Using TK_LIBRARY=$env:TK_LIBRARY"
}

& .\.venv\Scripts\pyinstaller.exe `
  --onefile `
  --noconsole `
  --uac-admin `
  --name BusyLightSetup `
  --collect-data customtkinter `
  src\busylight_setup\main.py 2>&1 | ForEach-Object { "$_" }

if (-not (Test-Path "dist\BusyLightSetup.exe")) {
  throw "PyInstaller did not produce dist\BusyLightSetup.exe"
}

Write-Host "Built executable in dist\BusyLightSetup.exe"
