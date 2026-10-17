"""raindesk/platform_win/power.py

الغرض: يمنع Windows من إبطاء مؤقّتات التطبيق أثناء تشغيل الصوت، فلا يتقطّع (underrun).
المسؤوليات: طلب دقة مؤقّت 1 ms (timeBeginPeriod) واستثناء العملية من "power throttling"
    (EcoQoS وتجاهل دقة المؤقّت)، وإلغاء الطلبين عند إيقاف الصوت. لا شيء يحدث خارج Windows.
الاعتماديات: ctypes فقط (مكتبة بايثون القياسية). لا يستورد PySide6.
النمط التصميمي: Guard/RAII بسيط: begin يعيد رمزًا (token) و end يعيد الحالة السابقة.
ملاحظات: في Windows 11 قد تُهمَل دقة المؤقّت العالية لنافذة تبدو محجوبة أو في الخلفية (نافذة
    شفافة تمرّر النقرات تُعامَل هكذا غالبًا)، فيصير مؤقّت 20 ms يعمل كل 15 إلى 30 ms أو أكثر
    ويفرغ مخزن الصوت. كل الاستدعاءات "أفضل جهد": أي فشل يُسجَّل بمستوى DEBUG ولا يرفع استثناء.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from dataclasses import dataclass
from typing import Any, Final

_LOG = logging.getLogger(__name__)

_TIMER_RESOLUTION_MS: Final[int] = 1  # ms: أدق دقة مؤقّت يطلبها timeBeginPeriod
_PROCESS_POWER_THROTTLING: Final[int] = 4  # ProcessPowerThrottling من PROCESS_INFORMATION_CLASS
_THROTTLING_VERSION: Final[int] = 1  # PROCESS_POWER_THROTTLING_CURRENT_VERSION
_THROTTLING_EXECUTION_SPEED: Final[int] = 0x1  # EcoQoS: تخفيض سرعة التنفيذ
_THROTTLING_IGNORE_TIMER_RESOLUTION: Final[int] = 0x4  # تجاهل طلبات دقة المؤقّت (Windows 11)


class _ProcessPowerThrottlingState(ctypes.Structure):
    """PROCESS_POWER_THROTTLING_STATE: ثلاثة ULONG (32 بت): Version وControlMask وStateMask."""

    _fields_ = (
        ("Version", ctypes.c_uint32),
        ("ControlMask", ctypes.c_uint32),
        ("StateMask", ctypes.c_uint32),
    )


@dataclass(frozen=True, slots=True)
class TimingBoost:
    """رمز يُعاد من begin_responsive_timing لتمريره إلى end_responsive_timing."""

    timer_period_set: bool
    throttling_disabled: bool


def _is_windows() -> bool:
    return sys.platform == "win32"


def _windll() -> Any:
    return getattr(ctypes, "windll", None)


def _set_throttling(control_mask: int) -> bool:
    """StateMask = 0 مع ControlMask = القناع: يعطّل التخفيض لهذه الخصائص؛ والقناع 0 = الافتراضي."""
    windll = _windll()
    if windll is None:
        return False
    try:
        kernel32 = windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        state = _ProcessPowerThrottlingState(_THROTTLING_VERSION, control_mask, 0)
        ok = kernel32.SetProcessInformation(
            ctypes.c_void_p(kernel32.GetCurrentProcess()),
            _PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
        return bool(ok)
    except Exception as exc:  # noqa: BLE001  أفضل جهد: لا نكسر الصوت بسبب هذا
        _LOG.debug("SetProcessInformation failed: %r", exc)
        return False


def _time_period(begin: bool) -> bool:
    windll = _windll()
    if windll is None:
        return False
    try:
        winmm = windll.winmm
        function = winmm.timeBeginPeriod if begin else winmm.timeEndPeriod
        return int(function(_TIMER_RESOLUTION_MS)) == 0  # TIMERR_NOERROR = 0
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("timeBeginPeriod/timeEndPeriod failed: %r", exc)
        return False


def begin_responsive_timing() -> TimingBoost | None:
    """يطلب مؤقّتات دقيقة وبلا تخفيض؛ يعيد None خارج Windows."""
    if not _is_windows():
        return None
    boost = TimingBoost(
        timer_period_set=_time_period(True),
        throttling_disabled=_set_throttling(
            _THROTTLING_EXECUTION_SPEED | _THROTTLING_IGNORE_TIMER_RESOLUTION
        ),
    )
    _LOG.info(
        "responsive timing: timer_period=%s throttling_disabled=%s",
        boost.timer_period_set,
        boost.throttling_disabled,
    )
    return boost


def end_responsive_timing(boost: TimingBoost | None) -> None:
    """يلغي ما طلبه begin_responsive_timing (آمن مع None وعند التكرار)."""
    if boost is None or not _is_windows():
        return
    if boost.timer_period_set:
        _time_period(False)
    if boost.throttling_disabled:
        _set_throttling(0)  # يعيد إدارة النظام الافتراضية
