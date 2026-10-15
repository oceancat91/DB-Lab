param([int]$Port = 27084, [string]$ReplicaSet = 'lab4rs')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $projectRoot '.runtime'
$dataPath = Join-Path $runtimePath 'mongo'
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
$probe = [Net.Sockets.TcpClient]::new()
try {
    $probe.Connect('127.0.0.1', $Port)
    Write-Output "Port $Port is already listening. Run init_mongo.py to verify project ownership."
    exit 0
} catch { } finally { $probe.Dispose() }
$mongoExe = (Get-Command mongod -ErrorAction Stop).Path
$logPath = Join-Path $runtimePath 'mongod.log'
$mongoArguments = @('--dbpath', ('"' + $dataPath + '"'), '--logpath', ('"' + $logPath + '"'), '--logappend', '--bind_ip', '127.0.0.1', '--port', $Port, '--replSet', $ReplicaSet, '--oplogSize', '128')
$process = Start-Process -FilePath $mongoExe -ArgumentList $mongoArguments -WindowStyle Hidden -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $runtimePath 'mongod.pid')
Write-Output "Started project MongoDB PID=$($process.Id), port=$Port. Initialize with python scripts/init_mongo.py."
