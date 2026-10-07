param([switch]$Clipboard, [switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Force secrets | Out-Null
if (!(Test-Path secrets/token)) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [IO.File]::WriteAllText((Join-Path $projectRoot 'secrets/token'), [Convert]::ToBase64String($bytes))
}
if (!(Test-Path secrets/id_ed25519)) {
    # Use ProcessStartInfo to preserve an empty passphrase argument on Windows PowerShell.
    $keyPath = Join-Path $projectRoot 'secrets/id_ed25519'
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'ssh-keygen.exe'
    $psi.Arguments = '-q -t ed25519 -N "" -f "' + $keyPath + '"'
    $psi.UseShellExecute = $false
    $p = [Diagnostics.Process]::Start($psi)
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw 'SSH key generation failed' }
}
Copy-Item -LiteralPath secrets/id_ed25519.pub -Destination secrets/authorized_keys
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($file in @('secrets/token','secrets/id_ed25519')) {
    & icacls $file /inheritance:r /grant:r "${currentIdentity}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Secret ACL setup failed' }
}
if (!(Test-Path .venv/Scripts/python.exe)) { & py -3.10 -m venv .venv }
& .venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies failed' }
if ($LocalOnly) { $env:SSH_BIND = '127.0.0.1' }
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed' }
& "$PSScriptRoot/start-agent.ps1" -Clipboard:$Clipboard
Write-Host "SSH: ssh -t -p 9961 -i `"$projectRoot/secrets/id_ed25519`" kakao@localhost"
