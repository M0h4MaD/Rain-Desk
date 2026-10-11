"""raindesk/engine/audio_noise.py

الغرض: أدوات ضجيج مشتركة بين مولّدات الصوت (المطر والرياح والرعد): نافذة نطاق طيفية وحلقة
    ضجيج دورية بالتشكيل الطيفي.
المسؤوليات: band_window (نافذة نطاق بمنحدرين ناعمين) وmake_loop (حلقة ستيريو دورية بدورة
    محددة بدقة وRMS ثابت).
الاعتماديات: NumPy فقط (بلا Qt).
النمط التصميمي: دوال نقية.
ملاحظات: الدورية مضمونة بالبناء: التحويل العكسي irfft لطيف معرَّف على شبكة N نقطة يعطي
    إشارة دورية بدورة N بالضبط، فلا قفزة عند الالتفاف ولا حاجة إلى مزج متقاطع (cross-fade).
    الأطوار مستقلة لكل قناة فتختلف القناتان (عرض ستيريو). نُقلت الدالتان من rain_audio.py
    دون تغيير في السلوك؛ ما زال rain_audio يعيد تصديرهما بالاسمين القديمين.
مثال: loop = make_loop(np.random.default_rng(1), 44100, 44100, 40.0, 500.0, -1.0)
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

CHANNELS: Final[int] = 2
TARGET_RMS: Final[float] = 0.2  # RMS كل حلقة بعد التطبيع
SKIRT_OCTAVES: Final[float] = 1.0 / 3.0  # عرض كل منحدر (skirt) بالأوكتاف
_TWO_PI: Final[float] = 2.0 * math.pi


def band_window(freq: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    """نافذة نطاق بمنحدرين من جيب التمام المرفوع (raised cosine) عرض كل منهما ثلث أوكتاف.

    المنحدر يتمركز على حافة النطاق (القيمة 0.5 عند الحافة نفسها)، ويُحسب في مجال log2
    لأن عرضه موصوف بالأوكتاف. خارج المنحدرين تكون القيمة 1 داخل النطاق و0 خارجه.
    """
    half = SKIRT_OCTAVES / 2.0
    log_f = np.log2(np.maximum(freq, 1e-9))  # التردد صفر (DC) يُحوَّل إلى قيمة سالبة جدًا
    rise = np.clip((log_f - (math.log2(low_hz) - half)) / SKIRT_OCTAVES, 0.0, 1.0)
    fall = np.clip(((math.log2(high_hz) + half) - log_f) / SKIRT_OCTAVES, 0.0, 1.0)
    window: np.ndarray = (0.5 * (1.0 - np.cos(math.pi * rise))) * (
        0.5 * (1.0 - np.cos(math.pi * fall))
    )
    return window


def make_loop(
    rng: np.random.Generator,
    samples: int,
    sample_rate: int,
    low_hz: float,
    high_hz: float,
    exponent: float,
) -> np.ndarray:
    """حلقة ضجيج ستيريو (samples, 2) float32 دورية بدورة samples بالضبط وRMS = 0.2 لكل قناة.

    الخطوات: السعة |X(f)| = f^exponent داخل النطاق، والأطوار موحّدة التوزيع عشوائيًا لكل
    قناة، ثم irfft.
    """
    freq = np.fft.rfftfreq(samples, 1.0 / sample_rate)
    magnitude = band_window(freq, low_hz, high_hz) * np.power(np.maximum(freq, 1.0), exponent)
    magnitude[0] = 0.0  # لا مركّبة DC
    loop = np.empty((samples, CHANNELS), np.float64)
    for channel in range(CHANNELS):
        phase = rng.uniform(0.0, _TWO_PI, freq.size)
        signal = np.fft.irfft(magnitude * np.exp(1j * phase), n=samples)
        signal -= signal.mean()  # إزالة أي DC متبقٍ من التقريب
        rms = float(np.sqrt(np.mean(signal**2)))
        loop[:, channel] = signal * (TARGET_RMS / rms if rms > 0.0 else 0.0)
    return loop.astype(np.float32)
