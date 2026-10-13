# RainDesk 1.0.0

A free, open-source rain overlay for Windows. Rain, wind, thunder and a small mascot play on top
of your desktop while your clicks and typing go straight through to the apps underneath.

## Highlights
- Rain with depth, wind gusts, splashes and water streams sliding down the screen edges.
- Rain, wind and thunder are synthesized live (no audio files), with separate wind and thunder sliders.
- Optional lightning (off by default, brightness and flash-rate limited) with delayed thunder.
- Drip, a small mascot that reacts to your mouse pointer.
- Multi-monitor, tray icon, launch at login, pauses for full-screen apps, English and Arabic (RTL).
- No network access, no telemetry.

## Download
`RainDesk-1.0.0-win64.zip`: unzip anywhere and run `RainDesk.exe`.

SHA-256: `PASTE-THE-HASH-HERE`

Check it in PowerShell:
```powershell
Get-FileHash .\RainDesk-1.0.0-win64.zip -Algorithm SHA256
```

## Known limitations
- Tested on Windows 10 only. Windows 11 and mixed-DPI multi-monitor reports are welcome.
- The executable is not code-signed, so SmartScreen may warn: More info, then Run anyway.
- Painting is the main cost: about 8.4 ms per frame at 1000 drops with anti-aliasing at 1080p
  on the test machine (3.6 ms without). The *Low* quality profile turns anti-aliasing off.
- Sound starts about a second after you first enable it (the synthesizer is built in the background).

License: MIT.
