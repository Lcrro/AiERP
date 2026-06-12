$ErrorActionPreference = "Stop"
$target = Join-Path $PSScriptRoot "dev\sync_agent_bridge.ps1"
& $target @args
exit $LASTEXITCODE
