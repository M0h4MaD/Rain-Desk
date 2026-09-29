"""raindesk/core/paths.py

الغرض: تحديد مسارات الموارد وبيانات التطبيق بشكل موحّد ومستقل عن طريقة التشغيل.
المسؤوليات: مسار الموارد (من المصدر أو من حزمة PyInstaller)، ومجلدات AppData وLocalAppData،
    ومسار الإعدادات والسجلات مع إنشاء المجلدات عند الحاجة.
الاعتماديات: raindesk.core.constants والمكتبة القياسية.
النمط التصميمي: Facade بسيط فوق 'os.environ' و'pathlib'.
ملاحظات: المتغيرات تُقرأ عند كل استدعاء (لا تُخزَّن) ليسهل اختبارها بـ monkeypatch.
مثال: from raindesk.core.paths import settings_path
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

from raindesk.core.constants import APP_NAME, SETTINGS_FILENAME

_APPDATA_ENV: Final[str] = "APPDATA"  # متغير بيئة Windows للبيانات المتجولة (Roaming)
_LOCALAPPDATA_ENV: Final[str] = "LOCALAPPDATA"  # متغير بيئة Windows للبيانات المحلية
_APPDATA_FALLBACK: Final[tuple[str, ...]] = ("AppData", "Roaming")  # بديل إن غاب المتغير
_LOCALAPPDATA_FALLBACK: Final[tuple[str, ...]] = ("AppData", "Local")
_LOG_SUBDIR: Final[str] = "logs"
# مستوى الصعود من هذا الملف إلى جذر المشروع: paths.py -> core -> raindesk -> الجذر.
_PROJECT_ROOT_LEVELS_UP: Final[int] = 2


def _base_dir(env_name: str, fallback: tuple[str, ...]) -> Path:
    """يعيد مجلد الأساس من متغير بيئة، أو من مجلد المستخدم إن كان المتغير غائبًا أو فارغًا."""
    raw = os.environ.get(env_name)
    if raw:
        return Path(raw)
    return Path.home().joinpath(*fallback)


def _ensure_dir(path: Path) -> Path:
    """ينشئ المجلد (ومعه الأمّهات) إن لم يوجد؛ يرفع OSError إن تعذّر (صلاحيات، قرص ممتلئ)."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """مسار مورد نسبي يعمل من المصدر ومن حزمة PyInstaller.

    داخل الحزمة يفك PyInstaller الملفات إلى مجلد يضعه في 'sys._MEIPASS'؛ خارجها نعتمد
    جذر المشروع. الاستدعاء O(1) ولا يفحص وجود الملف.
    """
    meipass: object = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str):
        return Path(meipass) / relative
    root = Path(__file__).resolve().parents[_PROJECT_ROOT_LEVELS_UP]
    return root / relative


def app_data_dir() -> Path:
    """%APPDATA%/RainDesk (بيانات المستخدم: الإعدادات)، يُنشأ إن لم يوجد."""
    return _ensure_dir(_base_dir(_APPDATA_ENV, _APPDATA_FALLBACK) / APP_NAME)


def local_data_dir() -> Path:
    """%LOCALAPPDATA%/RainDesk (بيانات محلية لا تُزامَن: السجلات)، يُنشأ إن لم يوجد."""
    return _ensure_dir(_base_dir(_LOCALAPPDATA_ENV, _LOCALAPPDATA_FALLBACK) / APP_NAME)


def settings_path() -> Path:
    """مسار ملف الإعدادات: app_data_dir()/settings.json (الملف نفسه لا يُنشأ هنا)."""
    return app_data_dir() / SETTINGS_FILENAME


def log_dir() -> Path:
    """مجلد السجلات: local_data_dir()/logs، يُنشأ إن لم يوجد."""
    return _ensure_dir(local_data_dir() / _LOG_SUBDIR)