$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
  throw "Python venv executable not found: $PythonExe"
}

& $PythonExe -m pip install -r requirements.txt | Out-Null

$env:PYTHONPATH = (Join-Path $Root "src")
$logsDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$env:BUSYLIGHT_DEBUG_LOG = Join-Path $logsDir ("setup-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

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

Write-Host "BusyLight Setup Wizard starting..."
Write-Host "Debug log: $env:BUSYLIGHT_DEBUG_LOG"
if ($env:TCL_LIBRARY -and $env:TK_LIBRARY) {
  Write-Host "TCL: $env:TCL_LIBRARY"
  Write-Host "TK:  $env:TK_LIBRARY"
}

& $PythonExe -m busylight_setup.main
