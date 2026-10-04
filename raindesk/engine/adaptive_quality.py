"""raindesk/engine/adaptive_quality.py

الغرض: التحكم بالجودة التكيفي: يخفّض عدد القطرات تلقائيًا عند الإجهاد ويستعيده عند الراحة.
المسؤوليات: متوسطات متحركة أسّية (EMA) لزمن الفاصل بين الإطارات وكلفة الإطار، وقاعدتا تخفيض
    واستعادة بينهما نطاق تباطؤ (hysteresis) يمنع التذبذب، ومعامل scale بين 0.5 و1.0.
الاعتماديات: raindesk.core.constants والمكتبة القياسية.
النمط التصميمي: Feedback Controller بنطاق ميت (Dead Band) وعدّادات إقامة (dwell counters).
ملاحظات رياضية:
    budget = 1000 / fps_cap (ms).  EMA: e' = e + 0.1 * (x - e).
    تخفيض: (interval_ema > 1.25 budget) أو (cost_ema > 0.80 budget) لـ 60 إطارًا متتاليًا
        يعطي scale = max(0.5, scale * 0.85).
    استعادة: (cost_ema < 0.40 budget) و(interval_ema < 1.10 budget) لـ 300 إطار متتالٍ
        يعطي scale = min(1.0, scale * 1.10).
    الفجوة بين العتبتين (0.40 و0.80) واختلاف العدّادين (60 و300) هما نطاق التباطؤ: كلفة بين
    0.5 و0.7 من الميزانية لا تحرّك شيئًا في الاتجاهين، فلا يحدث تذبذب بين الحالتين.
مثال: aq.configure(True, 30); aq.record(interval_ms, cost_ms); count = round(n * aq.scale)
"""

from __future__ import annotations

import logging
from typing import Final

from raindesk.core.constants import ADAPTIVE_DOWN_FRAMES, ADAPTIVE_MIN_SCALE, ADAPTIVE_UP_FRAMES
from raindesk.engine.math_utils import clamp

_LOG = logging.getLogger(__name__)

_EMA_ALPHA: Final[float] = 0.1  # وزن العينة الجديدة في المتوسط (حوالي 10 إطارات ذاكرة)
_MS_PER_SECOND: Final[float] = 1000.0
_DEFAULT_FPS: Final[int] = 30
_INTERVAL_DEGRADE_FACTOR: Final[float] = 1.25  # الفاصل أكبر من 1.25 الميزانية = تأخر واضح
_COST_DEGRADE_FACTOR: Final[float] = 0.80  # الكلفة أكبر من 80% من الميزانية = لا هامش
_COST_RESTORE_FACTOR: Final[float] = 0.40  # الكلفة أقل من 40% = هامش واسع للاستعادة
_INTERVAL_RESTORE_FACTOR: Final[float] = 1.10  # الفاصل قريب من الميزانية = لا تأخر
_DEGRADE_MULTIPLIER: Final[float] = 0.85
_RESTORE_MULTIPLIER: Final[float] = 1.10
_MAX_INTERVAL_FACTOR: Final[float] = 4.0  # يقصّ الفواصل الشاذة (سكون/توقف) قبل إدخالها في EMA


class AdaptiveQuality:
    """معامل جودة يتكيف مع الحمل. الثوابت: scale دائمًا ضمن [0.5, 1.0]."""

    def __init__(self) -> None:
        self._enabled = False
        self._budget_ms = _MS_PER_SECOND / _DEFAULT_FPS
        self._interval_ema: float | None = None
        self._cost_ema: float | None = None
        self._scale = 1.0
        self._down_count = 0  # إطارات متتالية تحت ظرف الإجهاد
        self._up_count = 0  # إطارات متتالية تحت ظرف الراحة

    # ------------------------------------------------------------------ الإعداد
    def configure(self, enabled: bool, fps_cap: int) -> None:
        """يفعّل أو يعطّل ويضبط الميزانية؛ التعطيل يعيد scale إلى 1.0 فورًا."""
        self._budget_ms = _MS_PER_SECOND / max(int(fps_cap), 1)
        if not enabled and self._enabled:
            self.reset()
        self._enabled = enabled
        if not enabled:
            self._scale = 1.0

    def reset(self) -> None:
        """يصفّر المتوسطات والعدّادات ويعيد scale إلى 1.0."""
        self._interval_ema = None
        self._cost_ema = None
        self._scale = 1.0
        self._down_count = 0
        self._up_count = 0

    # ------------------------------------------------------------------ القراءة
    @property
    def scale(self) -> float:
        """معامل في [0.5, 1.0] يُضرب في العدد المستهدف للقطرات."""
        return self._scale

    @property
    def interval_ema(self) -> float:
        """متوسط الفاصل بين الإطارات (ms)؛ 0 قبل أول عينة."""
        return 0.0 if self._interval_ema is None else self._interval_ema

    @property
    def cost_ema(self) -> float:
        """متوسط كلفة الإطار (ms)؛ 0 قبل أول عينة."""
        return 0.0 if self._cost_ema is None else self._cost_ema

    @property
    def fps(self) -> float:
        """معدل الإطارات الفعلي المقدَّر من متوسط الفاصل؛ 0 قبل أول عينة."""
        return 0.0 if not self.interval_ema else _MS_PER_SECOND / self.interval_ema

    # ------------------------------------------------------------------ التحديث
    def record(self, interval_ms: float, cost_ms: float) -> None:
        """يسجّل عينة إطار؛ المتوسطات تُحدَّث دائمًا (للوحة التشخيص) والقواعد تعمل إن فُعّل.

        الفاصل يُقصّ عند 4 أضعاف الميزانية: توقف طويل واحد (سكون الجهاز مثلًا) لا يجب أن
        يُحسب إجهادًا مستدامًا. الإجهاد الحقيقي المستمر يبقى يتجاوز العتبة حتى بعد القص.
        """
        interval = clamp(interval_ms, 0.0, _MAX_INTERVAL_FACTOR * self._budget_ms)
        cost = max(cost_ms, 0.0)
        if self._interval_ema is None or self._cost_ema is None:
            self._interval_ema, self._cost_ema = interval, cost
        else:
            self._interval_ema += _EMA_ALPHA * (interval - self._interval_ema)
            self._cost_ema += _EMA_ALPHA * (cost - self._cost_ema)
        if not self._enabled:
            return

        overloaded = (
            self._interval_ema > _INTERVAL_DEGRADE_FACTOR * self._budget_ms
            or self._cost_ema > _COST_DEGRADE_FACTOR * self._budget_ms
        )
        idle = (
            self._cost_ema < _COST_RESTORE_FACTOR * self._budget_ms
            and self._interval_ema < _INTERVAL_RESTORE_FACTOR * self._budget_ms
        )
        # "متتالية": أي إطار يخالف الظرف يصفّر عدّاده؛ والظرفان متنافيان فلا يُحسبان معًا.
        self._down_count = self._down_count + 1 if overloaded else 0
        self._up_count = self._up_count + 1 if idle else 0

        if self._down_count >= ADAPTIVE_DOWN_FRAMES:
            self._adjust(max(ADAPTIVE_MIN_SCALE, self._scale * _DEGRADE_MULTIPLIER))
        elif self._up_count >= ADAPTIVE_UP_FRAMES:
            self._adjust(min(1.0, self._scale * _RESTORE_MULTIPLIER))

    def _adjust(self, new_scale: float) -> None:
        """يطبّق التعديل ويصفّر العدّادين (بعد كل تعديل نبدأ العدّ من جديد) ويسجّل التغيير."""
        self._down_count = 0
        self._up_count = 0
        if new_scale == self._scale:
            return  # بلغنا الحد (0.5 أو 1.0): لا تغيير ولا سجل مكرر
        _LOG.info(
            "adaptive quality scale %.2f -> %.2f (interval %.1f ms, cost %.1f ms, budget %.1f ms)",
            self._scale, new_scale, self.interval_ema, self.cost_ema, self._budget_ms,
        )
        self._scale = new_scale