"""raindesk/engine/weather_fsm.py

الغرض: الطقس التلقائي (سلسلة ماركوف بين خمس حالات) والبرق (عملية بواسون ذات حدود أمان).
المسؤوليات: WeatherStateMachine: اختيار الحالة التالية باحتمالات صفوف المصفوفة، وزمن مكوث
    وزمن مزج يتأثران بـ variability، ومزج قيم الإعدادات المسبقة. LightningModel: أحداث برق
    بومضة أو اثنتين بغلاف أسّي، ملتزمة بمعيار WCAG 2.3.1.
الاعتماديات: raindesk.config.schema (PRESETS) وraindesk.engine.math_utils والمكتبة القياسية.
النمط التصميمي: Finite State Machine (Markov Chain) مع Eased Blend.
ملاحظات: الصنفان معًا هنا لأن البرق مؤثر طقسي وشجرة المشروع لا تحوي ملفًا مستقلًا له.
    كل العشوائية من random.Random الممرَّر (حتمية بالبذرة). لا استدعاءات عشوائية عامة.
مثال: machine = WeatherStateMachine(random.Random(7)); machine.set_enabled(True); machine.step(dt)
"""

from __future__ import annotations

import math
import random
from enum import StrEnum
from typing import Final

from raindesk.config.schema import PRESETS
from raindesk.engine.math_utils import clamp, ease_in_out_cubic, lerp


class WeatherState(StrEnum):
    """حالات الطقس الخمس مرتبة من الأخف إلى الأشد."""

    DRIZZLE = "drizzle"
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    STORM = "storm"


# مصفوفة الانتقال (كل صف مجموعه 1؛ الانتقال إلى الحالة نفسها غير وارد لأن المكوث يغطيها).
TRANSITIONS: Final[dict[WeatherState, dict[WeatherState, float]]] = {
    WeatherState.DRIZZLE: {
        WeatherState.LIGHT: 0.65, WeatherState.MODERATE: 0.30, WeatherState.HEAVY: 0.05,
    },
    WeatherState.LIGHT: {
        WeatherState.DRIZZLE: 0.30, WeatherState.MODERATE: 0.50, WeatherState.HEAVY: 0.20,
    },
    WeatherState.MODERATE: {
        WeatherState.DRIZZLE: 0.10, WeatherState.LIGHT: 0.30,
        WeatherState.HEAVY: 0.45, WeatherState.STORM: 0.15,
    },
    WeatherState.HEAVY: {
        WeatherState.LIGHT: 0.15, WeatherState.MODERATE: 0.50, WeatherState.STORM: 0.35,
    },
    WeatherState.STORM: {WeatherState.MODERATE: 0.55, WeatherState.HEAVY: 0.45},
}

_DWELL_MEAN_CALM_S: Final[float] = 180.0  # متوسط المكوث عند variability = 0
_DWELL_MEAN_WILD_S: Final[float] = 40.0  # متوسط المكوث عند variability = 1
_DWELL_SPREAD_MIN: Final[float] = 0.6  # المكوث الفعلي = المتوسط * U(0.6, 1.4)
_DWELL_SPREAD_MAX: Final[float] = 1.4
_BLEND_CALM_S: Final[float] = 15.0  # زمن المزج عند variability = 0
_BLEND_WILD_S: Final[float] = 5.0  # زمن المزج عند variability = 1
_DEFAULT_VARIABILITY: Final[float] = 0.5
_INITIAL_STATE: Final[WeatherState] = WeatherState.MODERATE  # يطابق الإعدادات الافتراضية
_PRESET_KEYS: Final[tuple[str, ...]] = tuple(PRESETS["moderate"])


class WeatherStateMachine:
    """طقس تلقائي: مكوث في حالة ثم مزج ناعم إلى التالية.

    المراحل: DWELL (blend = 0، state == next_state) ثم BLEND (يتقدم blend من 0 إلى 1 بمنحنى
    ease_in_out_cubic) ثم تصير الحالة التالية هي الحالية وتبدأ مرحلة مكوث جديدة.
    """

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._enabled = False
        self._variability = _DEFAULT_VARIABILITY
        self._state = _INITIAL_STATE
        self._next = _INITIAL_STATE
        self._blending = False
        self._elapsed = 0.0  # زمن مرحلة المكوث أو المزج الجارية
        self._dwell_s = self._sample_dwell()
        self._blend_s = self._blend_duration()

    # ------------------------------------------------------------------ الإعداد
    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """التشغيل يبدأ مكوثًا جديدًا في الحالة الحالية؛ الإيقاف يجمّد الآلة."""
        if enabled and not self._enabled:
            self._blending = False
            self._next = self._state
            self._elapsed = 0.0
            self._dwell_s = self._sample_dwell()
        self._enabled = enabled

    def set_variability(self, variability: float) -> None:
        """التنوع في [0, 1]؛ يؤثر على المكوث والمزج التاليين (لا يقطع المرحلة الجارية)."""
        self._variability = clamp(variability, 0.0, 1.0)

    # ------------------------------------------------------------------ الحالة
    @property
    def state(self) -> WeatherState:
        return self._state

    @property
    def next_state(self) -> WeatherState:
        """الحالة التي نمتزج إليها (تساوي state خلال المكوث)."""
        return self._next

    @property
    def blend(self) -> float:
        """نسبة المزج المخفَّفة في [0, 1] (0 خلال المكوث)."""
        if not self._blending:
            return 0.0
        return ease_in_out_cubic(self._elapsed / self._blend_s)

    @property
    def dwell_s(self) -> float:
        """مدة المكوث المسحوبة للمرحلة الحالية أو الأخيرة (ثانية)."""
        return self._dwell_s

    @property
    def blend_s(self) -> float:
        """مدة المزج المسحوبة لآخر مزج (ثانية)."""
        return self._blend_s

    def blended_values(self) -> dict[str, float]:
        """قيم مفاتيح PRESETS مستوفاة بين الحالة الحالية والتالية بنسبة blend."""
        current, upcoming, amount = PRESETS[self._state], PRESETS[self._next], self.blend
        return {key: lerp(current[key], upcoming[key], amount) for key in _PRESET_KEYS}

    # ------------------------------------------------------------------ التقدّم
    def _sample_dwell(self) -> float:
        mean = lerp(_DWELL_MEAN_CALM_S, _DWELL_MEAN_WILD_S, self._variability)
        return mean * self._rng.uniform(_DWELL_SPREAD_MIN, _DWELL_SPREAD_MAX)

    def _blend_duration(self) -> float:
        return lerp(_BLEND_CALM_S, _BLEND_WILD_S, self._variability)

    def _pick_next(self) -> WeatherState:
        """يختار الحالة التالية بالتجميع التراكمي لاحتمالات صف الحالة الحالية."""
        draw = self._rng.random()
        cumulative = 0.0
        row = TRANSITIONS[self._state]
        choice = self._state
        for candidate, probability in row.items():
            cumulative += probability
            choice = candidate
            if draw < cumulative:
                break
        return choice  # الأخيرة تُختار عند خطأ تقريب عائم (مجموع الصف 1 تقريبًا)

    def step(self, dt: float) -> None:
        """يقدّم الآلة؛ لا شيء إن كانت معطّلة. يعالج dt الكبير بحلقة (قد يعبر مرحلتين)."""
        if not self._enabled or dt <= 0.0:
            return
        remaining = dt
        while remaining > 0.0:
            limit = self._blend_s if self._blending else self._dwell_s
            room = limit - self._elapsed
            if remaining < room:
                self._elapsed += remaining
                return
            remaining -= room
            if self._blending:  # انتهى المزج: الحالة التالية تصبح الحالية
                self._state = self._next
                self._blending = False
                self._elapsed = 0.0
                self._dwell_s = self._sample_dwell()
            else:  # انتهى المكوث: نبدأ مزجًا إلى حالة جديدة
                self._next = self._pick_next()
                self._blending = True
                self._elapsed = 0.0
                self._blend_s = self._blend_duration()


# ---------------------------------------------------------------------------
# البرق
# ---------------------------------------------------------------------------
_LIGHTNING_INTERVAL_RARE_S: Final[float] = 45.0  # متوسط الفاصل عند frequency = 0
_LIGHTNING_INTERVAL_OFTEN_S: Final[float] = 9.0  # متوسط الفاصل عند frequency = 1
_LIGHTNING_MIN_GAP_S: Final[float] = 5.0  # أقل فاصل بين حدثين
_LIGHTNING_PEAK_MIN: Final[float] = 0.12  # أصغر ذروة لحدث (مجال بصري مقبول)
LIGHTNING_PEAK_MAX: Final[float] = 0.30  # سقف الذروة (أمان)؛ عام ليستعمله المرسِم أيضًا
_LIGHTNING_DECAY_S: Final[float] = 0.09  # ثابت الزمن في غلاف exp(-t / 0.09)
_LIGHTNING_SECOND_PROBABILITY: Final[float] = 0.5  # احتمال أن يتضمن الحدث ومضتين
_LIGHTNING_SECOND_DELAY_MIN_S: Final[float] = 0.09
_LIGHTNING_SECOND_DELAY_MAX_S: Final[float] = 0.16
_LIGHTNING_SECOND_RATIO: Final[float] = 0.60  # ذروة الومضة الثانية نسبةً للأولى
_LIGHTNING_TAIL_S: Final[float] = 0.9  # بعد آخر ومضة بهذا القدر ينتهي الحدث (exp(-10) تقريبًا صفر)


class LightningModel:
    """برق: عملية بواسون بحد أدنى 5 s بين الأحداث، لكل حدث ومضة أو ومضتان بغلاف أسّي.

    الأمان (WCAG 2.1 SC 2.3.1): الحدث يحوي ومضتين على الأكثر، والأحداث تفصلها 5 s فأكثر،
    فلا يتجاوز العدد ومضتين في أي ثانية (الحد 3)؛ والذروة <= 0.30؛ وعند الإيقاف تُصفَّر الشدة.
    """

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._enabled = False
        self._frequency = 0.0
        self._wait_s = _LIGHTNING_MIN_GAP_S  # الزمن المتبقي حتى الحدث التالي
        self._active_s: float | None = None  # زمن الحدث الجاري (None = لا حدث)
        self._event_end_s = 0.0  # زمن انتهاء الحدث الجاري منذ بدايته
        self._flashes: list[tuple[float, float]] = []  # (إزاحة الومضة بالثواني، ذروتها)
        self._alpha = 0.0
        self._event_count = 0

    def configure(self, enabled: bool, frequency: float) -> None:
        """يضبط التشغيل والتكرار؛ التشغيل من الإيقاف يسحب فاصل انتظار جديدًا."""
        self._frequency = clamp(frequency, 0.0, 1.0)
        if enabled and not self._enabled:
            self._wait_s = self._sample_wait()
        if not enabled:
            self._active_s = None
            self._flashes = []
            self._alpha = 0.0
        self._enabled = enabled

    @property
    def alpha(self) -> float:
        """شدة الومضة الحالية في [0, 0.30]."""
        return self._alpha

    @property
    def event_count(self) -> int:
        """عدد الأحداث التي بدأت منذ الإنشاء (للاختبار والتشخيص)."""
        return self._event_count

    def _sample_wait(self) -> float:
        """فاصل بواسون: أسّي بمتوسط lerp(45, 9, f) مع حد أدنى 5 s."""
        mean = lerp(_LIGHTNING_INTERVAL_RARE_S, _LIGHTNING_INTERVAL_OFTEN_S, self._frequency)
        return max(_LIGHTNING_MIN_GAP_S, self._rng.expovariate(1.0 / mean))

    def _start_event(self) -> None:
        peak = self._rng.uniform(_LIGHTNING_PEAK_MIN, LIGHTNING_PEAK_MAX)
        self._flashes = [(0.0, peak)]
        last_offset = 0.0
        if self._rng.random() < _LIGHTNING_SECOND_PROBABILITY:
            last_offset = self._rng.uniform(
                _LIGHTNING_SECOND_DELAY_MIN_S, _LIGHTNING_SECOND_DELAY_MAX_S
            )
            self._flashes.append((last_offset, peak * _LIGHTNING_SECOND_RATIO))
        self._active_s = 0.0
        self._event_end_s = last_offset + _LIGHTNING_TAIL_S
        self._event_count += 1

    def _envelope(self, t: float) -> float:
        """مجموع الأغلفة peak * exp(-(t - offset) / 0.09) للومضات التي بدأت."""
        total = 0.0
        for offset, peak in self._flashes:
            if t >= offset:
                total += peak * math.exp(-(t - offset) / _LIGHTNING_DECAY_S)
        return min(total, LIGHTNING_PEAK_MAX)

    def step(self, dt: float) -> None:
        """يقدّم النموذج؛ يبدأ حدثًا عند انتهاء الانتظار ويحدّث alpha."""
        if not self._enabled or dt <= 0.0:
            return
        if self._active_s is None:
            self._wait_s -= dt
            if self._wait_s <= 0.0:
                self._start_event()
            else:
                self._alpha = 0.0
                return
        else:
            self._active_s += dt
        assert self._active_s is not None
        self._alpha = self._envelope(self._active_s)
        if self._active_s >= self._event_end_s:
            self._active_s = None
            self._flashes = []
            self._alpha = 0.0
            self._wait_s = self._sample_wait()