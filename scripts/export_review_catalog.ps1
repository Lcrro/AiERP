$ErrorActionPreference = "Stop"
$target = Join-Path $PSScriptRoot "material_master\export_review_catalog.ps1"
& $target @args
exit $LASTEXITCODE
