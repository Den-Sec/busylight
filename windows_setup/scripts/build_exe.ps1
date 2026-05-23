$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

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

& .\.venv\Scripts\pyinstaller.exe --onefile --noconsole --name BusyLightSetup src\busylight_setup\main.py

Write-Host "Built executable in dist\\BusyLightSetup.exe"
