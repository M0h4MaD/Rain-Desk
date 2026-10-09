"""raindesk/config/schema.py

الغرض: مخطط الإعدادات: الكلاس Settings، ومواصفة كل حقل، والتحقق، والترحيل بين الإصدارات.
المسؤوليات: قيم افتراضية موحّدة، وclamp وcoercion لكل نوع، وإسقاط المفاتيح المجهولة،
    والإعدادات المسبقة (PRESETS) وملفات الجودة والمدى العشوائي، وترحيل schema_version.
الاعتماديات: raindesk.core.color_utils والمكتبة القياسية (لا PySide6 هنا).
النمط التصميمي: Data-Driven Validation: جدول مواصفات واحد يقود التحقق بدل if لكل حقل.
ملاحظات: الدوال هنا لا ترفع استثناءات عند بيانات تالفة؛ القيمة غير الصالحة تعود لافتراضيها
    مع تسجيل تحذير، لأن ملف الإعدادات قد يُعدَّل يدويًا أو يتلف.
مثال: settings = validate_and_coerce(migrate(json.load(f)))
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final

from raindesk.core.color_utils import hex_to_rgb, is_valid_hex, rgb_to_hex

SETTINGS_SCHEMA_VERSION: Final[int] = 1  # يرتفع عند أي تغيير غير متوافق في بنية الملف

_LOG = logging.getLogger(__name__)
_INT_MAX: Final[int] = 2147483647  # أكبر قيمة int بـ 32 بت (حد rng_seed)
_TRUE_TEXTS: Final[frozenset[str]] = frozenset({"true", "1"})
_FALSE_TEXTS: Final[frozenset[str]] = frozenset({"false", "0"})


@dataclass(slots=True)
class Settings:
    """كل إعدادات التطبيق: خاصية لكل مفتاح بقيمته الافتراضية (ترتيبها ترتيب المخطط)."""

    # --- مخفية ---
    schema_version: int = SETTINGS_SCHEMA_VERSION
    first_run_completed: bool = False
    window_geometry: str = ""  # base64 من QWidget.saveGeometry()
    # --- عام ---
    enabled: bool = True
    launch_at_login: bool = False
    start_hidden_in_tray: bool = True
    language: str = "auto"
    theme: str = "system"
    # --- المطر ---
    preset: str = "custom"
    intensity: float = 0.5
    speed: float = 1.0
    drop_length: float = 1.0
    drop_thickness: float = 1.0
    drop_opacity: float = 0.55
    drop_color: str = "#A9C7E8"
    parallax_strength: float = 0.7
    wind_angle_deg: float = 12.0
    wind_gusts: float = 0.25
    gust_period_s: float = 7.0
    # --- المؤثرات ---
    splashes_enabled: bool = True
    splash_amount: float = 0.5
    splash_zone: str = "bottom_edge"
    edge_streams_enabled: bool = True
    edge_streams_count: int = 3
    edge_streams_opacity: float = 0.35
    mood_enabled: bool = False
    mood_color: str = "#0B1A2B"
    mood_opacity: float = 0.15
    lightning_enabled: bool = False
    lightning_frequency: float = 0.3
    auto_weather: bool = False
    auto_weather_variability: float = 0.5
    sound_enabled: bool = False
    sound_volume: float = 0.35
    sound_follows_intensity: bool = True
    sound_wind: bool = True
    sound_thunder: bool = True
    # --- الشخصية ---
    mascot_enabled: bool = True
    mascot_frequency: float = 0.4
    mascot_scale: float = 1.0
    # --- العرض ---
    screens_mode: str = "all"
    selected_screens: list[str] = field(default_factory=list)
    cover_taskbar: bool = False
    quality: str = "balanced"
    fps_cap: int = 30
    antialiasing: bool = True
    pause_on_fullscreen: bool = True
    pause_on_battery_saver: bool = True
    exclude_from_capture: bool = False
    # --- متقدم ---
    adaptive_quality: bool = True
    depth_layers: int = 5
    topmost_watchdog: bool = True
    debug_hud: bool = False
    log_level: str = "INFO"
    rng_seed: int = -1  # -1 = عشوائي عند كل تشغيل


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """مواصفة حقل واحد.

    kind: أحد 'bool' و'int' و'float' و'str' و'choice' و'color' و'str_list'.
    minimum/maximum للأرقام، وchoices للاختيارات، وstep لخطوة المنزلق (وللأعداد الصحيحة
    ذات step أكبر من 1 يُقرَّب القيمة لأقرب مضاعف له)، وunit وحدة العرض في الواجهة.
    """

    key: str
    kind: str
    default: object
    minimum: float | None
    maximum: float | None
    choices: tuple[str, ...] | None
    step: float | None
    unit: str


@dataclass(frozen=True, slots=True)
class QualityProfile:
    """ملف جودة: يُكتب fps_cap وantialiasing في الإعدادات، أما drop_multiplier فتطبّقه
    طبقة العرض ولا يُخزَّن."""

    fps_cap: int
    antialiasing: bool
    drop_multiplier: float


# ---------------------------------------------------------------------------
# جدول المواصفات (مصدر الحقيقة للحدود والاختيارات)
# ---------------------------------------------------------------------------
def _bool(key: str, default: bool) -> FieldSpec:
    return FieldSpec(key, "bool", default, None, None, None, None, "")


def _int(
    key: str, default: int, lo: int, hi: int, step: float = 1.0, unit: str = ""
) -> FieldSpec:
    return FieldSpec(key, "int", default, float(lo), float(hi), None, step, unit)


def _float(
    key: str, default: float, lo: float, hi: float, step: float = 0.01, unit: str = ""
) -> FieldSpec:
    return FieldSpec(key, "float", default, lo, hi, None, step, unit)


def _choice(key: str, default: str, choices: tuple[str, ...]) -> FieldSpec:
    return FieldSpec(key, "choice", default, None, None, choices, None, "")


def _color(key: str, default: str) -> FieldSpec:
    return FieldSpec(key, "color", default, None, None, None, None, "")


def _str(key: str, default: str) -> FieldSpec:
    return FieldSpec(key, "str", default, None, None, None, None, "")


def _str_list(key: str) -> FieldSpec:
    return FieldSpec(
        key, "str_list", [], None, None, None, None, ""
    )  # الافتراضي لا يُعدَّل


_SPEC_LIST: Final[tuple[FieldSpec, ...]] = (
    _int(
        "schema_version",
        SETTINGS_SCHEMA_VERSION,
        SETTINGS_SCHEMA_VERSION,
        SETTINGS_SCHEMA_VERSION,
    ),
    _bool("first_run_completed", False),
    _str("window_geometry", ""),
    _bool("enabled", True),
    _bool("launch_at_login", False),
    _bool("start_hidden_in_tray", True),
    _choice("language", "auto", ("auto", "ar", "en")),
    _choice("theme", "system", ("system", "light", "dark")),
    _choice(
        "preset", "custom", ("custom", "drizzle", "light", "moderate", "heavy", "storm")
    ),
    _float("intensity", 0.5, 0.0, 1.0),
    _float("speed", 1.0, 0.25, 2.5),
    _float("drop_length", 1.0, 0.5, 2.0),
    _float("drop_thickness", 1.0, 0.5, 2.5),
    _float("drop_opacity", 0.55, 0.05, 1.0),
    _color("drop_color", "#A9C7E8"),
    _float("parallax_strength", 0.7, 0.0, 1.0),
    _float("wind_angle_deg", 12.0, -60.0, 60.0, step=0.5, unit="°"),
    _float("wind_gusts", 0.25, 0.0, 1.0),
    _float("gust_period_s", 7.0, 2.0, 20.0, step=0.5, unit="s"),
    _bool("splashes_enabled", True),
    _float("splash_amount", 0.5, 0.0, 1.0),
    _choice("splash_zone", "bottom_edge", ("bottom_edge", "depth_plane")),
    _bool("edge_streams_enabled", True),
    _int("edge_streams_count", 3, 1, 8),
    _float("edge_streams_opacity", 0.35, 0.05, 0.8),
    _bool("mood_enabled", False),
    _color("mood_color", "#0B1A2B"),
    _float("mood_opacity", 0.15, 0.0, 0.5),
    _bool("lightning_enabled", False),
    _float("lightning_frequency", 0.3, 0.0, 1.0),
    _bool("auto_weather", False),
    _float("auto_weather_variability", 0.5, 0.0, 1.0),
    _bool("sound_enabled", False),
    _float("sound_volume", 0.35, 0.0, 1.0),
    _bool("sound_follows_intensity", True),
    _bool("sound_wind", True),
    _bool("sound_thunder", True),
    _bool("mascot_enabled", True),
    _float("mascot_frequency", 0.4, 0.0, 1.0),
    _float("mascot_scale", 1.0, 0.5, 2.0),
    _choice("screens_mode", "all", ("all", "primary", "selected")),
    _str_list("selected_screens"),
    _bool("cover_taskbar", False),
    _choice("quality", "balanced", ("low", "balanced", "high")),
    _int("fps_cap", 30, 10, 60, step=5.0, unit="fps"),
    _bool("antialiasing", True),
    _bool("pause_on_fullscreen", True),
    _bool("pause_on_battery_saver", True),
    _bool("exclude_from_capture", False),
    _bool("adaptive_quality", True),
    _int("depth_layers", 5, 3, 8),
    _bool("topmost_watchdog", True),
    _bool("debug_hud", False),
    _choice("log_level", "INFO", ("DEBUG", "INFO", "WARNING", "ERROR")),
    _int("rng_seed", -1, -1, _INT_MAX),
)

FIELD_SPECS: Final[dict[str, FieldSpec]] = {spec.key: spec for spec in _SPEC_LIST}

# الإعدادات المسبقة: تُكتب حقولها الرقمية كما هي عند اختيار preset (مفاتيحها سبعة حقول).
PRESETS: Final[dict[str, dict[str, float]]] = {
    "drizzle": {
        "intensity": 0.18,
        "speed": 0.8,
        "drop_length": 0.7,
        "drop_thickness": 0.8,
        "drop_opacity": 0.4,
        "wind_angle_deg": 4.0,
        "wind_gusts": 0.1,
    },
    "light": {
        "intensity": 0.35,
        "speed": 0.95,
        "drop_length": 0.9,
        "drop_thickness": 0.9,
        "drop_opacity": 0.5,
        "wind_angle_deg": 8.0,
        "wind_gusts": 0.15,
    },
    "moderate": {
        "intensity": 0.55,
        "speed": 1.0,
        "drop_length": 1.0,
        "drop_thickness": 1.0,
        "drop_opacity": 0.55,
        "wind_angle_deg": 12.0,
        "wind_gusts": 0.25,
    },
    "heavy": {
        "intensity": 0.8,
        "speed": 1.2,
        "drop_length": 1.2,
        "drop_thickness": 1.1,
        "drop_opacity": 0.65,
        "wind_angle_deg": 18.0,
        "wind_gusts": 0.4,
    },
    "storm": {
        "intensity": 1.0,
        "speed": 1.5,
        "drop_length": 1.5,
        "drop_thickness": 1.3,
        "drop_opacity": 0.75,
        "wind_angle_deg": 28.0,
        "wind_gusts": 0.65,
    },
}

QUALITY_PROFILES: Final[dict[str, QualityProfile]] = {
    "low": QualityProfile(fps_cap=20, antialiasing=False, drop_multiplier=0.6),
    "balanced": QualityProfile(fps_cap=30, antialiasing=True, drop_multiplier=1.0),
    "high": QualityProfile(fps_cap=60, antialiasing=True, drop_multiplier=1.25),
}

# مجالات زر "عشوائي": كل مفتاح يُسحب منتظمًا من (أدنى، أعلى).
RANDOMIZE_RANGES: Final[dict[str, tuple[float, float]]] = {
    "intensity": (0.15, 0.95),
    "speed": (0.7, 1.6),
    "drop_length": (0.7, 1.4),
    "drop_opacity": (0.35, 0.75),
    "wind_angle_deg": (-35.0, 35.0),
    "wind_gusts": (0.05, 0.7),
}


# ---------------------------------------------------------------------------
# التحويل والتحقق (كل دالة ترفع ValueError عند قيمة غير صالحة ويلتقطها المستدعي)
# ---------------------------------------------------------------------------
def _round_half_up(x: float) -> int:
    """تقريب لأقرب عدد صحيح مع رفع نصف الوحدة للأعلى (بخلاف round الذي يقرّب للزوجي)."""
    return math.floor(x + 0.5)


def _to_finite_float(value: object) -> float:
    """يحوّل int أو float أو نصًا رقميًا إلى float منتهٍ؛ يرفض bool وNaN وinf وما يفيض."""
    if isinstance(value, bool):  # bool فرع من int في بايثون: نرفضه صراحةً كي لا يصبح 1.0
        raise ValueError("bool is not a number")
    try:
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            number = float(value.strip())
        else:
            raise ValueError(f"unsupported type: {type(value).__name__}")
    except OverflowError as exc:  # عدد صحيح أكبر من مجال float
        raise ValueError("number too large") from exc
    if not math.isfinite(number):
        raise ValueError("number is not finite")
    return number


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_TEXTS:
            return True
        if text in _FALSE_TEXTS:
            return False
    raise ValueError("not a boolean")


def _coerce_float(spec: FieldSpec, value: object) -> float:
    number = _to_finite_float(value)
    if spec.minimum is not None and spec.maximum is not None:
        return min(max(number, spec.minimum), spec.maximum)  # clamp إلى المجال
    return number


def _coerce_int(spec: FieldSpec, value: object) -> int:
    result = _round_half_up(_to_finite_float(value))
    if spec.step is not None and spec.step > 1:  # مثل fps_cap: مضاعفات 5
        result = int(_round_half_up(result / spec.step) * spec.step)
    if spec.minimum is not None and spec.maximum is not None:
        result = min(max(result, int(spec.minimum)), int(spec.maximum))
    return result


def _coerce_choice(spec: FieldSpec, value: object) -> str:
    if isinstance(value, str) and spec.choices is not None:
        lookup = {choice.lower(): choice for choice in spec.choices}
        match = lookup.get(
            value.strip().lower()
        )  # قبول اختلاف حالة الأحرف وإرجاع الصيغة القياسية
        if match is not None:
            return match
    raise ValueError("not an allowed choice")


def _coerce_color(value: object) -> str:
    if isinstance(value, str) and is_valid_hex(value.strip()):
        return rgb_to_hex(hex_to_rgb(value.strip()))  # توحيد الأحرف الكبيرة
    raise ValueError("not a #RRGGBB color")


def _coerce_str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise ValueError("not a string")


def _coerce_str_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [
            item for item in value if isinstance(item, str)
        ]  # تُسقَط العناصر غير النصية
    raise ValueError("not a list")


def _coerce_value(spec: FieldSpec, value: object) -> object:
    """يحوّل القيمة الخام إلى نوع الحقل ويقيّدها بمجاله، أو يرفع ValueError."""
    kind = spec.kind
    if kind == "bool":
        return _coerce_bool(value)
    if kind == "float":
        return _coerce_float(spec, value)
    if kind == "int":
        return _coerce_int(spec, value)
    if kind == "choice":
        return _coerce_choice(spec, value)
    if kind == "color":
        return _coerce_color(value)
    if kind == "str":
        return _coerce_str(value)
    if kind == "str_list":
        return _coerce_str_list(value)
    raise ValueError(f"unknown field kind: {kind!r}")


def default_settings() -> Settings:
    """نسخة جديدة مستقلة بالقيم الافتراضية."""
    return Settings()


def validate_and_coerce(raw: Mapping[str, object]) -> Settings:
    """يبني Settings من بيانات خام: clamp وcoercion، ويُسقط المجهول، ولا يرفع استثناءً أبدًا.

    القيمة غير الصالحة تعود لافتراضيها مع تحذير في السجل، والمفتاح الناقص يأخذ افتراضيه.
    لا ينفّذ الترحيل: استدعِ migrate() قبله. التعقيد O(عدد الحقول).
    """
    result = Settings()
    if not isinstance(raw, Mapping):
        _LOG.warning(
            "settings root is not an object (%s); using defaults", type(raw).__name__
        )
        return result
    for key, spec in FIELD_SPECS.items():
        if key not in raw:
            continue  # القيمة الافتراضية موجودة أصلًا في result
        try:
            setattr(result, key, _coerce_value(spec, raw[key]))
        except ValueError:
            _LOG.warning("invalid value for %s: %.80r; using default", key, raw[key])
    unknown = [name for name in raw if name not in FIELD_SPECS]
    if unknown:
        _LOG.debug("dropping unknown settings keys: %s", unknown)
    return result


def settings_to_dict(settings: Settings) -> dict[str, object]:
    """يحوّل Settings إلى قاموس مسطّح بترتيب المخطط (القوائم تُنسخ فلا تشترك بالحالة)."""
    data: dict[str, object] = {}
    for key in FIELD_SPECS:
        value = getattr(settings, key)
        data[key] = list(value) if isinstance(value, list) else value
    return data


# ---------------------------------------------------------------------------
# الترحيل
# ---------------------------------------------------------------------------
# تخطيط v0 اصطناعي (لم يُصدَر فعليًا): يُستخدم لإثبات أن سلسلة الترحيل تعمل ولاختبارها.
_V0_RENAMES: Final[dict[str, str]] = {"fps": "fps_cap", "rain_color": "drop_color"}


def _migrate_v0_to_v1(data: dict[str, object]) -> dict[str, object]:
    """v0 إلى v1: إعادة تسمية مفاتيح قديمة؛ المفتاح الجديد الموجود مسبقًا يبقى (له الأولوية)."""
    for old_key, new_key in _V0_RENAMES.items():
        if old_key in data:
            value = data.pop(old_key)
            data.setdefault(new_key, value)
    return data


# مفتاح القاموس = الإصدار المصدر، والدالة تنتج بنية الإصدار التالي (تعدّل النسخة الممرَّرة).
_MIGRATIONS: Final[dict[int, Callable[[dict[str, object]], dict[str, object]]]] = {
    0: _migrate_v0_to_v1,
}


def migrate(raw: dict[str, object]) -> dict[str, object]:
    """يرقّي بيانات إصدار أقدم إلى SETTINGS_SCHEMA_VERSION؛ دالة نقية (لا تعدّل المُدخل).

    غياب schema_version أو كونه غير صحيح يُعامَل كإصدار حالي (لا ترحيل)، وكذلك الإصدار
    الأحدث من الحالي (ملف من نسخة أحدث): تُترك بياناته كما هي ويتكفّل التحقق بإسقاط المجهول.
    """
    data = dict(raw)
    version = data.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        return data
    version = max(version, 0)
    while version < SETTINGS_SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            _LOG.warning("no migration from schema version %d", version)
            break
        data = step(data)
        version += 1
        data["schema_version"] = version
    return data
