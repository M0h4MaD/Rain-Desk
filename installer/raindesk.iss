; installer/raindesk.iss
; الغرض: مثبّت Inno Setup اختياري لـ RainDesk (بديل عن ملف ZIP). يثبّت لكل مستخدم بلا صلاحيات
;   مسؤول، ويضيف اختصار قائمة ابدأ، وخيارًا اختياريًا للتشغيل عند تسجيل الدخول.
; البناء:  1) python tools/package.py   2) iscc installer\raindesk.iss
;   الناتج: dist\installer\RainDesk-Setup-1.0.1.exe
; ملاحظات:
;   * يجب أن يطابق MyAppVersion الإصدار في raindesk/core/constants.py (يتحقق tests/test_packaging.py).
;   * أمر التشغيل التلقائي مطابق لما يكتبه التطبيق نفسه: "<exe>" --minimized بمسار مقتبس.
;   * الحذف يزيل قيمة Run دائمًا (حتى لو فعّلها المستخدم من إعدادات التطبيق لا من المثبّت)،
;     ولا يحذف الإعدادات في %APPDATA%\RainDesk (بيانات المستخدم).
;   * لم يُجرَّب على Windows ضمن هذا المشروع: انظر قائمة التحقق في docs/packaging.md.

#define MyAppName "RainDesk"
#define MyAppVersion "1.0.1"
#define MyAppExe "RainDesk.exe"

[Setup]
AppId={{E7015B26-BC07-4F27-99C4-BEF01BE48B12}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
SetupIconFile=..\assets\raindesk.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "autostart"; Description: "Start RainDesk when I sign in"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExe}"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { حذف قيمة التشغيل التلقائي مهما كان مصدرها (المثبّت أو إعدادات التطبيق) }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
end;
