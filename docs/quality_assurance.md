# Quality assurance record

This file is the single place where RainDesk's quality evidence is recorded: automated checks,
the manual test matrix, the 60-minute endurance test and the benchmark table. Fill the empty
cells yourself on your own machine and commit the file; the report (docs/report.md) cites it.

## 0. Test environment (fill in)

| Item | Value |
|---|---|
| Date | 2026/10 |
| Machine (CPU, RAM, GPU) |  |
| Windows edition and build (`winver`) |  |
| Display setup (resolution, scaling, monitors) |  |
| Python (`python --version`) |  |
| PySide6 / NumPy versions (`pip freeze`) |  |
| ruff / mypy versions |  |
| Run from | source / packaged build |

## 1. Automated checks

Run from the project root with the virtual environment active (Windows PowerShell):

```powershell
ruff check .
ruff format --check .
mypy --strict raindesk/engine raindesk/config raindesk/core
pytest -q
```

**One-time normalization.** Files written before `pyproject.toml` existed may not match the
formatter (line length 100) or the import order. Run this once, review `git diff`, then re-run
the four commands above:

```powershell
ruff check --fix .
ruff format .
```

`ruff` rules are pinned in `pyproject.toml` (`E4 E7 E9 F I B UP`) because ruff's built-in
default set changes between releases. Line length is enforced by the formatter (100).
Tests marked `windows_only` are skipped on other systems, so a Windows run shows no extra skips
for them.

| Check | Expected | Result |
|---|---|---|
| `ruff check .` | All checks passed |  |
| `ruff format --check .` | already formatted |  |
| `mypy --strict ...` | Success: no issues found |  |
| `pytest -q` | all passed (Windows-only tests included on Windows) |  |

## 2. Manual test matrix

Mark **Result** with `PASS`, `FAIL` or `N/A` (hardware not available) and write what you saw in
**Notes**, especially for failures (screenshot file name, log excerpt from
`%LOCALAPPDATA%\RainDesk\logs\raindesk.log`).

| # | Test | Steps | Expected | Result | Notes |
|---|---|---|---|---|---|
| 1 | **Click-through** | Click desktop icons and type in Notepad while rain is visible. | Every click and keystroke reaches the app below; the overlay never takes focus. |  |  |
| 2 | **Hidden from switchers** | Press Alt+Tab; look at the taskbar. | The overlay appears in neither. |  |  |
| 3 | **Multi-monitor** | Plug and unplug a monitor; change primary; change resolution. | Overlays follow within 2 seconds without a restart. |  |  |
| 4 | **DPI** | Try 100, 125, 150 and 175 percent scaling at 1080p and 4K. | Rain covers the full screen with no gaps or blurry scaling. |  |  |
| 5 | **Sleep and resume** | Sleep the PC for 1 minute, then resume. | Rain resumes without a burst or freeze and stays on top. |  |  |
| 6 | **Full-screen pause** | Play a video in browser full screen (F11), and a PowerPoint slide show. | Rain pauses when the full-screen app is in front and returns when it exits; CPU about 0 while paused. |  |  |
| 7 | **Battery Saver** | Enable Battery Saver. | Rain pauses when the option is on. |  |  |
| 8 | **Taskbar and Start menu** | Use auto-hide taskbar, Start menu, notification area, with the overlay running. | All behave normally. |  |  |
| 9 | **Language and RTL** | Switch Arabic and English while the window is open. | Text and layout direction update live; no clipped text. |  |  |
| 10 | **Theme** | Switch light, dark and system; change the Windows theme while the app runs. | UI follows immediately; the title bar follows on supported builds. |  |  |
| 11 | **Persistence** | Change ten settings, quit from the tray, relaunch. | All values restored. |  |  |
| 12 | **Corrupt settings** | Damage settings.json with a text editor and launch. | Defaults load, a corrupt copy is kept, and a tray message appears once. |  |  |
| 13 | **Single instance** | Launch the app twice. | The second launch exits and the first shows the settings window. |  |  |
| 14 | **Autostart** | Enable Launch at login; sign out and in. | The app starts minimized in the tray; disabling removes the Run value. |  |  |
| 15 | **Capture exclusion** | Enable it and take a screenshot with the Snipping Tool. | The rain is absent in the capture (experimental); the option is disabled with a tooltip if unsupported. |  |  |
| 16 | **Endurance** | Run for 60 minutes. | Working set growth under 5 percent; no visible stutter. |  |  |
| 17 | **Sound quality** | Enable Sound; sweep intensity from 0 to 1 and the wind sliders; toggle the wind sound. | A continuous rain bed with individual drops; louder and denser with intensity; a soft whoosh that swells with gusts; no clicks or zipper noise. |  |  |
| 18 | **Sound pause and release** | Pause the rain (tray toggle, or a full-screen video). | The sound fades out within about 250 ms and the audio device is released after 2 seconds (the app disappears from the Windows volume mixer). |  |  |
| 19 | **Audio device change** | Plug and unplug headphones or change the default output while the sound plays. | Playback follows the new default device within about a second and the app does not crash. |  |  |

## 3. Endurance test (60 minutes)

```powershell
python tools/endurance_monitor.py
```

The tool starts `main.py`, samples the working set, private bytes and CPU every 10 seconds,
writes `endurance_<timestamp>.csv`, and prints a Markdown summary. Leave the machine idle with
the overlay visible and sound enabled at a moderate level. To monitor a build you started
yourself (for example the packaged exe), pass its process id: `--pid 1234`. Use `--minutes 15`
for a quick rehearsal (the verdict needs at least 15 minutes of samples).

Pass criterion: working-set growth under 5 percent between the median of minutes 5-10 and the
median of the last 5 minutes (the first 5 minutes are warm-up and ignored).

Paste the printed table here:

| Metric | Value |
|---|---|
| Samples |  |
| Baseline working set (median, minutes 5-10) |  |
| Final working set (median, last 5 minutes) |  |
| Growth |  |
| Result |  |

Also note whether any stutter was visible (the debug HUD can be enabled in Settings, Advanced).

## 4. Benchmarks

```powershell
python tools/bench_engine.py
```

The tool prints a Markdown table and writes `bench_results.csv` in the current folder (the CSV
is ignored by git; paste the table below). Other measurements:

* CPU: `typeperf "\Process(python)\% Processor Time" -si 1 -sc 300` (5 minutes), divide by the
  number of logical cores to compare with Task Manager's total.
* Working set: Task Manager, Details tab, "Memory (active private working set)" or the
  endurance CSV above.
* Frame timings: the in-app debug HUD.

Targets from the performance budget (reference machine: mid-range laptop, 4 cores, integrated
GPU, 1920x1080 at 125 percent scaling, Windows 11):

| Metric | Target | Measured | Within target? |
|---|---|---|---|
| CPU, steady state | <= 3 percent of total CPU (balanced quality, 30 FPS, intensity 0.5); <= 8 percent at intensity 1.0 and 60 FPS. |  |  |
| RAM (working set) | <= 150 MB when run from source; <= 180 MB packaged. |  |  |
| Startup to first frame | <= 2.5 s (onedir build). |  |  |
| Engine step | <= 1.0 ms at 1000 drops; <= 3.0 ms at 5000 drops. |  |  |
| Paint at 1080p | <= 6 ms at 1000 drops (balanced). |  |  |
| CPU while paused | About 0 percent: timers stopped and no repaint. |  |  |
| Audio CPU added | <= 1 percent of total CPU with sound on; RainSynth block time <= 0.5 ms per 20 ms block at intensity 1.0. |  |  |
| Audio first enable | <= 400 ms to generate the noise loops and the droplet bank. |  |  |

Benchmark table pasted from `tools/bench_engine.py`:

```text
(paste here)
```

## 5. Deviations and known limitations

List every target that was missed or test that failed, with the reason and the follow-up.

* 
