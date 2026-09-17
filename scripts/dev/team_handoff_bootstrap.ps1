param(
    [ValidateSet("doctor", "bootstrap", "verify")]
    [string]$Action = "doctor",
    [string]$V4Workbook = "",
    [string]$Confirm = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $repoRoot ".env"
$envExample = Join-Path $repoRoot ".env.example"
$confirmationText = "BOOTSTRAP-NEXTERP-TEST-SANDBOX"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE."
    }
}

function Get-JsonResult {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $output = & $Command @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    try {
        return (($output -join [Environment]::NewLine) | ConvertFrom-Json)
    } catch {
        throw "Command did not return valid JSON: $Command $($Arguments -join ' ')"
    }
}

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Ensure-PythonEnvironment {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Invoke-Native -Command "python" -Arguments @("-m", "venv", (Join-Path $repoRoot ".venv"))
    }
    Invoke-Native -Command $venvPython -Arguments @("-m", "pip", "install", "-e", ".[dev]")
    if (-not (Test-Path -LiteralPath $envFile)) {
        Copy-Item -LiteralPath $envExample -Destination $envFile
        Write-Output "Created .env from .env.example. Replace only the values required by your local environment."
    }
}

function Assert-V4Workbook {
    if ([string]::IsNullOrWhiteSpace($V4Workbook)) {
        throw "-V4Workbook is required for V4 bootstrap and verification."
    }
    if (-not (Test-Path -LiteralPath $V4Workbook -PathType Leaf)) {
        throw "V4 workbook does not exist: $V4Workbook"
    }
}

function Invoke-Doctor {
    Assert-Command -Name "git"
    Assert-Command -Name "python"
    Assert-Command -Name "docker"
    Invoke-Native -Command "docker" -Arguments @("version", "--format", "{{.Server.Version}}")
    $result = [ordered]@{
        repository = $repoRoot
        git = (& git -C $repoRoot rev-parse --short HEAD).Trim()
        python = (& python --version).Trim()
        docker_ready = $true
        venv_exists = Test-Path -LiteralPath $venvPython
        env_exists = Test-Path -LiteralPath $envFile
        v4_workbook = if ($V4Workbook) { (Test-Path -LiteralPath $V4Workbook -PathType Leaf) } else { $false }
    }
    $result | ConvertTo-Json
}

function Invoke-Bootstrap {
    if ($Confirm -ne $confirmationText) {
        throw "Bootstrap writes only to the two fixed local test Sites. Re-run with -Confirm $confirmationText"
    }
    Assert-V4Workbook
    Invoke-Doctor | Out-Null
    Ensure-PythonEnvironment

    Invoke-Native -Command "powershell" -Arguments @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\test_env\material_test_site.ps1"), "-Action", "bootstrap")
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\material_master\sync_reference_catalog_database.py"), "--version", "2026-05")
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\sync_gpc_materials_to_test_site.py"), "initialize")
    $gpcPlan = Get-JsonResult -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\sync_gpc_materials_to_test_site.py"), "plan")
    Invoke-Native -Command $venvPython -Arguments @(
        (Join-Path $repoRoot "scripts\erpnext\sync_gpc_materials_to_test_site.py"), "apply",
        "--request-id", ([guid]::NewGuid().Guid),
        "--confirm-release-hash", [string]$gpcPlan.release_hash
    )
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\sync_gpc_materials_to_test_site.py"), "verify")

    $businessPlan = Get-JsonResult -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\bootstrap_material_test_business.py"), "plan")
    Invoke-Native -Command $venvPython -Arguments @(
        (Join-Path $repoRoot "scripts\erpnext\bootstrap_material_test_business.py"), "apply",
        "--request-id", ([guid]::NewGuid().Guid),
        "--confirm-plan-hash", [string]$businessPlan.plan_hash
    )
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\bootstrap_material_test_business.py"), "verify")

    Invoke-Native -Command "powershell" -Arguments @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\test_env\material_classification_v4_site.ps1"), "-Action", "bootstrap")
    $v4Plan = Get-JsonResult -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\import_classification_v4_workbook.py"), "plan", "--input", $V4Workbook)
    Invoke-Native -Command $venvPython -Arguments @(
        (Join-Path $repoRoot "scripts\erpnext\import_classification_v4_workbook.py"), "apply",
        "--input", $V4Workbook,
        "--request-id", ([guid]::NewGuid().Guid),
        "--confirm-release-hash", [string]$v4Plan.release_hash
    )
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\import_classification_v4_workbook.py"), "verify", "--input", $V4Workbook)
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\bootstrap_classification_v4_business.py"))

    Write-Output "Bootstrap completed. Start the portal with:"
    Write-Output "& .venv\Scripts\python.exe scripts\dev\agent_workbench.py --port 8788 --profile material_test"
}

function Invoke-Verify {
    Assert-V4Workbook
    Invoke-Doctor | Out-Null
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python environment is missing. Run the bootstrap action first."
    }
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\sync_gpc_materials_to_test_site.py"), "verify")
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\bootstrap_material_test_business.py"), "verify")
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\erpnext\import_classification_v4_workbook.py"), "verify", "--input", $V4Workbook)
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\dev\project_context.py"), "snapshot")
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\dev\project_context.py"), "audit-docs")
    Invoke-Native -Command $venvPython -Arguments @((Join-Path $repoRoot "scripts\dev\project_context.py"), "check")
    Write-Output "Both material test Sites and the repository context passed verification."
}

Push-Location $repoRoot
try {
    switch ($Action) {
        "doctor" { Invoke-Doctor }
        "bootstrap" { Invoke-Bootstrap }
        "verify" { Invoke-Verify }
    }
} finally {
    Pop-Location
}
