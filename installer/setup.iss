#define AppName "QRPointSystem"
[Setup]
AppId={{DCF730C7-7AA1-4759-9312-937152549726}
AppName={#AppName}
AppVersion=1.0.1
DefaultDirName={autopf}\QRPointSystem
DefaultGroupName=QR Point System
OutputDir=..\dist
OutputBaseFilename=Setup
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\QRPointServer.exe
CloseApplications=no
SetupLogging=yes

[Files]
Source: "..\dist\QRPointServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{code:DataDir}"
Name: "{code:BackupDir}"

[Tasks]
Name: "firewall"; Description: "Allow inbound TCP only for the specified trusted LAN on Private profile (administrator change)"; Flags: unchecked
Name: "autostart"; Description: "Start server when the installing Windows user logs on (administrator change)"; Flags: unchecked

[Icons]
Name: "{group}\Start server"; Filename: "{app}\QRPointServer.exe"
Name: "{group}\Initialize Admin (first install only)"; Filename: "{app}\QRPointServer.exe"; Parameters: "init"
Name: "{group}\Stop server gracefully"; Filename: "{app}\stop_server.bat"
Name: "{group}\Check system"; Filename: "{app}\check_system.bat"

[Registry]
Root: HKLM64; Subkey: "Software\QRPointSystem"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:DataDir}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "QRPointSystem"; ValueData: """{app}\QRPointServer.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{sys}\icacls.exe"; Parameters: """{code:DataDir}"" /inheritance:r /grant:r ""*S-1-5-18:(OI)(CI)F"" ""*S-1-5-32-544:(OI)(CI)F"" ""{code:DataOwner}:(OI)(CI)M"" /T"; Flags: runhidden waituntilterminated
Filename: "{sys}\icacls.exe"; Parameters: """{code:BackupDir}"" /inheritance:r /grant:r ""*S-1-5-18:(OI)(CI)F"" ""*S-1-5-32-544:(OI)(CI)F"" ""{code:DataOwner}:(OI)(CI)M"" /T"; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""QRPointSystem LAN"""; Tasks: firewall; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""QRPointSystem LAN"" dir=in action=allow program=""{app}\QRPointServer.exe"" protocol=TCP localport={code:ServerPort} remoteip={code:LanSubnet} profile=private"; Tasks: firewall; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\QRPointServer.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopQRPoint"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""QRPointSystem LAN"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveQRPointFirewall"

[Code]
var
  ConfigPage: TInputQueryWizardPage;

function DataDir(Param: String): String;
begin
  Result := ConfigPage.Values[3];
end;

function BackupDir(Param: String): String;
begin
  Result := ConfigPage.Values[4];
end;

function DataOwner(Param: String): String;
begin
  Result := ConfigPage.Values[2];
end;

function ServerPort(Param: String): String;
begin
  Result := ConfigPage.Values[0];
end;

function LanSubnet(Param: String): String;
begin
  Result := ConfigPage.Values[1];
end;

procedure InitializeWizard;
var ExistingDir: String;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir, 'LAN configuration and data access',
    'Only PC-01 needs this installer',
    'Data/backups: ProgramData\QRPointSystem (preserved on uninstall). HTTP is unencrypted. Choose a trusted LAN. Existing config is preserved. Enter the Windows account that will run the server.');
  ConfigPage.Add('TCP port (1-65535):', False);
  ConfigPage.Add('Trusted IPv4 LAN subnet CIDR (e.g. 192.168.10.0/24):', False);
  ConfigPage.Add('Data owner Windows account (DOMAIN\User):', False);
  ConfigPage.Add('Data directory (local NTFS, not a network share):', False);
  ConfigPage.Add('Backup directory:', False);
  ConfigPage.Values[0] := '8080';
  ConfigPage.Values[1] := '';
  ConfigPage.Values[2] := ExpandConstant('{userinfoname}');
  ConfigPage.Values[3] := ExpandConstant('{commonappdata}\QRPointSystem');
  if RegQueryStringValue(HKLM64, 'Software\QRPointSystem', 'DataDir', ExistingDir) then
    ConfigPage.Values[3] := ExistingDir;
  ConfigPage.Values[4] := AddBackslash(ConfigPage.Values[3]) + 'backups';
end;

function ValidCIDR(Value: String): Boolean;
var I, J, N, Slash, Prefix, Octets: Integer; Part: String;
begin
  Result := False;
  Slash := Pos('/', Value);
  if Slash = 0 then exit;
  Prefix := StrToIntDef(Copy(Value, Slash + 1, 10), -1);
  if (Prefix < 8) or (Prefix > 32) then exit;
  Part := ''; Octets := 0;
  for I := 1 to Slash do begin
    if (Value[I] = '.') or (I = Slash) then begin
      N := StrToIntDef(Part, -1);
      if (N < 0) or (N > 255) then exit;
      if (Octets = 0) and not ((N = 10) or (N = 172) or (N = 192)) then exit;
      if (Octets = 1) then begin
        J := StrToIntDef(Copy(Value, 1, Pos('.', Value)-1), -1);
        if (J = 172) and ((N < 16) or (N > 31) or (Prefix < 12)) then exit;
        if (J = 192) and ((N <> 168) or (Prefix < 16)) then exit;
      end;
      Octets := Octets + 1; Part := '';
    end else begin
      if (Value[I] < '0') or (Value[I] > '9') then exit;
      Part := Part + Value[I];
    end;
  end;
  Result := Octets = 4;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var Port: Integer;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then begin
    Port := StrToIntDef(ConfigPage.Values[0], 0);
    if (Port < 1) or (Port > 65535) or (ConfigPage.Values[2] = '') or
      (Length(ConfigPage.Values[3]) < 4) or (Length(ConfigPage.Values[4]) < 4) or
      (Copy(ConfigPage.Values[3], 1, 2) = '\\') or
      (Pos('"', ConfigPage.Values[2]) > 0) or
      (WizardIsTaskSelected('firewall') and not ValidCIDR(ConfigPage.Values[1])) then begin
      MsgBox('Enter valid port, Windows data owner, and private IPv4 CIDR for firewall.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function JsonPath(Value: String): String;
begin
  StringChangeEx(Value, '\', '\\', True);
  StringChangeEx(Value, '"', '\"', True);
  Result := Value;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var ConfigPath: String;
begin
  if CurStep = ssPostInstall then begin
    ConfigPath := AddBackslash(ConfigPage.Values[3]) + 'config.json';
    if not FileExists(ConfigPath) then
      SaveStringToFile(ConfigPath, UTF8Encode('{"port":' + ConfigPage.Values[0] + ',"secure_cookie":false,"backup_dir":"' + JsonPath(ConfigPage.Values[4]) + '"}'), False);
  end;
end;
