param(
    [ValidateSet("quick", "agent", "full", "integration", "llm", "write")]
    [string]$Mode = "quick"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

switch ($Mode) {
    "quick" {
        python -m pytest `
            tests/unit/agent_runtime/test_capability_registry.py `
            tests/unit/agent_runtime/test_agent_failure_regressions.py `
            tests/unit/agent_runtime/test_tool_contracts.py `
            -m unit -q
    }
    "agent" {
        python -m pytest tests/unit/agent_runtime -m unit -q
    }
    "full" {
        python -m pytest -q
    }
    "integration" {
        python -m pytest -m integration -q
    }
    "llm" {
        python scripts/acceptance/capability_runtime_stability.py --rounds 4
    }
    "write" {
        python scripts/acceptance/agent_write_capabilities.py all
    }
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
