# Third-party notices

RainDesk is built on open-source software. This file lists what the **distributed application**
contains or links to, under which license, and where to get the license texts and the source
code. Development-only tools are listed separately because they are not shipped.

> This is engineering guidance prepared by the project author, **not legal advice**. If you
> redistribute RainDesk commercially, have a lawyer review the obligations below.

RainDesk's own license is not decided yet (until then, all rights are reserved by the author).
The licenses below apply to the third-party components only.

Exact versions are recorded in `requirements.lock.txt` (created with `pip freeze` after the
install). `requirements.txt` only gives the allowed ranges.

## 1. Components shipped in the application

| Component | Used as | License | Where to read it |
|---|---|---|---|
| Python (CPython 3.12) | Runtime embedded by PyInstaller | PSF License Agreement (Python Software Foundation License 2.0 and earlier PSF-compatible licenses) | `LICENSE.txt` in the Python installation folder; https://docs.python.org/3/license.html |
| PySide6 (Qt for Python) and Qt 6 | GUI, painting, tray icon, local sockets, audio output | LGPLv3 (also offered under GPLv3 and a commercial license; RainDesk uses the **LGPLv3** route) | https://www.qt.io/licensing ; LGPLv3 text: https://www.gnu.org/licenses/lgpl-3.0.html |
| shiboken6 | Python/C++ binding runtime installed together with PySide6 | Part of Qt for Python (see the license files in its `.dist-info` folder) | `site-packages\shiboken6-*.dist-info\` |
| NumPy | Vectorized particle state | BSD-3-Clause (the wheel also bundles third-party libraries with their own licenses) | `site-packages\numpy-*.dist-info\` (look for `LICENSE.txt` and the bundled-licenses file) |

### 1.1 Qt and PySide6 under the LGPLv3

RainDesk uses Qt and PySide6 **unmodified** and **dynamically linked**: the Qt libraries are
separate DLL files in the application folder (`onedir` build), and RainDesk's own code only
calls them through the public PySide6 API. To stay within the LGPLv3 the distribution must:

1. **Say that Qt is used and under which license** (this file, and the "Open-source licenses" card on the About page of the app).
2. **Include the LGPLv3 text and the GPLv3 text it refers to** in the `licenses\` folder next
   to the executable (see section 4).
3. **Let users replace the Qt libraries** with their own build of Qt of a compatible version:
   this is why the default package is `onedir` (a folder), where the Qt DLLs are ordinary
   files. The `onefile` variant packs them into a single archive, which makes this harder to
   demonstrate; prefer `onedir` for distribution.
4. **Not forbid reverse engineering for debugging** modifications of the Qt libraries (the
   RainDesk distribution adds no such restriction).
5. **Offer the corresponding source code of Qt and PySide6** (the exact version shipped), for
   example by linking to the official source archives:
   * Qt sources: https://download.qt.io/official_releases/qt/ (choose the version that matches
     the shipped PySide6; `pip show PySide6` prints it).
   * Qt for Python (PySide6) sources: https://code.qt.io/cgit/pyside/pyside-setup.git
   * Qt's own list of third-party code inside Qt and their licenses:
     https://doc.qt.io/qt-6/licenses-used-in-qt.html

Qt and the Qt logo are trademarks of The Qt Company Ltd. RainDesk is not affiliated with or
endorsed by The Qt Company.

### 1.2 QtMultimedia (sound) and FFmpeg

RainDesk's sound uses `QAudioSink` from QtMultimedia (output only; the microphone is never
opened). **Verify** whether the PySide6 wheel you build with ships FFmpeg libraries next to
QtMultimedia, because FFmpeg has its own license (LGPL v2.1 or later, or GPL depending on how
it was built):

```powershell
Get-ChildItem dist\RainDesk -Recurse -Include avcodec*.dll,avformat*.dll,avutil*.dll,swresample*.dll,swscale*.dll |
    Select-Object FullName
```

* If the command prints files, add an FFmpeg entry to this table and ship its license text
  (https://ffmpeg.org/legal.html explains which license applies to which build). The
  replaceable-DLL argument in 1.1 applies to these libraries as well.
* If it prints nothing, no FFmpeg notice is needed for this build.

(Not verified by the author at the time of writing; the result depends on the PySide6 version.)

### 1.3 Bundled libraries inside the NumPy wheel

Binary NumPy wheels include math libraries (for example an optimized BLAS) and compiler
runtime libraries, each with its own license. NumPy lists them in the license files inside its
`.dist-info` folder; copy those files into `licenses\` (section 4) instead of summarizing them
here.

## 2. Build tools that end up in the package

| Component | Role | License |
|---|---|---|
| PyInstaller | Freezes the app and provides the bootloader that starts it | GPLv2 **with a special exception for the bootloader**: applications built with PyInstaller may be distributed under any license (license text: `COPYING.txt` in the PyInstaller repository and in `site-packages\pyinstaller-*.dist-info\`) |

PyInstaller's license applies to PyInstaller itself; it does not make RainDesk a GPL program.

## 3. Development tools (not distributed)

| Tool | Purpose | License |
|---|---|---|
| pytest | Unit tests | MIT |
| ruff | Lint and format | MIT |
| mypy | Static typing | MIT |
| Pillow | Build the multi-size `.ico` from a PNG rendered by Qt (`tools/make_icon.py`) | HPND (MIT-CMU style) |
| Visual Studio Code, Git for Windows, Inno Setup | Editor, version control, optional installer builder | Free of charge; see each product's license |

Pillow is used only while building the icon; it is not part of the distributed application.

## 4. License files inside the distribution

The packaged folder must contain a `licenses\` directory with the full text of each license
above. `python tools/package.py` creates it: for NumPy, PySide6, shiboken6 and PyInstaller it
copies every `LICENSE*` / `COPYING*` / `NOTICE*` file found in the installed distribution
(`dist-info`), copies the Python (PSF) license from the interpreter's folder as
`PSF-LICENSE.txt`, and copies this file. It prints a warning if no LGPL text is present.

Then check by hand that the list contains at least the PSF license, a license file for
PySide6 and NumPy, and (for LGPLv3 compliance) the LGPLv3 and GPLv3 texts: PySide6 wheels do not
include them, so download https://www.gnu.org/licenses/lgpl-3.0.txt and
https://www.gnu.org/licenses/gpl-3.0.txt, save them as `licenses\LGPL-3.0.txt` and
`licenses\GPL-3.0.txt`, and re-create the ZIP with `python tools/package.py --skip-build`.
(The collection logic is tested on Linux; the PSF file and the Windows paths were not run on
Windows by the author.)

## 5. What RainDesk does not contain

* No image, font, sound or video assets: icons are drawn at run time and the rain sound is
  synthesized by code. System fonts (for example Segoe UI) are used from the user's Windows
  installation and are not redistributed.
* No telemetry, analytics or network libraries.

## 6. Supply-chain hygiene

Install dependencies only from the official PyPI index, pin the versions in
`requirements.lock.txt`, and (optional hardening) install with hash checking:
`pip install --require-hashes -r requirements.hashes.txt`, where the hash file is generated
with a tool such as pip-tools (`pip-compile --generate-hashes`). Publish the SHA-256 of every
release archive (`Get-FileHash <file> -Algorithm SHA256`) next to the download.
