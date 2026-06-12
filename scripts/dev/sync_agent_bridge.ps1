param(
    [string]$BenchPath = "\\wsl.localhost\Ubuntu\home\administrator\frappe-bench",
    [string]$AppName = "agent_bridge"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$source = Join-Path $repoRoot "frappe_apps\$AppName\$AppName"
$target = Join-Path $BenchPath "apps\$AppName\$AppName"

if (-not (Test-Path $source)) {
    throw "Bridge source not found: $source"
}

if (-not (Test-Path $target)) {
    throw "WSL bridge target not found: $target"
}

Copy-Item -Path (Join-Path $source "api.py") -Destination (Join-Path $target "api.py") -Force
Write-Host "Synced $AppName api.py to $target"
