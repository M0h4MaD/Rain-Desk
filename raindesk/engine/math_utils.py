"""raindesk/engine/math_utils.py

الغرض: دوال رياضية صغيرة نقية يعتمد عليها المحرك والواجهة.
المسؤوليات: clamp وlerp وinv_lerp وsmoothstep ودوال التخفيف (easing) والتنعيم الأسّي ودالة العصف.
الاعتماديات: المكتبة القياسية فقط.
النمط التصميمي: مجموعة دوال نقية بلا حالة (Pure Functions).
ملاحظات رياضية: أنظر الصيغة في تعليق كل دالة (exp_smooth وgust_signal خصوصًا).
مثال: exp_smooth(current=0.0, target=1.0, dt=1/60, tau=0.25)
"""

from __future__ import annotations

import math
from typing import Final

# أوزان مكوّنات العصف: مجموعها 1 تمامًا، فيبقى |G| <= 1 دون قصّ في الحالة العادية.
_GUST_WEIGHTS: Final[tuple[float, float, float]] = (0.6, 0.3, 0.1)
# نسب دورات المكوّنات إلى الدورة الأساسية T؛ النسب غير متناسبة (incommensurate) فلا يتكرر النمط.
_GUST_PERIOD_RATIOS: Final[tuple[float, float, float]] = (1.0, 0.37, 2.3)
_MIN_PERIOD_S: Final[float] = 1e-6  # ثانية: يمنع القسمة على صفر إن وصلت دورة غير صالحة
_TWO_PI: Final[float] = 2.0 * math.pi
_CUBIC_HALF: Final[float] = 0.5  # منتصف المجال حيث يتبدل فرعا ease_in_out_cubic


def clamp(x: float, lo: float, hi: float) -> float:
    """يقيّد x ضمن [lo, hi]؛ NaN يمرّ كما هو (لا نخفي الخطأ بقيمة مختلقة).

    الشرط المسبق: lo <= hi. التعقيد: O(1).
    """
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def lerp(a: float, b: float, t: float) -> float:
    """الاستيفاء الخطي a + (b - a) * t؛ t خارج [0, 1] يُستقرأ (extrapolation) ولا يُقصّ."""
    return a + (b - a) * t


def inv_lerp(a: float, b: float, v: float) -> float:
    """عكس lerp: يعيد t بحيث lerp(a, b, t) = v؛ يعيد 0.0 إذا تساوى الطرفان (لا قسمة على صفر)."""
    if a == b:
        return 0.0
    return (v - a) / (b - a)


def smoothstep(e0: float, e1: float, x: float) -> float:
    """منحنى S ناعم من 0 إلى 1: 3t^2 - 2t^3 حيث t = clamp((x - e0) / (e1 - e0)).

    مشتقته صفر عند الطرفين فلا يظهر "كسر" في الحركة. إن تساوى e0 وe1 يصبح خطوة حادة.
    """
    if e0 == e1:
        return 0.0 if x < e0 else 1.0
    t = clamp(inv_lerp(e0, e1, x), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ease_out_quad(t: float) -> float:
    """تخفيف خروج تربيعي: 1 - (1 - t)^2؛ سريع في البداية ثم يبطئ (مناسب لاتساع تموّج الرذاذ)."""
    u = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - u) * (1.0 - u)


def ease_in_out_cubic(t: float) -> float:
    """تخفيف دخول وخروج تكعيبي: 4t^3 للنصف الأول و1 - (-2t + 2)^3 / 2 للثاني (مستمر الاشتقاق)."""
    u = clamp(t, 0.0, 1.0)
    if u < _CUBIC_HALF:
        return 4.0 * u * u * u
    v = -2.0 * u + 2.0
    return 1.0 - v * v * v / 2.0


def exp_smooth(current: float, target: float, dt: float, tau: float) -> float:
    """تنعيم أسّي مستقل عن معدل الإطارات.

    الصيغة: current' = current + (target - current) * alpha، حيث alpha = 1 - exp(-dt / tau).
    الرموز: dt زمن الخطوة (ثانية)، tau ثابت الزمن (ثانية): بعد tau يُقطع نحو 63% من الفرق.
    خاصية التركيب: n خطوة بزمن dt/n تساوي خطوة واحدة بزمن dt تمامًا، لأن
    (1 - alpha(dt/n))^n = exp(-dt/tau)، فلا يتغير الإحساس بتغيّر fps.
    dt <= 0 لا يغيّر شيئًا، وtau <= 0 يعني قفزًا فوريًا إلى الهدف.
    """
    if tau <= 0.0:
        return target
    if dt <= 0.0:
        return current
    alpha = 1.0 - math.exp(-dt / tau)
    return current + (target - current) * alpha


def gust_signal(t: float, period_s: float, phases: tuple[float, float, float]) -> float:
    """إشارة عصف شبه عشوائية في [-1, 1] بكلفة O(1).

    الصيغة: G(t) = 0.6 sin(2 pi t / T + f1) + 0.3 sin(2 pi t / (0.37 T) + f2)
                   + 0.1 sin(2 pi t / (2.3 T) + f3)
    الرموز: T = period_s، وf1..f3 أطوار عشوائية ثابتة طوال الجلسة.
    المعنى البصري: موجة بطيئة (عصف رئيسي) تعلوها تموجات أسرع أضعف. الدورات غير متناسبة فلا
    يتكرر النمط بوضوح، وهذا تقريب رخيص لضجيج متماسك أحادي البعد (Perlin-style 1D noise).
    """
    period = max(period_s, _MIN_PERIOD_S)
    total = 0.0
    for weight, ratio, phase in zip(_GUST_WEIGHTS, _GUST_PERIOD_RATIOS, phases, strict=True):
        total += weight * math.sin(_TWO_PI * t / (period * ratio) + phase)
    return clamp(total, -1.0, 1.0)  # حماية من خطأ تقريب عائم يتجاوز 1 بمقدار 1e-16