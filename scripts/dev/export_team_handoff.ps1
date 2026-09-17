param(
    [Parameter(Mandatory = $true)][string]$V4Workbook,
    [string]$OutputRoot = "",
    [switch]$IncludeReferenceDatabase
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not (Test-Path -LiteralPath $V4Workbook -PathType Leaf)) {
    throw "V4 workbook does not exist: $V4Workbook"
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot "outputs\team-handoff"
}
$stamp = [DateTimeOffset]::Now.ToString("yyyyMMdd-HHmmss")
$bundleRoot = Join-Path $OutputRoot "nexterp-handoff-$stamp"
$payloadRoot = Join-Path $bundleRoot "payload"
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

$sources = @(
    @{ Source = $V4Workbook; Target = "source\classification-v4-source.xlsx" },
    @{ Source = (Join-Path $repoRoot "data\material_master\chatgpt_classification_v4"); Target = "data\chatgpt_classification_v4" },
    @{ Source = (Join-Path $repoRoot "data\material_master\release_v1_1"); Target = "data\release_v1_1" },
    @{ Source = (Join-Path $repoRoot "docs\reference\material-classification-v4-erpnext.md"); Target = "docs\material-classification-v4-erpnext.md" },
    @{ Source = (Join-Path $repoRoot "docs\operations\team-handoff.md"); Target = "docs\team-handoff.md" }
)
if ($IncludeReferenceDatabase) {
    $sources += @{ Source = (Join-Path $repoRoot ".runtime\material-master\reference-catalog.sqlite3"); Target = "runtime\reference-catalog.sqlite3" }
}

foreach ($entry in $sources) {
    $sourcePath = [string]$entry["Source"]
    $targetPath = [string]$entry["Target"]
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Required handoff source is missing: $sourcePath"
    }
    $destination = Join-Path -Path $payloadRoot -ChildPath $targetPath
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    try {
        if (Test-Path -LiteralPath $sourcePath -PathType Container) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
            Get-ChildItem -LiteralPath $sourcePath -Force | Copy-Item -Destination $destination -Recurse -Force
        } else {
            Copy-Item -LiteralPath $sourcePath -Destination $destination -Force
        }
    } catch {
        throw "Unable to copy handoff source '$sourcePath' to '$destination': $($_.Exception.Message)"
    }
}

$secretRequirements = @"
# Credentials deliberately excluded

Transfer the following only through the team's approved password manager or encrypted channel:

- .env values required by the selected runtime
- .secrets/erpnext-material-test/site-secrets.json
- .secrets/erpnext-material-test/user-api-credentials.json
- .secrets/erpnext-material-classification-v4/site-secrets.json
- .secrets/erpnext-material-classification-v4/user-api-credentials.json
- DeepSeek/OpenClaw tokens, if the AI workbench is enabled

No credential, ERPNext database backup, runtime session or log is present in this bundle.
The two material Sites are reproducible with scripts/dev/team_handoff_bootstrap.ps1.
"@
$secretRequirements | Set-Content -LiteralPath (Join-Path $bundleRoot "SECRET-TRANSFER-CHECKLIST.md") -Encoding utf8

$bundlePrefix = $bundleRoot.TrimEnd('\') + '\'
$manifest = Get-ChildItem -LiteralPath $bundleRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($bundlePrefix.Length).Replace('\', '/')
        size = $_.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    }
}
$manifestPayload = [ordered]@{
    generated_at = [DateTimeOffset]::Now.ToString("o")
    git_head = (& git -C $repoRoot rev-parse HEAD).Trim()
    contains_secrets = $false
    files = @($manifest)
}
$manifestPayload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $bundleRoot "manifest.json") -Encoding utf8

$archivePath = "$bundleRoot.zip"
Compress-Archive -LiteralPath $bundleRoot -DestinationPath $archivePath -Force
Write-Output ([ordered]@{
    bundle = $bundleRoot
    archive = $archivePath
    file_count = @($manifest).Count
    contains_secrets = $false
} | ConvertTo-Json)
