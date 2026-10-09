# -*- mode: python ; coding: utf-8 -*-
"""raindesk.spec

الغرض: وصفة PyInstaller التي تبني RainDesk كمجلد onedir (RainDesk.exe + مكتبات Qt بجانبه).
المسؤوليات: نقطة الدخول main.py، تطبيق الأيقونة ومعلومات الإصدار، تعطيل نافذة الطرفية
    (console=False)، واستبعاد ما لا يحتاجه التطبيق لتصغير الحجم.
ملاحظات التصميم:
  * onedir لا onefile: لا فكّ لمئات الميغابايتات في %TEMP% عند كل إقلاع (إقلاع أسرع وأقل
    إنذارات من مضادات الفيروسات)، ويبقى Qt كمكتبات DLL مستقلة يمكن استبدالها كما تشترط LGPL.
  * upx=False: ضغط UPX يضاعف إنذارات مضادات الفيروسات ويكسر ملفات Qt أحيانًا.
  * QtMultimedia (صوت المطر) يُستورد كسولًا داخل raindesk/ui/audio فلا يراه التحليل الساكن
    دائمًا؛ لذلك يُضاف صراحةً إلا إن عُرّفت RAINDESK_NO_SOUND=1 (نسخة أصغر بلا صوت).
  * لا ملفات بيانات (datas فارغة): الواجهة والشخصية والأيقونة المصغّرة كلها تُرسم بالكود.
الاستعمال:
    pyinstaller raindesk.spec --noconfirm --clean
    set RAINDESK_NO_SOUND=1 && pyinstaller raindesk.spec --noconfirm --clean   (بلا صوت)
"""

import os

block_cipher = None

NO_SOUND = os.environ.get("RAINDESK_NO_SOUND") == "1"

# حزم Qt التي لا يستعملها التطبيق إطلاقًا (تقليل الحجم؛ التطبيق يستعمل Core وGui وWidgets
# وNetwork، ومعها Multimedia للصوت فقط).
EXCLUDED_QT = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtSensors",
    "PySide6.QtPositioning",
    "PySide6.QtNfc",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSerialPort",
    "PySide6.QtTextToSpeech",
    "PySide6.QtXml",
    "PySide6.QtConcurrent",
    "PySide6.QtDBus",
]
if NO_SOUND:
    EXCLUDED_QT += ["PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets"]

EXCLUDES = [
    "tkinter",
    "pytest",
    "unittest",
    "pydoc",
    "doctest",
    "PIL",
    "mypy",
    "ruff",
] + EXCLUDED_QT
HIDDEN_IMPORTS = [] if NO_SOUND else ["PySide6.QtMultimedia"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: المكتبات تذهب إلى COLLECT لا داخل الملف التنفيذي
    name="RainDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # تطبيق نوافذ: لا نافذة طرفية (logging_setup لا يضيف طرفية عند التجميد)
    icon="assets/raindesk.ico",
    version="version_info.txt",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RainDesk",
)
