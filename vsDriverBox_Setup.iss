; vsDriverBox Installation Script for Inno Setup
; To build the installer:
; 1. Run 'pyinstaller vsDriverBox.spec'
; 2. Open this .iss file in Inno Setup and Compile

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{D3B3A5E1-7B8C-4F9D-A5B2-C1D2E3F4G5H6}
AppName=Vision Driver Box
AppVersion={#AppVersion}
AppPublisher=Jim
DefaultDirName={commonpf}\VisionDriverBox
DefaultGroupName=Vision Driver Box
OutputDir=installer_output
OutputBaseFilename=vsDriverBox_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
; SetupIconFile=src\icon\State_Standby.ico (If you convert png to ico)

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "开机自动启动"; GroupDescription: "启动选项:"; Flags: checkedonce

[Files]
; Source from the 'dist' folder created by PyInstaller
Source: "dist\vsDriverBox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Protect configuration file from being overwritten during upgrade
Source: "src\.syscfg"; DestDir: "{app}\src"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\Vision Driver Box"; Filename: "{app}\vsDriverBox.exe"
Name: "{commondesktop}\Vision Driver Box"; Filename: "{app}\vsDriverBox.exe"; Tasks: desktopicon

[Registry]
; Auto-start on boot
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "vsDriverBox"; ValueData: """{app}\vsDriverBox.exe"""; Tasks: startup

[Run]
Filename: "{app}\vsDriverBox.exe"; Description: "{cm:LaunchProgram,Vision Driver Box}"; Flags: nowait postinstall skipifsilent
