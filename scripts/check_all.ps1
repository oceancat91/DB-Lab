# 一次跑完两个阶段的检查与测试。
#
#   先激活 conda 环境（conda activate lab4-survey），然后在 Lab4 目录执行：
#       .\scripts\check_all.ps1
#       .\scripts\check_all.ps1 -SkipTests      # 只跑结构检查
#
# 脚本不写死解释器路径：默认使用当前 PATH 上的 python，可用 -Python 指定。
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

Invoke-Step -Name '一阶段结构检查' -WorkDir (Join-Path $root 'Lab4-1') -Arguments @('scripts/check_workflow.py')
Invoke-Step -Name '二阶段结构检查' -WorkDir (Join-Path $root 'Lab4-2') -Arguments @('scripts/check_workflow.py')

if (-not $SkipTests) {
    Invoke-Step -Name '一阶段全量测试' -WorkDir (Join-Path $root 'Lab4-1') `
        -Arguments @('-m', 'pytest', 'tests', '-q')
    Invoke-Step -Name '二阶段全量测试' -WorkDir (Join-Path $root 'Lab4-2') `
        -Arguments @('-m', 'pytest', 'tests', '-q')
}

Write-Output ''
Write-Output '=== 汇总 ==='
$results | ForEach-Object { "{0,-16} exit {1}" -f $_.Step, $_.ExitCode } | Write-Output
$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -gt 0) {
    Write-Output ("失败步骤: " + (($failed | ForEach-Object { $_.Step }) -join '、'))
    exit 1
}
Write-Output '全部步骤通过；结构检查不证明业务行为，测试结果以各自输出为准。'
exit 0
