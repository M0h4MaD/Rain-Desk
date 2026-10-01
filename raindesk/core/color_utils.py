"""raindesk/core/color_utils.py

الغرض: تحويلات الألوان بصيغة '#RRGGBB' وحساب التباين وفق WCAG 2.1.
المسؤوليات: التحقق من الصيغة، والتحويل بين hex وRGB، والإضاءة النسبية، ونسبة التباين.
الاعتماديات: المكتبة القياسية فقط.
النمط التصميمي: مجموعة دوال نقية بلا حالة (Pure Functions).
ملاحظات رياضية (WCAG 2.1):
    لكل قناة c = v / 255:  lin = c / 12.92  إن كانت c <= 0.03928، وإلا ((c + 0.055) / 1.055) ** 2.4
    L = 0.2126 R + 0.7152 G + 0.0722 B   (الأوزان تعكس حساسية العين: الأخضر أعلى ثم الأحمر فالأزرق)
    التباين = (L_light + 0.05) / (L_dark + 0.05)  وقيمته بين 1 و21؛ AA للنص العادي يتطلب 4.5.
مثال: contrast_ratio('#000000', '#FFFFFF')  # نحو 21
"""

from __future__ import annotations

import re
from typing import Final

_HEX_PATTERN: Final[re.Pattern[str]] = re.compile(r"#[0-9A-Fa-f]{6}")  # يُطابق بالكامل بـ fullmatch
_CHANNEL_MAX: Final[int] = 255  # أعلى قيمة لقناة 8 بت
_HEX_LENGTH: Final[int] = 7  # طول '#RRGGBB'

# ثوابت WCAG 2.1 لتحويل sRGB إلى ضوء خطي.
_LINEAR_THRESHOLD: Final[float] = 0.03928
_LINEAR_DIVISOR: Final[float] = 12.92
_GAMMA_OFFSET: Final[float] = 0.055
_GAMMA_SCALE: Final[float] = 1.055
_GAMMA_EXPONENT: Final[float] = 2.4
_WEIGHT_R: Final[float] = 0.2126
_WEIGHT_G: Final[float] = 0.7152
_WEIGHT_B: Final[float] = 0.0722
_CONTRAST_FLARE: Final[float] = 0.05  # يمثل الضوء المحيط في صيغة التباين


def is_valid_hex(value: str) -> bool:
    """يعيد True فقط للصيغة '#RRGGBB' (ستة أرقام سداسية عشرية، الحالتان مقبولتان).

    يقبل أي نوع مدخل ويعيد False لغير النصوص، لأن القيم قد تأتي من JSON غير موثوق.
    التعقيد: O(1).
    """
    return isinstance(value, str) and _HEX_PATTERN.fullmatch(value) is not None


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """يحوّل '#RRGGBB' إلى (R, G, B) بقيم 0..255.

    Raises:
        ValueError: إذا لم تكن الصيغة صحيحة.
    """
    if not is_valid_hex(value):
        raise ValueError(f"invalid hex color: {value!r}")
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """يحوّل (R, G, B) إلى '#RRGGBB' بأحرف كبيرة (الصيغة القياسية الموحّدة داخل المشروع).

    Raises:
        ValueError: إذا خرجت أي قناة عن المجال 0..255.
    """
    if any(not 0 <= channel <= _CHANNEL_MAX for channel in rgb):
        raise ValueError(f"RGB channel out of range 0..255: {rgb!r}")
    red, green, blue = rgb
    return f"#{red:02X}{green:02X}{blue:02X}"


def _linearize(channel: int) -> float:
    """يحوّل قناة sRGB (0..255) إلى ضوء خطي في [0, 1] وفق WCAG 2.1."""
    c = channel / _CHANNEL_MAX
    if c <= _LINEAR_THRESHOLD:
        return c / _LINEAR_DIVISOR  # مقطع خطي قرب الأسود لتفادي انحدار لا نهائي لمنحنى القوة
    return float(((c + _GAMMA_OFFSET) / _GAMMA_SCALE) ** _GAMMA_EXPONENT)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """الإضاءة النسبية L في [0, 1] (الأسود 0 والأبيض 1) وفق تعريف WCAG 2.1."""
    red, green, blue = rgb
    return (
        _WEIGHT_R * _linearize(red)
        + _WEIGHT_G * _linearize(green)
        + _WEIGHT_B * _linearize(blue)
    )


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """نسبة التباين بين لونين في [1, 21]؛ لا يهم أيهما الأمامي (الصيغة متماثلة).

    Raises:
        ValueError: إذا كان أحد اللونين غير صحيح.
    """
    lum_fg = relative_luminance(hex_to_rgb(fg_hex))
    lum_bg = relative_luminance(hex_to_rgb(bg_hex))
    lighter, darker = max(lum_fg, lum_bg), min(lum_fg, lum_bg)
    return (lighter + _CONTRAST_FLARE) / (darker + _CONTRAST_FLARE)