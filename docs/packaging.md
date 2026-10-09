# Packaging RainDesk (M11)

RainDesk ships as a **folder build** (`onedir`): `RainDesk.exe` next to its Qt libraries. A ZIP of
that folder is the primary deliverable; an Inno Setup installer is optional.

## Build

```powershell
.venv\Scripts\activate
pip install -r requirements-dev.txt
python tools/package.py                 # icon -> PyInstaller -> licenses -> ZIP + SHA-256
python tools/package.py --no-sound      # smaller build without QtMultimedia (no rain sound)
iscc installer\raindesk.iss             # optional installer (needs Inno Setup 6)
```

`tools/package.py` writes `dist\RainDesk\`, `dist\RainDesk-1.0.0-win64.zip` and prints the
SHA-256. It warns if no LGPL text is in `dist\RainDesk\licenses\` (PySide6 wheels do not include
it): download `lgpl-3.0.txt` and `gpl-3.0.txt` from gnu.org and copy them there, then re-zip with
`python tools/package.py --skip-build`.

## Decisions

| Choice | Reason |
|---|---|
| `onedir`, not `onefile` | `onefile` unpacks hundreds of MB to `%TEMP%` on every start (slow start, more antivirus false positives); with `onedir` the Qt DLLs stay replaceable files, as the LGPL requires. |
| `console=False` | No console window. `logging_setup` adds no console handler when frozen, so a missing `sys.stdout` cannot break logging (checked in the frozen Linux build). |
| `upx=False` | UPX raises antivirus detections and can corrupt Qt files. |
| `datas=[]` | Nothing is read from disk at run time: UI, Drip and the tray icon are drawn in code. Only the `.ico` is used at build time. |
| Explicit `hiddenimports=["PySide6.QtMultimedia"]` | The sound code imports it lazily, so static analysis can miss it. `RAINDESK_NO_SOUND=1` removes it. |
| Excluded Qt modules | WebEngine, Qml/Quick, Pdf, Sql, Svg, ... (the list is in `raindesk.spec`; a test fails if the spec excludes a Qt module the app imports). |
| Per-user installer (`PrivilegesRequired=lowest`) | No administrator prompt; everything the app writes is in the user's `%APPDATA%` / `%LOCALAPPDATA%` anyway. |

Autostart is the same command everywhere: `"<full path>\RainDesk.exe" --minimized` under
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value `RainDesk`. The installer's optional
task writes exactly this, and uninstalling removes the value even if the user enabled it from the
app's settings.

## What was verified, and where

| Check | Result | Where |
|---|---|---|
| `pyinstaller raindesk.spec` builds; the frozen `RainDesk --selftest` exits 0, writes `settings.json` and `raindesk.log`; path containing spaces | passed | Linux, offscreen (container) |
| Build size (Linux, indicative only) | 245 MB folder / 154 MB ZIP with sound; 217 MB folder without | Linux |
| Spec/installer/version consistency, license collection, ZIP layout, icon sizes (7 sizes, 16-256) | passed (12 tests in `tests/test_packaging.py`) | Linux |
| Windows `.exe`, icon in Explorer/taskbar, version tab, tray, click-through, sound, autostart | **not run** | needs Windows |
| Inno Setup script compiles and installs | **not run** | needs Windows |

Linux sizes are not Windows sizes (different Qt platform plugins and system libraries); record the
Windows numbers in the table below.

## Windows verification checklist (do once per release)

1. `python tools/package.py` finishes without error; note the ZIP size and SHA-256.
2. Extract the ZIP to a path **with a space** (`C:\Temp\Rain Desk Test\`) and run `RainDesk.exe`:
   no console window, tray icon appears, rain shows, `%LOCALAPPDATA%\RainDesk\logs\raindesk.log`
   has "RainDesk started".
3. Explorer shows the drop icon on `RainDesk.exe`; Properties > Details shows version 1.0.0.0.
4. Turn on "launch at login" in Settings; in `regedit` the Run value is
   `"C:\Temp\Rain Desk Test\RainDesk.exe" --minimized` (quoted); sign out and in: RainDesk
   starts in the tray only.
5. Rain sound toggles on and off in the packaged build (QtMultimedia present). With `--no-sound`
   the sound controls must not crash the app.
6. Run on a machine **without Python installed** (clean VM or Windows Sandbox).
7. Windows Security reports no detection; if SmartScreen warns, that is expected for unsigned
   software (publish the SHA-256).
8. Installer (optional): installs without an administrator prompt, Start Menu shortcut works,
   "Start when I sign in" task writes the Run value, uninstall removes the program folder and
   the Run value but leaves `%APPDATA%\RainDesk\settings.json`.

| Build | Folder size | ZIP size | Cold start to tray (s) | Notes |
|---|---|---|---|---|
| with sound | | | | |
| `--no-sound` | | | | |
