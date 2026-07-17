param(
    [string]$Site = "fac.localhost",
    [string]$Distribution = "Ubuntu",
    [string]$BenchPath = "/home/administrator/frappe-bench"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$baselineDir = Join-Path $repoRoot ".secrets\civil-baselines\golden"
$wslBackupDir = "\\wsl.localhost\$Distribution\home\administrator\frappe-bench\sites\$Site\private\backups"

if ($Site -ne "fac.localhost") {
    throw "Refusing to create a civil baseline for non-test site: $Site"
}

function Invoke-Bench {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & wsl -d $Distribution --cd $BenchPath /home/administrator/.local/bin/bench @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "bench command failed: $($Arguments -join ' ')"
    }
}

$inventoryJson = Invoke-Bench --site $Site execute agent_bridge.test_env.inventory | Select-Object -Last 1
$inventory = $inventoryJson | ConvertFrom-Json
if ([int]$inventory.total -ne 0) {
    throw "Refusing to create a golden baseline with $($inventory.total) business documents."
}
$masterDataJson = Invoke-Bench --site $Site execute agent_bridge.test_env.master_data_inventory | Select-Object -Last 1
$masterData = $masterDataJson | ConvertFrom-Json

Invoke-Bench --site $Site backup --with-files --compress
$database = Get-ChildItem $wslBackupDir -Filter "*-database.sql.gz" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $database) {
    throw "ERPNext backup did not create a database archive."
}
$prefix = $database.Name -replace "-database\.sql\.gz$", ""
$required = @(
    "$prefix-database.sql.gz",
    "$prefix-files.tgz",
    "$prefix-private-files.tgz",
    "$prefix-site_config_backup.json"
)

if (Test-Path $baselineDir) {
    Remove-Item -LiteralPath $baselineDir -Recurse -Force
}
New-Item -ItemType Directory -Path $baselineDir -Force | Out-Null
foreach ($name in $required) {
    $source = Join-Path $wslBackupDir $name
    if (-not (Test-Path $source)) {
        throw "Missing backup artifact: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $baselineDir $name) -Force
}
$checksums = [ordered]@{}
foreach ($name in $required) {
    $checksums[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $baselineDir $name)).Hash.ToLowerInvariant()
}

$manifest = [ordered]@{
    version = 1
    site = $Site
    created_at = (Get-Date).ToString("o")
    git_commit = (git -C $repoRoot rev-parse HEAD).Trim()
    database = "$prefix-database.sql.gz"
    public_files = "$prefix-files.tgz"
    private_files = "$prefix-private-files.tgz"
    site_config = "$prefix-site_config_backup.json"
    checksums = $checksums
    inventory = $inventory
    master_data = $masterData
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $baselineDir "manifest.json") -Encoding utf8

Write-Host "Civil golden baseline created: $baselineDir"
Write-Host "Business documents: $($inventory.total)"
Write-Host "Projects: $($masterData.counts.Project); employees: $($masterData.counts.Employee); items: $($masterData.counts.Item)"
