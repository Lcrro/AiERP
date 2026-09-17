param(
    [ValidateSet("bootstrap", "start", "stop", "status", "baseline")]
    [string]$Action = "status",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$siteName = "material-test.localhost"
$projectName = "nexterp-material-test"
$erpnextVersion = "v15.118.2"
$frappeDockerCommit = "e33f185a0cb14980f1fb8a24989df18f0a41d86b"
$httpPort = 8003

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runtimeRoot = Join-Path $repoRoot ".runtime\erpnext-material-test"
$frappeDockerRoot = Join-Path $runtimeRoot "frappe_docker"
$secretRoot = Join-Path $repoRoot ".secrets\erpnext-material-test"
$secretJsonPath = Join-Path $secretRoot "site-secrets.json"
$stackEnvPath = Join-Path $secretRoot "stack.env"
$baselineRoot = Join-Path $secretRoot "blank-baseline"

function New-SecureText {
    $bytes = [byte[]]::new(32)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Ensure-DockerReady {
    & docker version --format '{{.Server.Version}}' *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is not ready. Start Docker Desktop and retry."
    }
}

function Ensure-FrappeDocker {
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $frappeDockerRoot ".git"))) {
        & git clone --no-checkout https://github.com/frappe/frappe_docker.git $frappeDockerRoot
        if ($LASTEXITCODE -ne 0) { throw "Unable to clone frappe_docker." }
        & git -C $frappeDockerRoot fetch --depth 1 origin $frappeDockerCommit
        if ($LASTEXITCODE -ne 0) { throw "Unable to fetch pinned frappe_docker commit." }
        & git -C $frappeDockerRoot checkout --detach $frappeDockerCommit
        if ($LASTEXITCODE -ne 0) { throw "Unable to check out pinned frappe_docker commit." }
    }

    $actualCommit = (& git -C $frappeDockerRoot rev-parse HEAD).Trim()
    if ($actualCommit -ne $frappeDockerCommit) {
        throw "frappe_docker commit mismatch: expected $frappeDockerCommit, got $actualCommit"
    }
}

function Ensure-Secrets {
    New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $secretJsonPath)) {
        $payload = [ordered]@{
            site = $siteName
            db_root_password = New-SecureText
            admin_password = New-SecureText
            generated_at = [DateTimeOffset]::Now.ToString("o")
        }
        $payload | ConvertTo-Json | Set-Content -LiteralPath $secretJsonPath -Encoding utf8
    }

    $secrets = Get-Content -Raw -LiteralPath $secretJsonPath | ConvertFrom-Json
    $stackEnv = @(
        "ERPNEXT_VERSION=$erpnextVersion"
        "DB_PASSWORD=$($secrets.db_root_password)"
        "HTTP_PUBLISH_PORT=$httpPort"
        "FRAPPE_SITE_NAME_HEADER=$siteName"
        "PULL_POLICY=missing"
        "RESTART_POLICY=unless-stopped"
    )
    $stackEnv | Set-Content -LiteralPath $stackEnvPath -Encoding utf8
    return $secrets
}

function Get-ComposePrefix {
    return @(
        "compose",
        "--project-name", $projectName,
        "--env-file", $stackEnvPath,
        "-f", (Join-Path $frappeDockerRoot "compose.yaml"),
        "-f", (Join-Path $frappeDockerRoot "overrides\compose.mariadb.yaml"),
        "-f", (Join-Path $frappeDockerRoot "overrides\compose.redis.yaml"),
        "-f", (Join-Path $frappeDockerRoot "overrides\compose.noproxy.yaml")
    )
}

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowFailure,
        [switch]$PassExitCode
    )
    $dockerArgs = @(Get-ComposePrefix) + $Arguments
    & docker @dockerArgs
    $composeExitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $composeExitCode -ne 0) {
        throw "Docker Compose command failed with exit code $composeExitCode."
    }
    if ($PassExitCode) { return $composeExitCode }
}

function Wait-Backend {
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $containerId = & docker compose --project-name $projectName ps --status running -q backend 2>$null
        if ($LASTEXITCODE -eq 0 -and $containerId) { return }
        Start-Sleep -Seconds 2
    }
    throw "ERPNext backend did not become ready within 120 seconds."
}

function Test-SiteExists {
    $result = Invoke-Compose -AllowFailure -PassExitCode -Arguments @(
        "exec", "-T", "backend", "bash", "-lc",
        "test -f sites/$siteName/site_config.json"
    )
    return $result -eq 0
}

if ($Action -eq "stop") {
    Ensure-DockerReady
    Ensure-FrappeDocker
    Ensure-Secrets | Out-Null
    Invoke-Compose -Arguments @("down") | Out-Null
    Write-Output "Stopped $projectName. Persistent volumes were preserved."
    exit 0
}

Ensure-DockerReady
Ensure-FrappeDocker
$secrets = Ensure-Secrets

if ($Action -eq "status") {
    Invoke-Compose -Arguments @("ps")
    exit 0
}

Invoke-Compose -Arguments @("up", "-d") | Out-Null
Wait-Backend

if ($Action -eq "start") {
    Write-Output "Started $projectName at http://localhost:$httpPort"
    exit 0
}

if ($Action -eq "bootstrap") {
    if (-not (Test-SiteExists)) {
        $createArgs = @(
            "exec", "-T",
            "-e", "SITE_ADMIN_PASSWORD=$($secrets.admin_password)",
            "-e", "DB_ROOT_PASSWORD=$($secrets.db_root_password)",
            "backend", "bash", "-lc",
            'bench new-site --mariadb-user-host-login-scope="%" --db-root-username=root --db-root-password="$DB_ROOT_PASSWORD" --admin-password="$SITE_ADMIN_PASSWORD" --install-app erpnext material-test.localhost'
        )
        Invoke-Compose -Arguments $createArgs | Out-Null
    }
    Invoke-Compose -Arguments @("exec", "-T", "backend", "bench", "--site", $siteName, "list-apps") | Out-Null
    Write-Output "ERPNext site is ready at http://localhost:$httpPort"
    Write-Output "Credentials are stored under .secrets/erpnext-material-test and were not printed."
    exit 0
}

if ($Action -eq "baseline") {
    if (-not (Test-SiteExists)) { throw "Site $siteName does not exist. Run bootstrap first." }
    if (Test-Path -LiteralPath $baselineRoot) {
        if (-not $Force) { throw "Blank baseline already exists. Use -Force to replace it." }
        $resolvedBaseline = (Resolve-Path -LiteralPath $baselineRoot).Path
        $resolvedSecretRoot = (Resolve-Path -LiteralPath $secretRoot).Path
        if (-not $resolvedBaseline.StartsWith($resolvedSecretRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove baseline outside the secret root."
        }
        Remove-Item -LiteralPath $resolvedBaseline -Recurse -Force
    }
    Invoke-Compose -Arguments @("exec", "-T", "backend", "bench", "--site", $siteName, "backup", "--with-files", "--compress") | Out-Null
    New-Item -ItemType Directory -Path $baselineRoot -Force | Out-Null
    Invoke-Compose -Arguments @(
        "cp",
        "backend:/home/frappe/frappe-bench/sites/$siteName/private/backups/.",
        $baselineRoot
    ) | Out-Null
    Write-Output "Blank site baseline saved under .secrets/erpnext-material-test/blank-baseline."
}
