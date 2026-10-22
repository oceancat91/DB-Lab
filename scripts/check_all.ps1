# Run both stages' structural checks and test suites in one pass.
#
#   conda activate lab4-survey
#   .\scripts\check_all.ps1
#   .\scripts\check_all.ps1 -SkipTests
#
# The file is deliberately ASCII-only so Windows PowerShell 5.1 and pwsh 7 read it the same way
# regardless of BOM. Chinese documentation lives in README.md.
param(
    [string]$Python = 'python',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$results = @()

function Invoke-Step {
    param([string]$Name, [string]$WorkDir, [string[]]$Arguments)
    Write-Output "=== $Name ==="
    Push-Location $WorkDir
    try {
        & $Python @Arguments
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    $script:results += [pscustomobject]@{ Step = $Name; ExitCode = $code }
    Write-Output ("--- {0}: exit {1} ---" -f $Name, $code)
}

Invoke-Step -Name 'privacy-scan' -WorkDir $root -Arguments @('scripts/check_private_data.py')
Invoke-Step -Name 'stage-1-checker' -WorkDir (Join-Path $root 'Lab4-1') -Arguments @('scripts/check_workflow.py')
Invoke-Step -Name 'stage-2-checker' -WorkDir (Join-Path $root 'Lab4-2') -Arguments @('scripts/check_workflow.py')

if (-not $SkipTests) {
    Invoke-Step -Name 'stage-1-tests' -WorkDir (Join-Path $root 'Lab4-1') `
        -Arguments @('-m', 'pytest', 'tests', '-q')
    Invoke-Step -Name 'stage-2-tests' -WorkDir (Join-Path $root 'Lab4-2') `
        -Arguments @('-m', 'pytest', 'tests', '-q')
}

Write-Output ''
Write-Output '=== summary ==='
$results | ForEach-Object { "{0,-18} exit {1}" -f $_.Step, $_.ExitCode } | Write-Output
$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -gt 0) {
    Write-Output ("failed steps: " + (($failed | ForEach-Object { $_.Step }) -join ', '))
    exit 1
}
Write-Output 'All steps passed. Structural checks do not prove behaviour; see each test log.'
exit 0
