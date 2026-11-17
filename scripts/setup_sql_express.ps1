# Run in an elevated PowerShell on PC-01. Uses local extracted Express setup media.
[CmdletBinding()]
param(
    [string]$SetupPath,
    [string]$OdbcMsiPath,
    [switch]$AcceptLicense,
    [string]$InstanceName = 'SQLEXPRESS',
    [string]$Database = 'QRPointSystem',
    [string]$AppAccount = "$env:USERDOMAIN\$env:USERNAME",
    [string]$DataDir = "$env:ProgramData\QRPointSystem",
    [string]$BackupDir = "$env:ProgramData\QRPointSystem\backups",
    [string]$Python = "$PSScriptRoot\..\.venv\Scripts\python.exe"
)
$ErrorActionPreference = 'Stop'
if ($InstanceName -notmatch '^[A-Za-z][A-Za-z0-9_]{0,15}$') { throw 'Invalid instance name' }
if (($SetupPath -or $OdbcMsiPath) -and -not $AcceptLicense) {
    throw 'Read the Microsoft SQL Server / ODBC license terms, then pass -AcceptLicense to install.'
}
if ($SetupPath) {
    $media = (Resolve-Path -LiteralPath $SetupPath).Path
    $admin = "$env:USERDOMAIN\$env:USERNAME"
    $setupArgs = @('/Q', '/ACTION=Install', '/FEATURES=SQLEngine', "/INSTANCENAME=$InstanceName", "/SQLSYSADMINACCOUNTS=`"$admin`"", '/SQLSVCSTARTUPTYPE=Automatic', '/TCPENABLED=0', '/NPENABLED=0', '/IACCEPTSQLSERVERLICENSETERMS')
    $setupResult = Start-Process -FilePath $media -ArgumentList $setupArgs -WindowStyle Hidden -Wait -PassThru
    if ($setupResult.ExitCode -notin @(0, 3010)) { throw "SQL setup failed: $($setupResult.ExitCode)" }
    if ($setupResult.ExitCode -eq 3010) { throw 'Reboot Windows, then rerun without -SetupPath.' }
}
if ($OdbcMsiPath) {
    $driver = (Resolve-Path -LiteralPath $OdbcMsiPath).Path
    $process = Start-Process msiexec.exe -ArgumentList @('/i', "`"$driver`"", '/qn', '/norestart', 'IACCEPTMSODBCSQLLICENSETERMS=YES') -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) { throw "ODBC install failed: $($process.ExitCode)" }
}
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
& icacls.exe $DataDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' "${AppAccount}:(OI)(CI)M"
if ($LASTEXITCODE -ne 0) { throw 'Data folder ACL failed' }
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$sqlService = "NT SERVICE\MSSQL`$$InstanceName"
& icacls.exe $BackupDir /grant "${sqlService}:(OI)(CI)M" "${AppAccount}:(OI)(CI)M"
if ($LASTEXITCODE -ne 0) { throw 'Backup folder ACL failed' }
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & $Python -m server.cli provision --data-dir $DataDir --server ".\$InstanceName" --database $Database --app-account $AppAccount --backup-dir $BackupDir
    if ($LASTEXITCODE -ne 0) { throw 'Database provisioning failed' }
} finally { Pop-Location }
Write-Host 'SQL Express is configured. Follow docs/SQL_EXPRESS.md to migrate existing data.'
