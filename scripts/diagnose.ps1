$ErrorActionPreference = 'Stop'
$processes = Get-Process KakaoTalk -ErrorAction Stop
$processes | Select-Object Id,Path,SessionId,MainWindowHandle
foreach ($p in $processes) {
    $p.Modules | Select-Object ModuleName
    Get-NetTCPConnection -OwningProcess $p.Id -ErrorAction SilentlyContinue | Select-Object State,LocalPort,RemoteAddress,RemotePort
}
Get-ChildItem "$env:LOCALAPPDATA\Kakao\KakaoTalk" -Force | Select-Object Name,Mode
Get-ChildItem \\.\pipe\ -ErrorAction SilentlyContinue | Where-Object Name -Match 'kakao|talk' | Select-Object Name
# Metadata only. No database, memory or credential contents are read.
