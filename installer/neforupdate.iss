; NEFORUPDATE installer (Inno Setup 6) - made by Neforus (https://neforus.com)
; Build with release.cmd, which passes the version from neforupdate\__init__.py.
; Packages the folder build in dist\NEFORUPDATE-app (made from NEFORUPDATE-installer.spec).

#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif
#define AppName "NEFORUPDATE"
#define AppExe "NEFORUPDATE.exe"
#define AppPage "https://neforus.com/neforupdate"

[Setup]
; AppId identifies NEFORUPDATE across versions (upgrades, uninstall). Never change it.
AppId={{519A27CB-BBA4-47C4-92E4-9DB23DBE38EB}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Neforus
AppPublisherURL=https://neforus.com
AppSupportURL={#AppPage}
AppUpdatesURL={#AppPage}
AppCopyright=Made by Neforus
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany=Neforus
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoCopyright=Made by Neforus - neforus.com
; "Only for me" (no admin prompt, %LOCALAPPDATA%\Programs) or "All users" (Program Files): the user picks
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Close a running NEFORUPDATE before replacing its files
AppMutex=NEFORUPDATE_running
CloseApplications=yes
RestartApplications=no
SetupMutex=NEFORUPDATE_setup
OutputDir=..\dist
OutputBaseFilename=NEFORUPDATE-Setup-{#AppVersion}
SetupIconFile=..\assets\neforupdate.ico
; Open source: show the MIT licence in the wizard
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
; Show the branded welcome page (Inno Setup skips it by default)
DisableWelcomePage=no
WizardImageFile=wizard-large-164x314.bmp,wizard-large-192x386.bmp,wizard-large-246x459.bmp,wizard-large-273x556.bmp,wizard-large-328x604.bmp,wizard-large-355x700.bmp,wizard-large-410x797.bmp
WizardSmallImageFile=wizard-small-55x55.bmp,wizard-small-64x68.bmp,wizard-small-83x80.bmp,wizard-small-92x97.bmp,wizard-small-110x106.bmp,wizard-small-119x123.bmp,wizard-small-138x140.bmp
Compression=lzma2/ultra64
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nNEFORUPDATE finds pending updates from winget, the Microsoft Store, Chocolatey, Scoop and Windows Update, and installs the ones you pick with one click.%n%nFree and open source (MIT). Made by Neforus - neforus.com

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove files from an older version before copying the new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\NEFORUPDATE-app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Licence files next to the .exe, where people look for them
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\BRANDING.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
; AppUserModelID matches the app's own, so taskbar pins and the Start menu entry group together
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Neforus.NEFORUPDATE"; Comment: "Update every app on this PC"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Neforus.NEFORUPDATE"; Comment: "Update every app on this PC"; Tasks: desktopicon

[Registry]
; Win+R -> "neforupdate" opens the app
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// After uninstalling, offer to remove the user's settings, links and logs too. Silent uninstalls keep them.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if SuppressibleMsgBox('Also remove your NEFORUPDATE settings, linked apps and logs?',
         mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\NEFORUPDATE'), True, True, True);
      RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Neforus\NEFORUPDATE');
      RegDeleteKeyIfEmpty(HKEY_CURRENT_USER, 'Software\Neforus');
    end;
end;
