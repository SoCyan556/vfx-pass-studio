#ifndef SourceDir
  #define SourceDir ".."
#endif
#define AppVersion "0.4.0"
[Setup]
AppId={{A1A1EE05-8CA5-482A-9450-F956A3F24CF8}
AppName=VFX Pass Studio
AppVersion={#AppVersion}
AppPublisher=SoCyan556
AppPublisherURL=https://github.com/SoCyan556/vfx-pass-studio
DefaultDirName={localappdata}\Programs\VFX Pass Studio
DefaultGroupName=VFX Pass Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#SourceDir}\dist
OutputBaseFilename=VFX-Pass-Studio-Setup-{#AppVersion}
SetupIconFile={#SourceDir}\ui\assets\vfx-pass-studio.ico
UninstallDisplayIcon={app}\VFX Pass Studio.exe
LicenseFile={#SourceDir}\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
AppMutex=VFXPassStudioInstaller
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "{#SourceDir}\build\stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\VFX Pass Studio"; Filename: "{app}\VFX Pass Studio.exe"; WorkingDir: "{app}"; AppUserModelID: "SoCyan.VFXPassStudio"
Name: "{group}\Repair runtime"; Filename: "{app}\VFX Pass Studio.exe"; Parameters: "--setup"; WorkingDir: "{app}"
Name: "{autodesktop}\VFX Pass Studio"; Filename: "{app}\VFX Pass Studio.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "SoCyan.VFXPassStudio"
[Run]
Filename: "{app}\VFX Pass Studio.exe"; Description: "Set up the AI runtime and open VFX Pass Studio"; Flags: nowait postinstall skipifsilent
