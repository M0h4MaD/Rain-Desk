"""raindesk/engine/wind_model.py

الغرض: نموذج صوت رياح واقعي فوق إشارة العصف: طبقات ضجيج بألوان مختلفة تُمزج حسب قوة الرياح
    وشدة العصفة، مع "تنفّس" بطيء مستقل وصفير (howl) يعلو في العصفات القوية.
المسؤوليات: جدول حلقات الرياح (نطاق وميل وطول)، وكسب الطبقات الإضافية (mid وhiss وhowl)،
    وحالة التنفّس البطيء (Breath) التي تمنع أن تبدو الرياح الثابتة آلية.
الاعتماديات: NumPy وraindesk.engine.math_utils.
النمط التصميمي: دوال نقية + كائن حالة صغير (Breath).
ملاحظات: الرياح الحقيقية ليست ضجيجًا واحدًا بكسب متغيّر: عند ازدياد السرعة يعلو المحتوى
    الترددي (يصير الصوت أكثر "حفيفًا")، وتظهر نغمة صفير (انظر تسمية howl) تتصاعد مع العصفة.
    لذلك نمزج خمس حلقات بأطوال غير متناسبة (8 و7 و6 و9 و7.5 ثانية) فلا يتكرر الجمع بينها
    تكرارًا مسموعًا. الطبقة الأولى "wind" تحتفظ باسمها وكسبها القديمين (توافق مع ما سبق).
    كسب الصفير مضروب في g فيصمت في السكون ويعلو عند الذروة؛ ويتبدّل بين حلقتين
    (منخفضة ومرتفعة) بحسب g فتتغير "نغمته" مع قوة العصفة.
مثال: gains = wind_extra_gains(0.8, 0.5, 0.0); breath = Breath(rng); b = breath.step(0.02)
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from raindesk.engine.math_utils import clamp

# اسم الحلقة: (الحد الأدنى Hz، الأعلى Hz، أس التردد، الطول بالثواني أو None = طول الحلقات العام)
WIND_LOOP_SPECS: Final[dict[str, tuple[float, float, float, float | None]]] = {
    "wind": (40.0, 500.0, -1.0, None),  # الجسم المنخفض: الحلقة الأصلية (-6 dB/أوكتاف)
    "wind_mid": (180.0, 1600.0, -0.7, 7.0),  # "الهبوب": جسم الصوت المتوسط
    "wind_hiss": (1800.0, 7500.0, -0.2, 6.0),  # حفيف الهواء عند السرعات العالية
    "wind_howl_lo": (330.0, 420.0, 0.0, 9.0),  # صفير منخفض النغمة (نطاق ضيق)
    "wind_howl_hi": (520.0, 660.0, 0.0, 7.5),  # صفير مرتفع النغمة
}
EXTRA_LAYERS: Final[tuple[str, ...]] = ("wind_mid", "wind_hiss", "wind_howl_lo", "wind_howl_hi")

_MID_LEVEL: Final[float] = 0.6
_HISS_LEVEL: Final[float] = 0.30
_HOWL_LEVEL: Final[float] = 0.30
_HOWL_ONSET: Final[float] = 0.40  # قوة الرياح الفعّالة التي يبدأ عندها الصفير
_BREATH_TAU_S: Final[float] = 1.2  # ثابت التنعيم (ثانية)
_BREATH_HOLD_S: Final[tuple[float, float]] = (1.5, 4.0)  # كل كم ثانية يُختار هدف جديد
BREATH_DEPTH: Final[float] = 0.15  # عمق تأثير التنفّس على كسب الجسم المنخفض


def wind_extra_gains(amount: float, gust: float, breath: float) -> dict[str, float]:
    """كسب الطبقات الإضافية.

    amount: قوة الرياح [0, 1]. gust: العصفة [-1, 1]. breath: التنفّس البطيء [-1, 1].
    القوة الفعّالة s = a * (0.5 + 0.35 g + 0.15 b) حيث g = (gust + 1) / 2 في [0, 1]:
    mid ~ s^1.3 (0.35 + 0.65 g)، hiss ~ s^2 g^1.5 (في العصفات القوية فقط)،
    howl ~ ((s - 0.4) / 0.6)^1.5 g موزَّع بين الحلقتين المنخفضة والمرتفعة بنسبة (1 - g) : g.
    """
    a = clamp(amount, 0.0, 1.0)
    g = clamp((gust + 1.0) / 2.0, 0.0, 1.0)
    s = clamp(a * (0.5 + 0.35 * g + 0.15 * clamp(breath, -1.0, 1.0)), 0.0, 1.0)
    howl = _HOWL_LEVEL * clamp((s - _HOWL_ONSET) / (1.0 - _HOWL_ONSET), 0.0, 1.0) ** 1.5 * g
    return {
        "wind_mid": _MID_LEVEL * s**1.3 * (0.35 + 0.65 * g),
        "wind_hiss": _HISS_LEVEL * s**2 * g**1.5,
        "wind_howl_lo": howl * (1.0 - g),
        "wind_howl_hi": howl * g,
    }


class Breath:
    """تنفّس بطيء في [-1, 1]: مشي عشوائي مُنعَّم يغيّر هدفه كل 1.5 إلى 4 ثوانٍ."""

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng
        self.value = 0.0
        self._target = float(rng.uniform(-1.0, 1.0))
        self._hold = float(rng.uniform(*_BREATH_HOLD_S))

    def step(self, dt: float) -> float:
        """يتقدّم dt ثانية ويعيد القيمة الجديدة (تنعيم أسّي نحو الهدف)."""
        self._hold -= dt
        if self._hold <= 0.0:
            self._target = float(self._rng.uniform(-1.0, 1.0))
            self._hold = float(self._rng.uniform(*_BREATH_HOLD_S))
        self.value += (self._target - self.value) * (1.0 - math.exp(-dt / _BREATH_TAU_S))
        return self.value
