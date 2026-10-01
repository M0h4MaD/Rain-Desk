"""raindesk/ui/frame_clock.py

الغرض: ساعة الإطارات: تُصدر tick(dt) بمعدل fps ثابت مع dt مقيَّد بسقف.
المسؤوليات: مؤقّت دقيق، وحساب dt الحقيقي، وتقييده بـ DT_MAX_S، والإبلاغ عن التوقفات الطويلة
    (سكون/استئناف) عبر stall_detected قبل التقييد.
الاعتماديات: QtCore وraindesk.core.constants.
النمط التصميمي: Observer (إشارات Qt) وTemplate Method للحلقة الرئيسية.
ملاحظات: نقيس dt بـ time.perf_counter (ساعة رتيبة monotonic لا تتأثر بتغيير وقت النظام).
مثال: clock.tick.connect(on_tick); clock.set_fps(30); clock.start()
"""

from __future__ import annotations

import time
from typing import Final

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from raindesk.core.constants import DT_MAX_S

_MS_PER_SECOND: Final[float] = 1000.0
_FPS_MIN: Final[int] = 1
_FPS_MAX: Final[int] = 240
_DEFAULT_FPS: Final[int] = 30
# أي dt خام أكبر من هذا (ثانية) يعني سكونًا/استئنافًا أو توقفًا طويلًا فنبلّغ عنه.
_STALL_THRESHOLD_S: Final[float] = 1.0


class FrameClock(QObject):
    """ينتج إطارات زمنية؛ لا يعرف شيئًا عن الرسم (الفصل بين الوقت والعرض)."""

    tick = Signal(float)  # dt بالثواني، مقيَّد أصلًا بـ DT_MAX_S
    stall_detected = Signal(float)  # dt الخام (قبل التقييد) عند توقف أطول من الحد

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fps: int = _DEFAULT_FPS
        self._last_time: float = 0.0
        self._last_interval_ms: float = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)  # دقة نحو 1 ms بدل 15.6 ms الافتراضية
        self._timer.setInterval(self._interval_for(self._fps))
        self._timer.timeout.connect(self._on_timeout)

    @staticmethod
    def _interval_for(fps: int) -> int:
        """الفاصل بالميلي ثانية لكل إطار (لا يقل عن 1)."""
        return max(1, round(_MS_PER_SECOND / fps))

    def start(self) -> None:
        """يبدأ الإصدار؛ يصفّر المرجع الزمني كي لا يكون أول dt هو زمن الإيقاف كله."""
        if self._timer.isActive():
            return
        self._last_time = time.perf_counter()
        self._timer.start()

    def stop(self) -> None:
        """يوقف الإصدار (المؤقّت متوقف فلا استهلاك للمعالج)."""
        self._timer.stop()

    def set_fps(self, fps: int) -> None:
        """يضبط معدل الإطارات ضمن [1, 240]؛ التغيير أثناء العمل يعيد تشغيل المؤقّت فقط."""
        clamped = min(max(int(fps), _FPS_MIN), _FPS_MAX)
        if clamped == self._fps:
            return
        self._fps = clamped
        self._timer.setInterval(self._interval_for(clamped))

    @property
    def fps(self) -> int:
        """المعدل المطلوب حاليًا."""
        return self._fps

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    @property
    def last_interval_ms(self) -> float:
        """الفاصل الفعلي الخام بين آخر إطارين بالميلي ثانية (للجودة التكيفية وشاشة HUD)."""
        return self._last_interval_ms

    def _on_timeout(self) -> None:
        now = time.perf_counter()
        raw = max(0.0, now - self._last_time)
        self._last_time = now
        self._last_interval_ms = raw * _MS_PER_SECOND
        if raw > _STALL_THRESHOLD_S:
            self.stall_detected.emit(raw)  # قبل التقييد، ليُعاد تثبيت النوافذ بعد الاستئناف
        self.tick.emit(min(raw, DT_MAX_S))