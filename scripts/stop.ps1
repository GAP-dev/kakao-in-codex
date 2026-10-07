param([switch]$AgentOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (Test-Path agent.pid) {
    $agentPid = [int](Get-Content agent.pid)
    $p = Get-CimInstance Win32_Process -Filter "ProcessId = $agentPid" -ErrorAction SilentlyContinue
    if ($p -and $p.CommandLine -like '*bridge.agent*' -and $p.CommandLine -like "*$projectRoot*") {
        $allProcesses = Get-CimInstance Win32_Process
        $descendantIds = @($agentPid)
        for ($level = 0; $level -lt 4; $level++) {
            $childIds = @($allProcesses | Where-Object { $_.ParentProcessId -in $descendantIds -and $_.Name -like 'python*' } | Select-Object -ExpandProperty ProcessId)
            $descendantIds = @($descendantIds + $childIds | Select-Object -Unique)
        }
        [array]::Reverse($descendantIds)
        foreach ($childId in $descendantIds) { Stop-Process -Id $childId -ErrorAction SilentlyContinue }
        Stop-Process -Id $agentPid -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath agent.pid
}
if (!$AgentOnly) { & docker compose down }
