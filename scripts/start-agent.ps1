param([switch]$Clipboard, [switch]$Mock)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $projectRoot
if (Test-Path agent.pid) {
    $previousPid = [int](Get-Content agent.pid)
    $previousProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $previousPid" -ErrorAction SilentlyContinue
    if ($previousProcess -and $previousProcess.CommandLine -like '*bridge.agent*' -and $previousProcess.CommandLine -like "*$projectRoot*") {
        throw 'Agent already running. Stop it first with scripts/stop.ps1 -AgentOnly'
    }
}
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
$arguments = '-m bridge.agent --token-file "' + (Join-Path $projectRoot 'secrets/token') + '"'
if ($Clipboard) { $arguments += ' --clipboard' }
if ($Mock) { $arguments += ' --mock' }
$p = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput agent.log -RedirectStandardError agent-error.log
$p.Id | Set-Content agent.pid
Write-Host "Host agent started in this user's GUI session. PID $($p.Id)"
