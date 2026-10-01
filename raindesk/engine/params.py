"""raindesk/engine/params.py

الغرض: معاملات المحاكاة الفعلية (EngineParams) وتنعيمها الزمني.
المسؤوليات: بناء المعاملات من Settings مع إمكانية تجاوز قيم (من آلة الطقس)، وتنعيم الحقول
    العشرية أسّيًا مع قفز فوري للحقول الصحيحة واللون.
الاعتماديات: raindesk.config.schema وraindesk.core وraindesk.engine.math_utils.
النمط التصميمي: Value Object (EngineParams) وLow-pass Filter (ParamSmoother).
ملاحظات رياضية: التنعيم أسّي يركّب تمامًا (انظر exp_smooth)، فلا يعتمد الإحساس على fps.
مثال: smoother = ParamSmoother(params_from_settings(settings)); params = smoother.step(dt)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from typing import Final

from raindesk.config.schema import Settings, default_settings
from raindesk.core.color_utils import hex_to_rgb
from raindesk.core.constants import SMOOTHING_TAU_S
from raindesk.engine.math_utils import exp_smooth

# الحقول التي قد تتجاوزها آلة الطقس (هي مفاتيح PRESETS نفسها).
_OVERRIDABLE_KEYS: Final[tuple[str, ...]] = (
    "intensity", "speed", "drop_length", "drop_thickness", "drop_opacity",
    "wind_angle_deg", "wind_gusts",
)


@dataclass(slots=True)
class EngineParams:
    """معاملات الإطار الحالي كما يراها المحرك والرسّام (كلها بوحدات منطقية موثّقة في الإعدادات)."""

    intensity: float
    speed: float
    drop_length: float
    drop_thickness: float
    drop_opacity: float
    parallax: float
    wind_angle_deg: float
    wind_gusts: float
    gust_period_s: float
    depth_layers: int
    color_rgb: tuple[int, int, int]
    splash_amount: float


# أسماء الحقول العشرية فقط (تُنعَّم)؛ النوع نص لأن الملف يستعمل annotations المؤجَّلة.
_FLOAT_FIELDS: Final[tuple[str, ...]] = tuple(
    f.name for f in fields(EngineParams) if f.type == "float"
)


def _rgb_or_default(hex_color: str) -> tuple[int, int, int]:
    """يحوّل '#RRGGBB' إلى RGB؛ اللون غير الصالح يعود للافتراضي (لا نرفع استثناءً في الحلقة)."""
    try:
        return hex_to_rgb(hex_color)
    except ValueError:
        return hex_to_rgb(default_settings().drop_color)


def params_from_settings(s: Settings, overrides: Mapping[str, float] | None = None) -> EngineParams:
    """يبني EngineParams من الإعدادات؛ overrides (من آلة الطقس) تتقدم على القيم المقابلة.

    Args:
        s: لقطة الإعدادات الحالية.
        overrides: قيم اختيارية لمفاتيح PRESETS فقط؛ المفاتيح الأخرى تُتجاهل.
    splash_amount تساوي 0 عند تعطيل الرذاذ، فيتحول تعطيله إلى تنعيم سلس لا قفزة.
    """
    values: dict[str, float] = {key: float(getattr(s, key)) for key in _OVERRIDABLE_KEYS}
    if overrides:
        for key in _OVERRIDABLE_KEYS:
            if key in overrides:
                values[key] = float(overrides[key])
    return EngineParams(
        intensity=values["intensity"],
        speed=values["speed"],
        drop_length=values["drop_length"],
        drop_thickness=values["drop_thickness"],
        drop_opacity=values["drop_opacity"],
        parallax=float(s.parallax_strength),
        wind_angle_deg=values["wind_angle_deg"],
        wind_gusts=values["wind_gusts"],
        gust_period_s=float(s.gust_period_s),
        depth_layers=int(s.depth_layers),
        color_rgb=_rgb_or_default(s.drop_color),
        splash_amount=float(s.splash_amount) if s.splashes_enabled else 0.0,
    )


class ParamSmoother:
    """ينعّم المعاملات نحو هدف متغيّر؛ الحقول العشرية فقط، أما depth_layers واللون فيقفزان فورًا.

    الثوابت: الحالة الحالية تبقى بين الحالة السابقة والهدف لكل حقل عشري. التعقيد O(عدد الحقول).
    سلامة الخيوط: غير آمن؛ يُستعمل من خيط الواجهة فقط.
    """

    def __init__(self, initial: EngineParams, tau_s: float = SMOOTHING_TAU_S) -> None:
        self._tau_s = tau_s
        self._current = replace(initial)
        self._target = replace(initial)

    def set_target(self, target: EngineParams) -> None:
        """يعيّن هدفًا جديدًا (نسخة)؛ الحقول الصحيحة واللون تُطبَّق على الحالة الحالية فورًا."""
        self._target = replace(target)
        self._current.depth_layers = target.depth_layers
        self._current.color_rgb = target.color_rgb

    def step(self, dt: float) -> EngineParams:
        """يتقدم بزمن dt ويعيد نسخة من الحالة المنعّمة (يمكن للمستدعي الاحتفاظ بها بأمان)."""
        for name in _FLOAT_FIELDS:
            setattr(
                self._current,
                name,
                exp_smooth(getattr(self._current, name), getattr(self._target, name), dt,
                           self._tau_s),
            )
        return replace(self._current)

    def snap(self) -> None:
        """يقفز فورًا إلى الهدف دون تنعيم (عند استيراد إعدادات أو إعادة ضبط)."""
        self._current = replace(self._target)