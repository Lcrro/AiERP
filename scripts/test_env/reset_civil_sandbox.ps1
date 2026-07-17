param(
    [Parameter(Mandatory = $true)]
    [string]$Confirm,
    [string]$Site = "fac.localhost",
    [string]$Distribution = "Ubuntu",
    [string]$BenchPath = "/home/administrator/frappe-bench"
)

$ErrorActionPreference = "Stop"
$requiredConfirmation = "RESET-CIVIL-SANDBOX"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$baselineDir = Join-Path $repoRoot ".secrets\civil-baselines\golden"
$manifestPath = Join-Path $baselineDir "manifest.json"
$wslBackupDir = "\\wsl.localhost\$Distribution\home\administrator\frappe-bench\sites\$Site\private\backups"
$sessionDir = Join-Path $repoRoot "data\runtime\sessions"

if ($Confirm -ne $requiredConfirmation) {
    throw "Confirmation must be exactly: $requiredConfirmation"
}
if ($Site -ne "fac.localhost") {
    throw "Refusing to reset non-test site: $Site"
}
if (-not (Test-Path $manifestPath)) {
    throw "Golden baseline not found. Run scripts\test_env\create_civil_baseline.ps1 first."
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.site -ne $Site) {
    throw "Baseline site '$($manifest.site)' does not match requested site '$Site'."
}

function Invoke-Bench {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & wsl -d $Distribution --cd $BenchPath /home/administrator/.local/bin/bench @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "bench command failed: $($Arguments -join ' ')"
    }
}

$stagedNames = @{}
foreach ($name in @($manifest.database, $manifest.public_files, $manifest.private_files)) {
    $source = Join-Path $baselineDir $name
    if (-not (Test-Path $source)) {
        throw "Baseline artifact missing: $source"
    }
    $expectedHash = [string]$manifest.checksums.$name
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
    if (-not $expectedHash -or $actualHash -ne $expectedHash) {
        throw "Baseline checksum mismatch: $name"
    }
}
foreach ($name in @($manifest.database, $manifest.public_files, $manifest.private_files)) {
    $source = Join-Path $baselineDir $name
    $stagedName = "golden-reset-$name"
    $stagedNames[$name] = $stagedName
    Copy-Item -LiteralPath $source -Destination (Join-Path $wslBackupDir $stagedName) -Force
}

$linuxStage = "sites/$Site/private/backups"
$maintenanceEnabled = $false
try {
    Invoke-Bench --site $Site set-maintenance-mode on
    $maintenanceEnabled = $true
    $restoreScript = Join-Path $repoRoot "scripts\test_env\restore_civil_site.py"
    $wslRestoreScript = (& wsl -d $Distribution wslpath -a ($restoreScript -replace '\\', '/')).Trim()
    & wsl -d $Distribution --cd $BenchPath python3 $wslRestoreScript `
        --bench $BenchPath `
        --site $Site `
        --database "$linuxStage/$($stagedNames[$manifest.database])" `
        --public-files "$linuxStage/$($stagedNames[$manifest.public_files])" `
        --private-files "$linuxStage/$($stagedNames[$manifest.private_files])"
    if ($LASTEXITCODE -ne 0) {
        throw "Civil site restore helper failed."
    }
    Invoke-Bench --site $Site clear-cache
}
finally {
    foreach ($stagedName in $stagedNames.Values) {
        Remove-Item -LiteralPath (Join-Path $wslBackupDir $stagedName) -Force -ErrorAction SilentlyContinue
    }
    if ($maintenanceEnabled) {
        Invoke-Bench --site $Site set-maintenance-mode off
    }
}

if (Test-Path $sessionDir) {
    Get-ChildItem -LiteralPath $sessionDir -Filter "*.json" -File | Remove-Item -Force
}

$inventoryJson = Invoke-Bench --site $Site execute agent_bridge.test_env.inventory | Select-Object -Last 1
$inventory = $inventoryJson | ConvertFrom-Json
if ([int]$inventory.total -ne 0) {
    throw "Reset completed but verification found $($inventory.total) business documents."
}
$masterDataJson = Invoke-Bench --site $Site execute agent_bridge.test_env.master_data_inventory | Select-Object -Last 1
$masterData = $masterDataJson | ConvertFrom-Json
foreach ($property in $manifest.master_data.counts.PSObject.Properties) {
    if ([int]$masterData.counts.($property.Name) -ne [int]$property.Value) {
        throw "Master data verification failed for $($property.Name)."
    }
}

Write-Host "Civil sandbox restored to golden baseline."
Write-Host "ERPNext business documents: $($inventory.total)"
Write-Host "Master data fingerprint verified."
Write-Host "Workbench conversations cleared."
