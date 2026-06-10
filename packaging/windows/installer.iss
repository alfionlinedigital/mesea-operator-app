; Inno Setup script for the Mesea Operator Windows installer.
; Compiled in CI:  iscc /DMyAppVersion=<ver> packaging\windows\installer.iss
; Wraps the PyInstaller onefile exe (dist\mesea-operator.exe) into a per-user
; installer (no admin required) with Start Menu + desktop shortcuts.

#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif
#define MyAppName "Mesea Operator"

[Setup]
AppId={{8F4E2A10-MESEA-OPER-ATOR-0000A1B2C3D4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Alfi Online Digital
DefaultDirName={autopf}\Mesea Operator
DefaultGroupName=Mesea Operator
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\installer_out
OutputBaseFilename=mesea-operator-windows-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\mesea-operator.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Mesea Operator"; Filename: "{app}\mesea-operator.exe"
Name: "{userdesktop}\Mesea Operator"; Filename: "{app}\mesea-operator.exe"

[Run]
Filename: "{app}\mesea-operator.exe"; Description: "Pornește Mesea Operator"; Flags: nowait postinstall skipifsilent
