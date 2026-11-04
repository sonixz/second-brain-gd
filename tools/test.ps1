# Runs the automated tests on Windows (PowerShell).
#   .\tools\test.ps1                      # Python tests only
#   .\tools\test.ps1 -Godot C:\path\Godot_v4.7.2-stable_win64_console.exe
param([string]$Python = "python", [string]$Godot = "")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "== Python tests"
& $Python -m unittest discover -s tests/python -t . -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Godot -eq "") { Write-Host "== Godot path not given: skipping Godot tests"; exit 0 }
Write-Host "== Godot end-to-end (headless, temporary data folder)"
& $Godot --headless --path . --import | Out-Null
$tmp = Join-Path $env:LOCALAPPDATA ("SecondBrainGD-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$env:SBGD_HOME = $tmp
$env:SBGD_PORT = "18765"
$env:SBGD_OCR = "fake"
try {
  & $Godot --headless --path . --script res://tests/godot/test_runner.gd
  $code = $LASTEXITCODE
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  Remove-Item Env:SBGD_HOME, Env:SBGD_PORT, Env:SBGD_OCR
}
exit $code
