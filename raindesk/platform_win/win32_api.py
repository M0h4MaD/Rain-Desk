"""raindesk/platform_win/win32_api.py

الغرض: غلاف رقيق فوق واجهات Windows (عبر ctypes) يعزل كل كود النظام في مكان واحد.
المسؤوليات: تثبيت النافذة فوق الأخرى، وتمرير النقرات، واستثناء النافذة من التقاط الشاشة،
    وشريط عنوان داكن، وحالة ملء الشاشة، وموفّر البطارية، وإعداد الرسوم المتحركة.
الاعتماديات: المكتبة القياسية (ctypes) فقط؛ لا PySide6.
النمط التصميمي: Facade مع Null Object (على غير Windows أو عند الفشل تعود قيمة محايدة).
ملاحظات ctypes: نعرّف argtypes وrestype لكل دالة، وإلا تُبتر المقابض (handles) على Python
    64 بت. لا ترفع أي دالة عامة استثناءً؛ الفشل يعيد False أو قيمة محايدة ويُسجَّل مرة واحدة.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from enum import IntEnum
from typing import Any, Final

_LOG = logging.getLogger(__name__)
_LOGGED_KEYS: set[str] = set()  # مفاتيح رسائل سُجّلت سابقًا (لمنع تكرار التحذير كل إطار)


class UserNotificationState(IntEnum):
    """قيم QUERY_USER_NOTIFICATION_STATE كما في shellapi.h."""

    UNKNOWN = 0  # قيمة محلية: تعذّر الاستعلام
    NOT_PRESENT = 1  # جلسة مقفلة أو شاشة توقف
    BUSY = 2  # تطبيق بملء الشاشة
    RUNNING_D3D_FULL_SCREEN = 3  # لعبة Direct3D بملء الشاشة حصريًا
    PRESENTATION_MODE = 4  # وضع العرض التقديمي
    ACCEPTS_NOTIFICATIONS = 5  # الحالة العادية
    QUIET_TIME = 6  # ساعات التركيز
    APP = 7  # تطبيق UWP بملء الشاشة


# ثوابت Win32 (أسماؤها كما في winuser.h لتسهيل مراجعتها في التوثيق الرسمي).
_GWL_EXSTYLE: Final[int] = -20  # فهرس النمط الموسّع للنافذة
_WS_EX_TRANSPARENT: Final[int] = 0x00000020  # النقرات تمر إلى النافذة التي تحتها
_WS_EX_TOOLWINDOW: Final[int] = 0x00000080  # بلا زر في شريط المهام ولا في Alt+Tab
_WS_EX_LAYERED: Final[int] = 0x00080000  # نافذة بشفافية لكل بكسل
_WS_EX_NOACTIVATE: Final[int] = 0x08000000  # لا تصبح النافذة الأمامية أبدًا
_CLICK_THROUGH_STYLES: Final[int] = (
    _WS_EX_TRANSPARENT | _WS_EX_LAYERED | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW
)
_HWND_TOPMOST: Final[int] = -1  # قيمة المقبض الخاصة "فوق كل النوافذ"
_SWP_NOSIZE: Final[int] = 0x0001
_SWP_NOMOVE: Final[int] = 0x0002
_SWP_NOZORDER: Final[int] = 0x0004
_SWP_NOACTIVATE: Final[int] = 0x0010
_SWP_FRAMECHANGED: Final[int] = 0x0020  # يعيد قراءة النمط بعد تغييره
_WDA_NONE: Final[int] = 0x00000000
_WDA_EXCLUDEFROMCAPTURE: Final[int] = 0x00000011  # يتطلب Windows 10 بناء 19041 فأعلى
_MIN_BUILD_EXCLUDE_FROM_CAPTURE: Final[int] = 19041
_DWMWA_USE_IMMERSIVE_DARK_MODE: Final[int] = 20  # القيمة الرسمية (Windows 10 20H1 فأحدث)
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD: Final[int] = 19  # قيمة غير موثّقة في بناءات أقدم
_SPI_GETCLIENTAREAANIMATION: Final[int] = 0x1042
_BATTERY_SAVER_ON: Final[int] = 1  # SystemStatusFlag عند تفعيل موفّر البطارية
_S_OK: Final[int] = 0  # HRESULT للنجاح
_POINTER_SIZE_64: Final[int] = 8  # بايت: حجم المؤشر في Python 64 بت


class _SystemPowerStatus(ctypes.Structure):
    """SYSTEM_POWER_STATUS: DWORD بحجم 32 بت على Windows، لذلك c_uint32."""

    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_uint32),
        ("BatteryFullLifeTime", ctypes.c_uint32),
    ]


def _log_once(key: str, message: str, *args: object) -> None:
    """يسجّل تحذيرًا مرة واحدة لكل مفتاح."""
    if key not in _LOGGED_KEYS:
        _LOGGED_KEYS.add(key)
        _LOG.warning(message, *args)


def _bind(dll: Any, name: str, argtypes: list[Any], restype: Any) -> Any:
    """يجلب دالة من DLL ويضبط argtypes وrestype؛ يعيد None إذا كانت غير موجودة (Windows قديم)."""
    try:
        func = getattr(dll, name)
    except AttributeError:
        _log_once(f"missing:{name}", "Win32 function not available: %s", name)
        return None
    func.argtypes = argtypes
    func.restype = restype
    return func


# دوال النظام المربوطة (تبقى None خارج Windows أو إذا غابت الدالة).
_set_window_pos: Any = None
_get_window_long: Any = None
_set_window_long: Any = None
_set_display_affinity: Any = None
_system_parameters_info: Any = None
_dwm_set_window_attribute: Any = None
_query_notification_state: Any = None
_get_system_power_status: Any = None


def _load_win32() -> None:
    """يربط الدوال مرة واحدة عند الاستيراد؛ على غير Windows لا يفعل شيئًا."""
    global _set_window_pos, _get_window_long, _set_window_long, _set_display_affinity
    global _system_parameters_info, _dwm_set_window_attribute
    global _query_notification_state, _get_system_power_status
    if sys.platform != "win32":
        return
    from ctypes import wintypes

    long_ptr = ctypes.c_ssize_t  # LONG_PTR: بحجم المؤشر
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    except OSError as exc:  # لا يحدث عمليًا على Windows سليم
        _log_once("dll-load", "cannot load system DLLs: %s", exc)
        return
    _set_window_pos = _bind(
        user32, "SetWindowPos",
        [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
         wintypes.UINT],
        wintypes.BOOL,
    )
    is_64 = ctypes.sizeof(ctypes.c_void_p) == _POINTER_SIZE_64
    _get_window_long = _bind(  # على 32 بت لا يُصدَّر GetWindowLongPtrW (ماكرو فقط)
        user32, "GetWindowLongPtrW" if is_64 else "GetWindowLongW",
        [wintypes.HWND, ctypes.c_int], long_ptr,
    )
    _set_window_long = _bind(
        user32, "SetWindowLongPtrW" if is_64 else "SetWindowLongW",
        [wintypes.HWND, ctypes.c_int, long_ptr], long_ptr,
    )
    _set_display_affinity = _bind(
        user32, "SetWindowDisplayAffinity", [wintypes.HWND, wintypes.DWORD], wintypes.BOOL
    )
    _system_parameters_info = _bind(
        user32, "SystemParametersInfoW",
        [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT], wintypes.BOOL,
    )
    _query_notification_state = _bind(
        shell32, "SHQueryUserNotificationState", [ctypes.POINTER(ctypes.c_int)], ctypes.c_long
    )
    _get_system_power_status = _bind(
        kernel32, "GetSystemPowerStatus", [ctypes.POINTER(_SystemPowerStatus)], wintypes.BOOL
    )
    try:
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    except OSError:
        _log_once("dwmapi-load", "dwmapi.dll not available; dark title bar disabled")
    else:
        _dwm_set_window_attribute = _bind(
            dwmapi, "DwmSetWindowAttribute",
            [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD], ctypes.c_long,
        )


_load_win32()


def is_windows() -> bool:
    """True إذا كان النظام Windows."""
    return sys.platform == "win32"


def windows_build() -> int:
    """رقم بناء Windows (مثل 22631)؛ 0 على غير Windows."""
    if sys.platform != "win32":
        return 0
    return int(sys.getwindowsversion().build)


def set_topmost(hwnd: int) -> bool:
    """يثبّت النافذة فوق النوافذ الأخرى دون تنشيطها؛ True عند النجاح."""
    if _set_window_pos is None:
        return False
    try:
        flags = _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
        ok = bool(_set_window_pos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, flags))
        if not ok:
            _log_once("topmost", "SetWindowPos(TOPMOST) failed, error %d", ctypes.get_last_error())
        return ok
    except Exception as exc:  # noqa: BLE001  لا نرفع أبدًا إلى خيط الواجهة
        _log_once("topmost-exc", "set_topmost raised: %s", exc)
        return False


def ensure_click_through(hwnd: int) -> bool:
    """يضيف الأنماط الموسّعة WS_EX_TRANSPARENT وLAYERED وNOACTIVATE وTOOLWINDOW (احتياط لـ Qt).

    idempotent: إن كانت الأنماط موجودة فلا كتابة. النافذة تصير شفافة للفأرة والتركيز، وبلا
    زر في شريط المهام. يعيد True عند النجاح أو إن كانت الأنماط موجودة أصلًا.
    """
    if _get_window_long is None or _set_window_long is None or _set_window_pos is None:
        return False
    try:
        ctypes.set_last_error(0)  # القيمة 0 المعادة قد تكون نتيجة صحيحة، فنفحص الخطأ أيضًا
        current = int(_get_window_long(hwnd, _GWL_EXSTYLE))
        if current == 0 and ctypes.get_last_error() != 0:
            _log_once("getlong", "GetWindowLongPtr failed, error %d", ctypes.get_last_error())
            return False
        wanted = current | _CLICK_THROUGH_STYLES
        if wanted == current:
            return True
        ctypes.set_last_error(0)
        previous = int(_set_window_long(hwnd, _GWL_EXSTYLE, wanted))
        if previous == 0 and ctypes.get_last_error() != 0:
            _log_once("setlong", "SetWindowLongPtr failed, error %d", ctypes.get_last_error())
            return False
        apply_flags = (
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED
        )
        _set_window_pos(hwnd, None, 0, 0, 0, 0, apply_flags)  # يجعل النظام يقرأ النمط الجديد
        return True
    except Exception as exc:  # noqa: BLE001
        _log_once("clickthrough-exc", "ensure_click_through raised: %s", exc)
        return False


def set_exclude_from_capture(hwnd: int, enabled: bool) -> bool:
    """تجريبي: يخفي النافذة من لقطات الشاشة والتسجيل (WDA_EXCLUDEFROMCAPTURE).

    يتطلب Windows 10 بناء 19041 فأعلى؛ يعيد False (ويسجّل مرة) إذا لم يتوفر أو فشل.
    """
    if not is_windows() or _set_display_affinity is None:
        return False
    if windows_build() < _MIN_BUILD_EXCLUDE_FROM_CAPTURE:
        _log_once("affinity-build", "exclude-from-capture needs Windows build 19041 or newer")
        return False
    try:
        affinity = _WDA_EXCLUDEFROMCAPTURE if enabled else _WDA_NONE
        ok = bool(_set_display_affinity(hwnd, affinity))
        if not ok:
            _log_once("affinity", "SetWindowDisplayAffinity failed, error %d",
                      ctypes.get_last_error())
        return ok
    except Exception as exc:  # noqa: BLE001
        _log_once("affinity-exc", "set_exclude_from_capture raised: %s", exc)
        return False


def set_dark_title_bar(hwnd: int, enabled: bool) -> bool:
    """يفعّل أو يلغي شريط العنوان الداكن (DWMWA_USE_IMMERSIVE_DARK_MODE)؛ يجرّب القيمة 19 إن فشلت 20."""
    if _dwm_set_window_attribute is None:
        return False
    try:
        value = ctypes.c_int(1 if enabled else 0)
        for attribute in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            result = _dwm_set_window_attribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == _S_OK:
                return True
        return False
    except Exception as exc:  # noqa: BLE001
        _log_once("dark-exc", "set_dark_title_bar raised: %s", exc)
        return False


def query_user_notification_state() -> UserNotificationState:
    """حالة المستخدم (ملء الشاشة، قفل...) عبر SHQueryUserNotificationState؛ UNKNOWN عند الفشل."""
    if _query_notification_state is None:
        return UserNotificationState.UNKNOWN
    try:
        state = ctypes.c_int(0)
        if _query_notification_state(ctypes.byref(state)) != _S_OK:
            return UserNotificationState.UNKNOWN
        return UserNotificationState(state.value)
    except ValueError:  # قيمة جديدة لا نعرفها
        return UserNotificationState.UNKNOWN
    except Exception as exc:  # noqa: BLE001
        _log_once("notify-exc", "query_user_notification_state raised: %s", exc)
        return UserNotificationState.UNKNOWN


def is_battery_saver_on() -> bool:
    """True إذا كان موفّر البطارية (Battery Saver) مفعّلًا؛ False عند الفشل."""
    if _get_system_power_status is None:
        return False
    try:
        status = _SystemPowerStatus()
        if not _get_system_power_status(ctypes.byref(status)):
            return False
        return bool(status.SystemStatusFlag == _BATTERY_SAVER_ON)
    except Exception as exc:  # noqa: BLE001
        _log_once("battery-exc", "is_battery_saver_on raised: %s", exc)
        return False


def client_animations_enabled() -> bool:
    """يحترم إعداد Windows للرسوم المتحركة؛ True (الوضع الافتراضي) إذا تعذّر الاستعلام."""
    if _system_parameters_info is None:
        return True
    try:
        flag = ctypes.c_int(1)
        if not _system_parameters_info(_SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0):
            return True
        return bool(flag.value)
    except Exception as exc:  # noqa: BLE001
        _log_once("anim-exc", "client_animations_enabled raised: %s", exc)
        return True