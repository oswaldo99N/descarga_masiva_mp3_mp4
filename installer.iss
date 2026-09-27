#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{9D6D923D-57CB-496F-A725-5B963D097F3A}
AppName=Nexo Descargas
AppVersion={#AppVersion}
AppVerName=Nexo Descargas {#AppVersion}
DefaultDirName={localappdata}\Programs\Nexo Descargas
DefaultGroupName=Nexo Descargas
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\installer
OutputBaseFilename=Nexo-Descargas-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\logo.ico
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Nexo Descargas
UninstallDisplayIcon={app}\NexoDescargas.exe

[Files]
Source: "dist\NexoDescargas\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\GPL-3.0.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\logo.ico"; DestDir: "{app}"; DestName: "NexoDescargas.ico"; Flags: ignoreversion

[Icons]
Name: "{group}\Nexo Descargas"; Filename: "{app}\NexoDescargas.exe"; IconFilename: "{app}\NexoDescargas.ico"; AppUserModelID: "Oswaldo.NexoDescargas"
Name: "{autodesktop}\Nexo Descargas"; Filename: "{app}\NexoDescargas.exe"; IconFilename: "{app}\NexoDescargas.ico"; AppUserModelID: "Oswaldo.NexoDescargas"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Run]
Filename: "{app}\NexoDescargas.exe"; Description: "Abrir Nexo Descargas"; Flags: nowait postinstall skipifsilent
