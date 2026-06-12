$ErrorActionPreference = "Stop"
$target = Join-Path $PSScriptRoot "dev\start_wsl_sandbox.ps1"
& $target @args
exit $LASTEXITCODE
