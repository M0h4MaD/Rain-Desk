# RainDesk

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-informational)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)

A free, lightweight rain overlay for Windows. Rain, wind, thunder and a small mascot (Drip) play
on top of your desktop while every click and keystroke still reaches the programs underneath.
Written in Python with PySide6 (Qt 6) and NumPy. No network access, no telemetry.

<!-- Drag your demo video (MP4, under 10 MB) into the GitHub editor here; it will insert a link. -->

*(ملخص بالعربية في آخر الملف.)*

## Download

Grab the latest `RainDesk-<version>-win64.zip` from the
[Releases](https://github.com/M0h4MaD/Rain-Desk/releases) page, unzip it anywhere and run
`RainDesk.exe`. No installer is needed. The SHA-256 of each zip is listed in the release notes.

> **Tested on Windows 10 only so far.** The executable is not code-signed, so SmartScreen may
> show an "unknown publisher" warning (More info, then Run anyway). Reports from Windows 11 and
> from multi-monitor setups with mixed DPI are very welcome: please open an issue.

Prefer to run it from source? See [Run from source](#run-from-source).

## Features

**Rain and weather**
* Rain drawn on every selected monitor, tuned by intensity, speed, drop length, thickness,
  opacity, wind angle and gusts. Five presets (drizzle, light, moderate, heavy, storm) and a
  *Randomize* button.
* Splashes where drops land (along the bottom edge, or spread over a depth plane), rain streams
  running down the screen edges, and an optional colour mood tint.
* **Auto weather**: a small state machine drifts between the presets so the weather changes
  by itself (variability is adjustable).
* **Realistic depth and wind**: near drops are long and fast, far drops short and faint, and
  wind arrives in gusts instead of one constant slant.
* **Water streams on the screen edges**: drops grow, stick, slide, merge and leave wet trails.
* **Lightning** with a brightness cap and a flash-rate limit (off by default); it is forced off
  when Windows animations are disabled (light-sensitivity friendly). Thunder follows the flash
  after a delay that depends on how close it was.
* **Sound**: rain, wind and thunder are synthesized live, so there are no audio files. Wind and
  thunder have their own volume sliders. It follows intensity and wind, fades out when the rain
  pauses and releases the audio device when idle. Output only: the microphone is never opened.

**Drip, the mascot**
* A small water drop that now and then walks along the top of the taskbar, jumps, dances,
  spins, waves, yawns and naps, catches raindrops with its mouth and shivers in a storm.
* It reacts to your mouse pointer without ever blocking it: its eyes follow the pointer,
  it comes over and waves when you rest the pointer near the taskbar, runs after the pointer
  when you play with it, enjoys being petted when you wiggle the pointer over it, and jumps
  when lightning flashes or the pointer rushes at it.
* Frequency and size are adjustable; when disabled it costs nothing. On the first run it starts
  disabled if Windows animations are off.

**Windows integration**
* Always on top, click-through, hidden from Alt+Tab and the taskbar, one window per monitor,
  follows monitor changes, DPI aware.
* Tray icon, single instance (a second launch opens the settings of the first), optional
  *Launch at login* (one `Run` value under `HKCU`), pauses for full-screen apps and Battery
  Saver (both can be switched off) and while the session is locked.
* Optional: cover the taskbar, keep re-asserting topmost, exclude the overlay from screenshots
  (experimental; the option is disabled with a tooltip if unsupported).

**Interface**: English and Arabic with live switching and right-to-left layout, light, dark and
system themes, an adaptive quality mode that lowers the drop count if frames get slow, and an
optional debug HUD.

## Requirements

* Windows 10 or 11, 64-bit.
* Python 3.12 (64-bit) from python.org, with *Add python.exe to PATH* ticked.
* Several hundred MB of disk space for the virtual environment (PySide6 is large).

## Run from source

Windows PowerShell, from the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt        # or requirements.txt if you only want to run it
python main.py
```

If PowerShell refuses to run the activation script, allow it for your user once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

After the first successful install, freeze the exact versions (this file becomes the source of
truth for reproducible installs and for `THIRD_PARTY_NOTICES.md`):

```powershell
python -m pip freeze | Out-File requirements.lock.txt -Encoding ascii
```

Command-line options:

| Option | Meaning |
|---|---|
| `--minimized` | Start in the tray without opening the settings window |
| `--selftest` | Start, log, and quit after 1 second (smoke test) |
| `--selftest-seconds N` | Run normally for N seconds, then quit |

## Using RainDesk

* **Tray icon**: click to open the settings. The menu has *Open settings*, *Show rain*,
  *Sound*, *Randomize*, *Presets* and *Quit*.
* **Settings pages**: General, Rain and Wind, Effects, Mascot, Display and Performance,
  Advanced, About (open-source licenses are listed there). Changes apply immediately and are
  saved automatically.

## Where RainDesk keeps its data

| What | Where |
|---|---|
| Settings | `%APPDATA%\RainDesk\settings.json` |
| Damaged settings (kept for inspection) | `%APPDATA%\RainDesk\settings.corrupt-YYYYMMDD-HHMMSS.json` |
| Log (1 MB, 3 rotated copies) | `%LOCALAPPDATA%\RainDesk\logs\raindesk.log` |
| Autostart | One value named `RainDesk` under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, only while *Launch at login* is on |

To reset everything, quit RainDesk and delete the `RainDesk` folders above.

## Privacy

No telemetry, no network access, no clipboard access, no keyboard or mouse hooks, no screen
capture. The mouse position is only *read* so that Drip can look at it. The only registry write
is the autostart value above. Audio is output only. Logs contain application events and file
paths, no personal data.

## Troubleshooting

| Symptom | What to check |
|---|---|
| No rain | The tray menu *Show rain* is on; no full-screen app is in front; Battery Saver is off or the pause option is disabled; read the log. |
| No tray icon | The tray may be hidden in the overflow area. If Windows reports no tray at all, the settings window stays open with a message and closing it quits the app. |
| Sound controls are greyed out | No audio output device was found, or QtMultimedia is missing. Plug a device in; the controls come back by themselves. |
| Rain on the wrong monitor | Display and Performance page: choose primary, all, or selected screens. |
| Lightning never happens | It is off when Windows animation effects are off (Windows Accessibility settings). |
| High CPU | Lower *Quality*, the FPS cap or the intensity, or enable *Adaptive quality*. |
| SmartScreen says "unknown publisher" (packaged build) | The executable is not code-signed. Compare the SHA-256 of the download with the one in the release notes, then choose *More info*, *Run anyway*. |
| Rain does not show over a full-screen game | By default RainDesk pauses for full-screen apps; switch that option off to keep it showing. Games in exclusive full-screen mode may still cover the overlay (not tested). |

## Development

```powershell
ruff check .
ruff format --check .
mypy --strict raindesk/engine raindesk/config raindesk/core
pytest -q
```

If the formatter or import order complains on an older checkout, normalize once with
`ruff check --fix .` and `ruff format .`, then review `git diff`. The tool settings live in
`pyproject.toml`. Tests that need Win32 or the registry are marked `windows_only` and are
skipped on other systems; Qt tests run on the offscreen platform (set in `tests/conftest.py`).

Benchmarks and the long-run test:

```powershell
python tools/bench_engine.py              # engine and paint timings, writes bench_results.csv
python tools/endurance_monitor.py         # 60-minute memory growth test (see docs\quality_assurance.md)
```

`docs/quality_assurance.md` holds the manual test matrix, the endurance and benchmark records.
`docs/report.md` is a technical report (in Arabic, with English technical terms) covering the
design, the math, the architecture and the measurements. The benchmark results quoted there
(Windows 10, 12 logical cores) are in `bench_results.csv`: the simulation step is about 0.05 ms at
1000 drops, and painting is the real cost (about 8.4 ms at 1000 drops with anti-aliasing at 1080p,
3.6 ms without). Anti-aliasing is off in the *Low* quality profile.

### Layout

```text
main.py                     entry point (calls raindesk.app.bootstrap.main)
raindesk/
  core/                     constants, paths, logging, single-instance guard
  config/                   settings schema, validation, atomic JSON store
  engine/                   simulation without Qt: rain, splashes, edge streams, weather,
                            adaptive quality, sound synthesis, the mascot (Drip)
  platform_win/             Win32 helpers, autostart, system watcher
  i18n/                     English and Arabic strings, translator
  ui/                       overlay windows, painters, tray, settings window and pages,
                            audio player (QtMultimedia), mascot host
  app/                      composition root (bootstrap) and AppController
tools/                      benchmarks, endurance monitor, icon tool, packaging script
tests/                      pytest suite
docs/                       quality records and the technical report (report.md)
```

Dependencies point one way: `ui -> app -> engine / config / platform_win / i18n -> core`.
`engine/`, `config/schema.py` and the Win32 helpers never import PySide6, so they are tested
without a display. Every long-lived object has an explicit `shutdown()`; the simulation runs
on the GUI thread, driven by one frame clock. The only worker thread builds the sound
synthesizer (noise loops and thunder samples) so that enabling sound never freezes the UI.

## Build a distributable

```powershell
python tools/package.py                  # icon, PyInstaller build, licenses, zip and SHA-256
python tools/package.py --no-sound       # variant without QtMultimedia
python tools/package.py --skip-build     # re-zip after adding files to dist\RainDesk
iscc installer\raindesk.iss              # optional installer (needs Inno Setup 6)
```

The default is a folder build (`onedir`): faster start, fewer antivirus false positives, and the
Qt libraries stay replaceable files, which the LGPL requires. Copy the license texts into
`dist\RainDesk\licenses\` as described in `THIRD_PARTY_NOTICES.md`, then re-zip with
`--skip-build`. More detail and the Windows checklist are in `docs/packaging.md`.

## Third-party software and license

RainDesk uses Python, PySide6 (Qt for Python, LGPLv3), NumPy (BSD-3-Clause) and, for building,
PyInstaller. See `THIRD_PARTY_NOTICES.md`.

RainDesk itself is released under the [MIT License](LICENSE).

---

## ملخص بالعربية

**RainDesk** تطبيق خفيف لنظام Windows 10 و11 يعرض مطرًا ورياحًا وبرقًا ورعدًا وصوت مطر فوق سطح
المكتب، مع شخصية صغيرة اسمها **Drip** تمشي فوق شريط المهام وتلعب مع مؤشر الفأرة. النافذة
شفافة وتمرّر كل النقرات والكتابة إلى البرامج تحتها، ولا تظهر في Alt+Tab أو شريط المهام.

* **التنزيل**: من صفحة Releases حمّل ملف `RainDesk-<version>-win64.zip` وفُكّه وشغّل `RainDesk.exe`.
* **التشغيل من المصدر**: ثبّت Python 3.12 (64 بت)، ثم في PowerShell:
  `py -3.12 -m venv .venv` ثم `.\.venv\Scripts\Activate.ps1` ثم
  `pip install -r requirements-dev.txt` ثم `python main.py`.
* **الإعدادات** في `%APPDATA%\RainDesk\settings.json` والسجلات في
  `%LOCALAPPDATA%\RainDesk\logs\raindesk.log`.
* **الخصوصية**: لا اتصال بالشبكة ولا تتبّع ولا التقاط للشاشة ولا مراقبة للوحة المفاتيح أو
  الفأرة؛ موضع المؤشر يُقرأ فقط لتنظر إليه Drip. الصوت للإخراج فقط.
* **فحوص الجودة**: `ruff check .` و`ruff format --check .` و
  `mypy --strict raindesk/engine raindesk/config raindesk/core` و`pytest -q`
  (نفّذ `ruff check --fix .` و`ruff format .` مرة واحدة إن لزم التنسيق).
* **سجل الاختبارات اليدوية والتحمّل والأداء**: `docs/quality_assurance.md`.
* **التراخيص**: المشروع نفسه بترخيص MIT (ملف `LICENSE`). والمكتبات الخارجية في
  `THIRD_PARTY_NOTICES.md` (PySide6/Qt بترخيص LGPLv3 وربط ديناميكي).
