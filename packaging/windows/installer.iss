; Inno Setup script for the Mesea Operator Windows installer.
; Compiled in CI:  iscc /DMyAppVersion=<ver> packaging\windows\installer.iss
; Wraps the PyInstaller onefile exe (dist\mesea-operator.exe) into a per-user
; installer (no admin required) with Start Menu + desktop shortcuts.

#ifndef MyAppVersion
  #define MyAppVersion "0.3.1"
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
; Detect a running instance and ask the user to close it before installing.
; The running app holds this same named mutex (config.SINGLE_INSTANCE_MUTEX /
; instance_guard.acquire_singleton); if present, Setup/Uninstall halts with a
; "please close all instances" prompt. CloseApplications additionally lets the
; wizard offer to shut the app if it still holds the target exe open.
AppMutex=MeseaOperatorMutex
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\..\dist\mesea-operator.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Mesea Operator"; Filename: "{app}\mesea-operator.exe"
Name: "{userdesktop}\Mesea Operator"; Filename: "{app}\mesea-operator.exe"

[Run]
Filename: "{app}\mesea-operator.exe"; Description: "Pornește Mesea Operator"; Flags: nowait postinstall skipifsilent
