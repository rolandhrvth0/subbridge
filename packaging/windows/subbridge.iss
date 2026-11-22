; Inno Setup script – builds SubBridge-Setup-<version>.exe from dist\SubBridge
; iscc /DAppVersion=0.1.1 packaging\windows\subbridge.iss
#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif

[Setup]
AppId={{7E1D8F2A-5B3C-4C11-9A7E-5B0D2C8E4F11}
AppName=SubBridge
AppVersion={#AppVersion}
AppPublisher=Roland Horváth (rolandhrvth.hu)
AppPublisherURL=https://rolandhrvth.hu/subbridge
AppSupportURL=https://rolandhrvth.hu/subbridge
DefaultDirName={autopf}\SubBridge
DefaultGroupName=SubBridge
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=SubBridge-Setup-{#AppVersion}
SetupIconFile=..\subbridge.ico
UninstallDisplayIcon={app}\SubBridge.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\..\LICENSE
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "firewall"; Description: "Allow phones on the local network to connect (Windows Firewall)"; GroupDescription: "Network:"

[Files]
Source: "..\..\dist\SubBridge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SubBridge"; Filename: "{app}\SubBridge.exe"
Name: "{autodesktop}\SubBridge"; Filename: "{app}\SubBridge.exe"; Tasks: desktopicon

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""SubBridge"""; Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""SubBridge"" dir=in action=allow program=""{app}\SubBridge.exe"" profile=private enable=yes"; Flags: runhidden; Tasks: firewall
Filename: "{app}\SubBridge.exe"; Description: "{cm:LaunchProgram,SubBridge}"; Flags: nowait postinstall skipifsilent
; automatic update (silent): start the new version again unless the app was being closed
Filename: "{app}\SubBridge.exe"; Flags: nowait; Check: Relaunch

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""SubBridge"""; Flags: runhidden; RunOnceId: "fw"

[Code]
function Relaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
