# Run in an elevated Windows PowerShell console. No downloads or CA-store changes.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIP,
    [string]$DataDir = "$env:ProgramData\QRPointSystem",
    [string]$AppDir,
    [string]$Python,
    [string]$AppAccount = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
    [ValidateRange(1, 65535)]
    [int]$Port,
    [switch]$StopServer,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'

$address = $null
if (-not [System.Net.IPAddress]::TryParse($ServerIP, [ref]$address)) { throw 'ServerIP must be an IPv4 address.' }
$octets = $address.GetAddressBytes()
if ($octets.Length -ne 4 -or -not (
    $octets[0] -eq 10 -or
    ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
    ($octets[0] -eq 192 -and $octets[1] -eq 168)
)) { throw 'Use the server private IPv4 address (10.x, 172.16-31.x, or 192.168.x).' }
$ServerIP = $address.ToString()
$DataDir = [System.IO.Path]::GetFullPath($DataDir)
if (-not $AppDir) {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'QRPointServer.exe')) {
        $AppDir = $PSScriptRoot
    } else { $AppDir = Split-Path $PSScriptRoot -Parent }
}
$AppDir = (Resolve-Path -LiteralPath $AppDir).Path
$serverExe = Join-Path $AppDir 'QRPointServer.exe'
$prefix = @()
if (-not $Python -and (Test-Path -LiteralPath $serverExe)) {
    $runner = $serverExe
} else {
    if (-not $Python) { $Python = Join-Path $AppDir '.venv\Scripts\python.exe' }
    if (-not (Test-Path -LiteralPath $Python)) {
        throw 'No application runtime found. Specify -AppDir containing the new EXE, or -Python and the source project directory.'
    }
    $runner = (Resolve-Path -LiteralPath $Python).Path
    if (-not (Test-Path -LiteralPath (Join-Path $AppDir 'server\https_setup.py'))) {
        throw 'The source project does not contain server\https_setup.py.'
    }
    $prefix = @('-m', 'server.cli')
}
$configPath = Join-Path $DataDir 'config.json'
$tlsDir = Join-Path $DataDir 'https'

Push-Location $AppDir
try {
    $helpText = (& $runner @prefix --help 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $helpText -notmatch 'https-setup') {
        throw 'This application version does not support https-setup. Use the updated EXE or source project.'
    }
    if ($ValidateOnly) {
        Write-Host "Validation passed. Runtime: $runner"
        Write-Host "Private IP: $ServerIP | Data: $DataDir"
        Write-Host 'No files, certificates, permissions, firewall rules, or trust stores were changed.'
        return
    }
    $principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run Windows PowerShell as Administrator, then execute this script again.'
    }
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw 'The selected data directory has no config.json. Configure the application first, or specify the correct -DataDir.'
    }
    # Parse before stopping anything, and retain the original file unchanged on validation errors.
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $effectivePort = if ($PSBoundParameters.ContainsKey('Port')) { $Port } elseif ($config.port) { [int]$config.port } else { 8080 }
    $account = New-Object System.Security.Principal.NTAccount($AppAccount)
    $accountSid = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
    if ($StopServer) {
        & $runner @prefix stop --data-dir $DataDir
        if ($LASTEXITCODE -ne 0) { throw 'Could not request a normal server stop.' }
    }
    # Respect the application's lock. Never remove server.lock to bypass a running server.
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    $free = $false
    do {
        $stream = $null
        $locked = $false
        try {
            $stream = [System.IO.File]::Open((Join-Path $DataDir 'server.lock'), 'OpenOrCreate', 'ReadWrite', 'ReadWrite')
            $stream.Lock(0, 1)
            $locked = $true
            $free = $true
        } catch [System.IO.IOException] {
            if (-not $StopServer -or [DateTime]::UtcNow -ge $deadline) {
                throw 'Server lock is busy. Stop the server normally or rerun with -StopServer.'
            }
            Start-Sleep -Milliseconds 500
        } finally {
            if ($stream) {
                if ($locked) { $stream.Unlock(0, 1) }
                $stream.Dispose()
            }
        }
    } until ($free)
    New-Item -ItemType Directory -Path $tlsDir -Force | Out-Null
    $grants = @('*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F')
    if ($accountSid -notin @('S-1-5-18', 'S-1-5-32-544')) { $grants += "*${accountSid}:(OI)(CI)RX" }
    & icacls.exe $tlsDir /inheritance:r /grant:r @grants
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the HTTPS folder permissions.' }
    # Keep a unique backup in the protected folder, not in the public certificate export.
    $backup = Join-Path $tlsDir ("config-before-https-{0}.json" -f [guid]::NewGuid().ToString('N'))
    Copy-Item -LiteralPath $configPath -Destination $backup
    Write-Host 'Enter the CA password twice. Reuse the original password when renewing.'
    & $runner @prefix https-setup --data-dir $DataDir --ip $ServerIP --port $effectivePort
    if ($LASTEXITCODE -ne 0) { throw 'HTTPS setup failed. The server remains stopped; inspect the error before retrying.' }
    $certificate = Join-Path $tlsDir 'QRPoint-Root-CA.cer'
    if (-not (Test-Path -LiteralPath $certificate)) { throw 'No public CA certificate was produced.' }
    Write-Host ''
    Write-Host 'HTTPS certificates generated; config.json updated.' -ForegroundColor Green
    Write-Host "Phone URL: https://${ServerIP}:$effectivePort"
    Write-Host "Install ONLY this public certificate on phones: $certificate"
    Write-Host "CA SHA-256: $((Get-FileHash -LiteralPath $certificate -Algorithm SHA256).Hash)"
    Write-Host "Configuration backup: $backup"
    Write-Host "Application account with certificate read access: $AppAccount"
    Write-Host 'Restart the application normally. No firewall or device trust settings were changed.'
    Write-Host 'On iPhone, enable full trust after installing the CA. Allow camera access in the browser.'
} finally { Pop-Location }
