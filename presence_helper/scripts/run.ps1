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

# Core has no runtime deps; this is essentially a no-op the second time.
& $PythonExe -m pip install -q -r requirements.txt | Out-Null

$env:PYTHONPATH = (Join-Path $Root "src")
& $PythonExe -m busylight_presence.main @args
