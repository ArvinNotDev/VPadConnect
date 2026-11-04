#ifndef ProductVersion
  #define ProductVersion "0.2.1-beta.3"
#endif
#ifndef ProductFileVersion
  #define ProductFileVersion "0.2.1.3"
#endif

#define AppExe "VPadConnect.exe"
#define ViGEmInstaller "ViGEmBus_1.22.0_x64_x86_arm64.exe"
#define ViGEmProductCode "{9C581C76-2D68-40F8-AA6F-94D3C5215C05}"

[Setup]
AppId={{B2D1D2D2-DA22-4DB3-9E9C-12D8191B0220}}
AppName=VPadConnect
AppVersion={#ProductVersion}
AppVerName=VPadConnect {#ProductVersion}
AppPublisher=VPadConnect
AppPublisherURL=https://github.com/ArvinNotDev/VPadConnect
AppSupportURL=https://github.com/ArvinNotDev/VPadConnect/issues
DefaultDirName={autopf}\VPadConnect
DefaultGroupName=VPadConnect
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
CloseApplications=yes
CloseApplicationsFilter=VPadConnect.exe
RestartApplications=no
RestartIfNeededByRun=no
AlwaysRestart=no
SetupIconFile=..\ui\assets\vpadconnect-icon.ico
UninstallDisplayIcon={app}\VPadConnect.exe
OutputDir=..\dist
OutputBaseFilename=VPadConnect-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#ProductFileVersion}
VersionInfoCompany=VPadConnect
VersionInfoDescription=VPadConnect Windows Installer
VersionInfoProductName=VPadConnect
VersionInfoProductVersion={#ProductFileVersion}
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\build\installer-support\vpadconnect.installed"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "Detect-ViGEmBus.ps1"; DestDir: "{tmp}"; Flags: dontcopy
Source: "Invoke-ViGEmBusInstall.ps1"; DestDir: "{tmp}"; Flags: dontcopy
Source: "..\build\vendor\{#ViGEmInstaller}"; DestDir: "{tmp}"; DestName: "{#ViGEmInstaller}"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\VPadConnect"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\VPadConnect"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch VPadConnect"; Flags: postinstall nowait skipifsilent runasoriginaluser

[Code]
const
  ViGEmNeedsRestart = 10;

var
  DriverRestartRequired: Boolean;
  DriverInstallFailed: Boolean;
  DriverInstallExitCode: Integer;
  FinishedMessageAdded: Boolean;

procedure InstallViGEmIfRequired();
var
  DriverPath: String;
  DetectionScriptPath: String;
  OrchestratorPath: String;
  PowerShellPath: String;
  Ran: Boolean;
begin
  ExtractTemporaryFile('Detect-ViGEmBus.ps1');
  ExtractTemporaryFile('Invoke-ViGEmBusInstall.ps1');
  ExtractTemporaryFile('{#ViGEmInstaller}');
  DriverPath := ExpandConstant('{tmp}\{#ViGEmInstaller}');
  DetectionScriptPath := ExpandConstant('{tmp}\Detect-ViGEmBus.ps1');
  OrchestratorPath := ExpandConstant('{tmp}\Invoke-ViGEmBusInstall.ps1');
  PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  WizardForm.StatusLabel.Caption := 'Installing the ViGEmBus virtual gamepad driver...';
  Ran := Exec(
    PowerShellPath,
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + OrchestratorPath +
      '" -DriverInstaller "' + DriverPath + '" -DetectionScript "' +
      DetectionScriptPath + '" -ProductCode "{#ViGEmProductCode}" -PowerShellPath "' +
      PowerShellPath + '"',
    '', SW_HIDE, ewWaitUntilTerminated, DriverInstallExitCode);

  if not Ran then
  begin
    DriverInstallExitCode := -1;
    DriverInstallFailed := True;
    exit;
  end;

  if DriverInstallExitCode = ViGEmNeedsRestart then
    DriverRestartRequired := True
  else if DriverInstallExitCode <> 0 then
    DriverInstallFailed := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    InstallViGEmIfRequired();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and DriverRestartRequired and
    not FinishedMessageAdded then
  begin
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10 + #13#10 +
      'Windows may need to restart before virtual XInput controllers are available. ' +
      'VPadConnect will not restart the computer automatically.';
    FinishedMessageAdded := True;
  end;
end;

procedure DeinitializeSetup();
begin
  if DriverInstallFailed then
    MsgBox(
      'VPadConnect was installed, but ViGEmBus could not be confirmed as ready ' +
      '(installer exit code ' + IntToStr(DriverInstallExitCode) + '). ' +
      'Virtual Xbox/XInput output will not work until ViGEmBus is installed or repaired. ' +
      'Mouse controls, hotkeys, and Web Companion remain available. ' +
      'See the ViGEmBus notice installed with VPadConnect for the official source.',
      mbError, MB_OK);
end;
