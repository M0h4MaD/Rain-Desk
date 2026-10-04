"""raindesk/platform_win/autostart.py

الغرض: التشغيل التلقائي مع تسجيل الدخول عبر مفتاح Run في سجل المستخدم الحالي (بلا صلاحيات مدير).
المسؤوليات: بناء أمر التشغيل (نسخة مجمّدة أو بيئة تطوير)، وقراءة الإدخال وكتابته وحذفه.
الاعتماديات: winreg (على Windows فقط) والمكتبة القياسية وraindesk.core.constants.
النمط التصميمي: Facade فوق winreg مع Null Object خارج Windows (تعيد قيمًا محايدة).
ملاحظات:
    المفتاح: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run، اسم القيمة 'RainDesk'.
    مجمّد: "<RainDesk.exe>" --minimized؛ تطوير: "<pythonw.exe>" "<main.py>" --minimized
    (pythonw لا يفتح نافذة طرفية). المسارات تُقتبس دائمًا لأنها قد تحوي مسافات.
    وجود القيمة في السجل هو مصدر الحقيقة لحالة launch_at_login في الواجهة.
    قيد معروف: إدخال عطّله المستخدم من تبويب Startup في مدير المهام يبقى في مفتاح Run.
مثال: autostart.set_enabled(True); autostart.is_enabled()
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Final

from raindesk.core.constants import RUN_KEY_PATH, RUN_VALUE_NAME

if sys.platform == "win32":
    import winreg

_LOG = logging.getLogger(__name__)

_MINIMIZED_FLAG: Final[str] = "--minimized"
_PYTHONW_NAME: Final[str] = "pythonw.exe"
_MAIN_SCRIPT: Final[str] = "main.py"
_PROJECT_ROOT_LEVELS_UP: Final[int] = 2  # autostart.py -> platform_win -> raindesk -> الجذر


def build_launch_command() -> str:
    """أمر التشغيل الذي يُكتب في السجل (مقتبس المسارات، ويبدأ مخفيًا في الشريط)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {_MINIMIZED_FLAG}'
    interpreter = Path(sys.executable)
    pythonw = interpreter.with_name(_PYTHONW_NAME)  # نفس مجلد المفسّر (داخل .venv\Scripts)
    if not pythonw.exists():
        pythonw = interpreter  # بديل: python.exe (قد تظهر نافذة طرفية)
    script = Path(__file__).resolve().parents[_PROJECT_ROOT_LEVELS_UP] / _MAIN_SCRIPT
    return f'"{pythonw}" "{script}" {_MINIMIZED_FLAG}'


def get_command(value_name: str = RUN_VALUE_NAME) -> str | None:
    """نص الأمر المخزَّن في السجل، أو None إن لم يوجد (أو خارج Windows)."""
    if sys.platform != "win32":
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_QUERY_VALUE
        ) as key:
            value, _kind = winreg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        return None  # المفتاح أو القيمة غير موجودين: التشغيل التلقائي معطّل
    except OSError as exc:
        _LOG.warning("cannot read the startup entry: %s", exc)
        return None
    return str(value)


def is_enabled(value_name: str = RUN_VALUE_NAME) -> bool:
    """True إذا كانت قيمة التشغيل التلقائي موجودة في السجل."""
    return get_command(value_name) is not None


def set_enabled(enabled: bool, value_name: str = RUN_VALUE_NAME) -> bool:
    """يكتب إدخال التشغيل التلقائي أو يحذفه؛ True عند النجاح (حذف غير الموجود نجاح أيضًا).

    لا يرفع استثناءً: الفشل (سياسة مؤسسية تمنع الكتابة مثلًا) يُسجَّل ويعيد False.
    """
    if sys.platform != "win32":
        return False
    try:
        if enabled:
            # CreateKeyEx تفتح المفتاح أو تنشئه إن غاب (لا يحدث عادةً لكنه أكثر متانة).
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, build_launch_command())
        else:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, value_name)
    except FileNotFoundError:
        return not enabled  # عند التعطيل: لا شيء لحذفه = معطّل أصلًا (نجاح)
    except OSError as exc:
        _LOG.warning("cannot update the startup entry: %s", exc)
        return False
    return True