param(
    [ValidateSet("bootstrap", "start", "stop", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

# This Site is deliberately isolated from material-test.localhost.  It is a
# classification-only sandbox for a user-provided workbook and has no
# transaction baseline or production credentials.
$siteName = "material-classification-v4.localhost"
$projectName = "nexterp-material-classification-v4"
$erpnextVersion = "v15.118.2"
$httpPort = 8004

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$sharedFrappeDockerRoot = Join-Path $repoRoot ".runtime\erpnext-material-test\frappe_docker"
$runtimeRoot = Join-Path $repoRoot ".runtime\erpnext-material-classification-v4"
$secretRoot = Join-Path $repoRoot ".secrets\erpnext-material-classification-v4"
$secretJsonPath = Join-Path $secretRoot "site-secrets.json"
$stackEnvPath = Join-Path $secretRoot "stack.env"

function New-SecureText {
    $bytes = [byte[]]::new(32)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Ensure-DockerReady {
    & docker version --format '{{.Server.Version}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not ready. Start Docker Desktop and retry." }
}

function Ensure-FrappeDocker {
    if (-not (Test-Path -LiteralPath (Join-Path $sharedFrappeDockerRoot ".git"))) {
        throw "Shared frappe_docker checkout is missing. Run material-test.localhost bootstrap first."
    }
}

function Ensure-Secrets {
    New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $secretJsonPath)) {
        [ordered]@{
            site = $siteName
            db_root_password = New-SecureText
            admin_password = New-SecureText
            generated_at = [DateTimeOffset]::Now.ToString("o")
        } | ConvertTo-Json | Set-Content -LiteralPath $secretJsonPath -Encoding utf8
    }
    $secrets = Get-Content -Raw -LiteralPath $secretJsonPath | ConvertFrom-Json
    if ($secrets.site -ne $siteName -or [string]::IsNullOrWhiteSpace([string]$secrets.admin_password)) {
        throw "Classification Site secret file is incomplete or belongs to another Site."
    }
    @(
        "ERPNEXT_VERSION=$erpnextVersion"
        "DB_PASSWORD=$($secrets.db_root_password)"
        "HTTP_PUBLISH_PORT=$httpPort"
        "FRAPPE_SITE_NAME_HEADER=$siteName"
        "PULL_POLICY=missing"
        "RESTART_POLICY=unless-stopped"
    ) | Set-Content -LiteralPath $stackEnvPath -Encoding utf8
    return $secrets
}

function Get-ComposePrefix {
    return @(
        "compose", "--project-name", $projectName, "--env-file", $stackEnvPath,
        "-f", (Join-Path $sharedFrappeDockerRoot "compose.yaml"),
        "-f", (Join-Path $sharedFrappeDockerRoot "overrides\compose.mariadb.yaml"),
        "-f", (Join-Path $sharedFrappeDockerRoot "overrides\compose.redis.yaml"),
        "-f", (Join-Path $sharedFrappeDockerRoot "overrides\compose.noproxy.yaml")
    )
}

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [switch]$AllowFailure)
    & docker @(Get-ComposePrefix) @Arguments
    if (-not $AllowFailure -and $LASTEXITCODE -ne 0) {
        throw "Docker Compose command failed with exit code $LASTEXITCODE."
    }
}

function Wait-Backend {
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $containerId = & docker @(Get-ComposePrefix) ps --status running -q backend 2>$null
        if ($LASTEXITCODE -eq 0 -and $containerId) { return }
        Start-Sleep -Seconds 2
    }
    throw "Classification ERPNext backend did not become ready within 120 seconds."
}

function Test-SiteExists {
    Invoke-Compose -AllowFailure -Arguments @(
        "exec", "-T", "backend", "bash", "-lc", "test -f sites/$siteName/site_config.json"
    )
    return $LASTEXITCODE -eq 0
}

Ensure-DockerReady
Ensure-FrappeDocker
$secrets = Ensure-Secrets

if ($Action -eq "status") {
    Invoke-Compose -Arguments @("ps")
    exit 0
}

if ($Action -eq "stop") {
    Invoke-Compose -Arguments @("down")
    Write-Output "Stopped $projectName. Persistent classification volumes were preserved."
    exit 0
}

Invoke-Compose -Arguments @("up", "-d")
Wait-Backend

if ($Action -eq "bootstrap") {
    if (-not (Test-SiteExists)) {
        Invoke-Compose -Arguments @(
            "exec", "-T", "-e", "SITE_ADMIN_PASSWORD=$($secrets.admin_password)",
            "-e", "DB_ROOT_PASSWORD=$($secrets.db_root_password)", "backend", "bash", "-lc",
            'bench new-site --mariadb-user-host-login-scope="%" --db-root-username=root --db-root-password="$DB_ROOT_PASSWORD" --admin-password="$SITE_ADMIN_PASSWORD" --install-app erpnext material-classification-v4.localhost'
        )
    }
    Write-Output "ERPNext classification Site is ready at http://localhost:$httpPort"
    Write-Output "Credentials are stored under .secrets/erpnext-material-classification-v4 and were not printed."
    exit 0
}

if (-not (Test-SiteExists)) { throw "Site $siteName does not exist. Run bootstrap first." }
Write-Output "Started $projectName at http://localhost:$httpPort"
