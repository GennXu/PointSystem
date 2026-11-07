#define AppName "QRPointSystem"
[Setup]
AppId={{DCF730C7-7AA1-4759-9312-937152549726}
AppName={#AppName}
AppVersion=1.1.0
DefaultDirName={autopf}\QRPointSystem
DefaultGroupName=QR 點數系統
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

[Languages]
Name: "chinesetraditional"; MessagesFile: "ChineseTraditional.isl"

[Files]
Source: "..\dist\QRPointServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{code:DataDir}"
Name: "{code:BackupDir}"

[Tasks]
Name: "firewall"; Description: "僅允許指定可信任私人網段的 TCP 連入（需管理員權限）"; Flags: unchecked
Name: "autostart"; Description: "安裝者登入 Windows 後自動啟動服務（需管理員權限）"; Flags: unchecked

[Icons]
Name: "{group}\啟動伺服器"; Filename: "{app}\QRPointServer.exe"
Name: "{group}\建立初始管理員（僅首次安裝）"; Filename: "{app}\QRPointServer.exe"; Parameters: "init"
Name: "{group}\正常停止伺服器"; Filename: "{app}\stop_server.bat"
Name: "{group}\檢查系統"; Filename: "{app}\check_system.bat"

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
  ConfigPage := CreateInputQueryPage(wpSelectDir, '區域網路與資料存取設定',
    '只有伺服器主機需要安裝',
    '資料與備份在解除安裝後會保留。HTTP 未加密，請選可信任區域網路。既有設定會保留，請指定執行服務的 Windows 帳號。');
  ConfigPage.Add('TCP 連接埠（1 至 65535）：', False);
  ConfigPage.Add('可信任的私人 IPv4 網段（例如 192.168.1.0/24）：', False);
  ConfigPage.Add('資料擁有者 Windows 帳號（網域\使用者）：', False);
  ConfigPage.Add('資料目錄（本機磁碟，請勿使用網路共用）：', False);
  ConfigPage.Add('備份目錄：', False);
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
      MsgBox('請輸入有效的連接埠、Windows 資料擁有者及私人防火牆網段。', mbError, MB_OK);
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
