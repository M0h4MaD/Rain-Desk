"""raindesk/engine/rain_audio.py

الغرض: صوت مطر مولَّد برمجيًا بالكامل (بلا ملفات صوت): فراش مطر مستمر، ونقرات قطرات فردية،
    وهبّة رياح تتعدّل بإشارة العصف.
المسؤوليات: بناء حلقات ضجيج دورية بالتشكيل الطيفي، وبنك نقرات قطرات، وجدولة أحداث بواسون،
    ومزج الطبقات بمنحدرات خطية للكسب، وقص ناعم للمخرج، وإخراج float32 أو int16.
الاعتماديات: NumPy وraindesk.core.constants وraindesk.engine.math_utils.
النمط التصميمي: Block-based Synthesizer ذو حالة (مواضع الحلقات والذيل والكسب بين الكتل).
ملاحظات رياضية:
    1) الحلقة الدورية: نبني طيفًا على شبكة N نقطة (سعة مشكَّلة وأطوار عشوائية) ونعكسه بـ irfft.
       مبرهنة: التحويل العكسي المنفصل لطيف معرَّف على شبكة N نقطة يعطي إشارة دورية بدورة N
       بالضبط، فالعينة x[N] تساوي x[0] بالبناء، وتكرار القراءة بلا قفزة ودون مزج متقاطع
       (cross-fade). نستعمل أطوارًا مستقلة لكل قناة فتختلف القناتان (عرض ستيريو).
    2) قص المخرج: y = 0.98 * tanh(1.2 x). لأن |tanh| < 1 فالمخرج لا يتجاوز 0.98 أبدًا مهما
       كانت الكتل المجموعة، والإشارات الصغيرة تبقى شبه خطية (الميل 0.98 * 1.2 = 1.18)، فلا يُسمع
       تشويه عند المستويات المنخفضة، ولا يحدث قص حاد (hard clipping) المزعج.
    3) حبّات السكون (zipper noise): كل كسب يتغير بمنحدر خطي عبر الكتلة لا بخطوة.
مثال: synth = RainSynth(np.random.default_rng(1)); block = synth.render(882, params)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np

from raindesk.core.constants import (
    AUDIO_DROPLET_BANK_SIZE,
    AUDIO_LOOP_SECONDS,
    AUDIO_MAX_DROPLETS_PER_S,
    AUDIO_SAMPLE_RATE,
)
from raindesk.engine.math_utils import clamp

_CHANNELS: Final[int] = 2
_TARGET_RMS: Final[float] = 0.2  # RMS كل حلقة بعد التطبيع
_SKIRT_OCTAVES: Final[float] = 1.0 / 3.0  # عرض كل منحدر (skirt) بالأوكتاف
_TWO_PI: Final[float] = 2.0 * math.pi
_INT16_MAX: Final[int] = 32767
_SOFT_CLIP_LIMIT: Final[float] = 0.98
_SOFT_CLIP_DRIVE: Final[float] = 1.2

# --- أشكال الحلقات: (الحد الأدنى Hz، الحد الأعلى Hz، أس التردد في السعة) ---
_BED_MID: Final[tuple[float, float, float]] = (300.0, 9000.0, -0.5)  # وردي (-3 dB/أوكتاف)
_BED_HIGH: Final[tuple[float, float, float]] = (4000.0, 12000.0, 0.0)  # مسطّح
_WIND: Final[tuple[float, float, float]] = (40.0, 500.0, -1.0)  # -6 dB/أوكتاف

# --- بنك القطرات ---
# نواة مرشح النطاق لنقرات القطرات (انظر _make_droplet_bank).
_DROPLET_KERNEL: Final[np.ndarray] = np.array([1.0, 1.0, -1.0, -1.0])
_DROPLET_MIN_S: Final[float] = 0.020
_DROPLET_MAX_S: Final[float] = 0.060
_DROPLET_TAU_MIN_S: Final[float] = 0.003
_DROPLET_TAU_MAX_S: Final[float] = 0.010
_BUBBLE_FRACTION: Final[float] = 0.60  # نسبة النقرات التي تحوي رنين فقاعة
_BUBBLE_F0_MIN_HZ: Final[float] = 1200.0  # Minnaert: f تقريبًا 3.26 / r (r بالمتر)
_BUBBLE_F0_MAX_HZ: Final[float] = 5000.0
_BUBBLE_CHIRP: Final[float] = 0.15  # ارتفاع التردد 15% خلال أول 8 ms
_BUBBLE_CHIRP_S: Final[float] = 0.008
_BUBBLE_TAU_MIN_S: Final[float] = 0.005
_BUBBLE_TAU_MAX_S: Final[float] = 0.014
_BUBBLE_LEVEL: Final[float] = 0.8  # سعة الرنين نسبةً لانفجار الضجيج قبل التطبيع
_FADE_IN_S: Final[float] = 0.001  # 1 ms: يمنع نقرة بداية كل قطرة
_DROP_RATE_EXPONENT: Final[float] = 1.2
_DROP_GAIN_MIN: Final[float] = 0.15  # الكسب U(0.15, 1.0) ** 2


@dataclass(slots=True)
class AudioParams:
    """معاملات كتلة صوت: intensity وwind_amount وmaster في [0, 1]، وgust في [-1, 1]."""

    intensity: float
    wind_amount: float
    gust: float
    master: float
    wind_enabled: bool


def _band_window(freq: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    """نافذة نطاق بمنحدرين من جيب التمام المرفوع (raised cosine) عرض كل منهما ثلث أوكتاف.

    المنحدر يتمركز على حافة النطاق (القيمة 0.5 عند الحافة نفسها)، ويُحسب في مجال log2
    لأن عرضه موصوف بالأوكتاف. خارج المنحدرين تكون القيمة 1 داخل النطاق و0 خارجه.
    """
    half = _SKIRT_OCTAVES / 2.0
    log_f = np.log2(np.maximum(freq, 1e-9))  # التردد صفر (DC) يُحوَّل إلى قيمة سالبة جدًا
    rise = np.clip((log_f - (math.log2(low_hz) - half)) / _SKIRT_OCTAVES, 0.0, 1.0)
    fall = np.clip(((math.log2(high_hz) + half) - log_f) / _SKIRT_OCTAVES, 0.0, 1.0)
    return (0.5 * (1.0 - np.cos(math.pi * rise))) * (0.5 * (1.0 - np.cos(math.pi * fall)))


def _make_loop(
    rng: np.random.Generator,
    samples: int,
    sample_rate: int,
    low_hz: float,
    high_hz: float,
    exponent: float,
) -> np.ndarray:
    """حلقة ضجيج ستيريو (samples, 2) float32 دورية بدورة samples بالضبط وRMS = 0.2 لكل قناة.

    الخطوات: السعة |X(f)| = f^exponent داخل النطاق، والأطوار موحّدة التوزيع عشوائيًا لكل
    قناة، ثم irfft. الدورية بدقة مضمونة بالبناء (انظر الملاحظات في رأس الملف).
    """
    freq = np.fft.rfftfreq(samples, 1.0 / sample_rate)
    magnitude = _band_window(freq, low_hz, high_hz) * np.power(np.maximum(freq, 1.0), exponent)
    magnitude[0] = 0.0  # لا مركّبة DC
    loop = np.empty((samples, _CHANNELS), np.float64)
    for channel in range(_CHANNELS):
        phase = rng.uniform(0.0, _TWO_PI, freq.size)
        signal = np.fft.irfft(magnitude * np.exp(1j * phase), n=samples)
        signal -= signal.mean()  # إزالة أي DC متبقٍ من التقريب
        rms = float(np.sqrt(np.mean(signal**2)))
        loop[:, channel] = signal * (_TARGET_RMS / rms if rms > 0.0 else 0.0)
    return loop.astype(np.float32)


class _Loop:
    """حلقة مع موضع قراءة خاص بها؛ read ينسخ كتلة بشريحتين متجاورتين عند الالتفاف."""

    def __init__(self, data: np.ndarray, start: int) -> None:
        self.data = data
        self.position = start % data.shape[0]

    def read_into(self, out: np.ndarray) -> None:
        """يملأ out (frames, 2) من الحلقة ويقدّم الموضع بمقدار frames modulo N."""
        total = self.data.shape[0]
        written = 0
        frames = out.shape[0]
        while written < frames:
            take = min(frames - written, total - self.position)
            out[written : written + take] = self.data[self.position : self.position + take]
            written += take
            self.position = (self.position + take) % total


class RainSynth:
    """مولّد صوت المطر بالكتل. الحالة بين الاستدعاءات: مواضع الحلقات والكسب والذيل."""

    def __init__(
        self,
        rng: np.random.Generator,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        loop_seconds: float = AUDIO_LOOP_SECONDS,
        droplet_bank_size: int = AUDIO_DROPLET_BANK_SIZE,
    ) -> None:
        self._rng = rng
        self._sample_rate = int(sample_rate)
        samples = max(round(loop_seconds * self._sample_rate), 2)
        specs: dict[str, tuple[float, float, float]] = {
            "bed_mid": _BED_MID, "bed_high": _BED_HIGH, "wind": _WIND,
        }
        self._loops: dict[str, _Loop] = {}
        for name, (low, high, exponent) in specs.items():
            data = _make_loop(rng, samples, self._sample_rate, low, high, exponent)
            self._loops[name] = _Loop(data, int(rng.integers(0, samples)))  # إزاحة بدء عشوائية
        self._bank, self._bank_lengths = self._make_droplet_bank(max(int(droplet_bank_size), 1))
        self._max_len = int(self._bank_lengths.max())
        self._tail = np.zeros((self._max_len, _CHANNELS), np.float32)
        self._scratch = np.zeros((0, _CHANNELS), np.float32)
        self._layers = {
            name: np.zeros((0, _CHANNELS), np.float32) for name in ("bed_mid", "bed_high", "wind")
        }
        self._previous_gains: dict[str, float] | None = None  # None = أول كتلة: بلا منحدر
        self.events_last_render = 0

    # ------------------------------------------------------------------ خصائص
    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def loop(self, name: str) -> np.ndarray:
        """نسخة قراءة فقط من حلقة ('bed_mid' أو 'bed_high' أو 'wind') للاختبار والتحليل."""
        view = self._loops[name].data.view()
        view.flags.writeable = False
        return view

    def reset(self) -> None:
        """يمسح الذيل والكسب السابق (تبدأ الكتلة التالية بلا منحدر من قيم قديمة)."""
        self._tail[:] = 0.0
        self._previous_gains = None
        self.events_last_render = 0

    # ------------------------------------------------------------------ بنك القطرات
    def _make_droplet_bank(self, size: int) -> tuple[np.ndarray, np.ndarray]:
        """(bank، lengths): نقرات أحادية 20 إلى 60 ms مطبَّعة الذروة ومصفّرة الحشو.

        كل نقرة: ضجيج أبيض مرشَّح بنواة h = [1, 1, -1, -1] (جداء (1 + z^-1)(1 - z^-2)): تمرير
        عالٍ بمنحدر +6 dB/أوكتاف عند الترددات المنخفضة مع صفر عند Nyquist، فلا حدّة رقمية بين
        عينتين متجاورتين كما في الفرق الأول وحده (تتركز الطاقة بين نحو 2 و12 kHz، ووسيطها
        قرابة 4.8 kHz بالقياس)، مضروبة بغلاف أسّي بثابت زمن 3 إلى 10 ms. نحو 60% منها فيها
        رنين فقاعة: جيب مخمَّد بتردد f0 في [1.2, 5.0] kHz مع زقزقة صاعدة بنسبة 15% خلال أول
        8 ms (فقاعة الهواء ترنّ بتردد يتناسب عكسيًا مع نصف قطرها: Minnaert، f ≈ 3.26 / r هرتز).
        """
        rng, rate = self._rng, self._sample_rate
        lengths = rng.integers(
            round(_DROPLET_MIN_S * rate), round(_DROPLET_MAX_S * rate) + 1, size
        )
        bank = np.zeros((size, int(lengths.max())), np.float32)
        bubble_ids = set(rng.permutation(size)[: round(_BUBBLE_FRACTION * size)].tolist())
        for index in range(size):
            length = int(lengths[index])
            time = np.arange(length) / rate
            noise = np.convolve(rng.standard_normal(length + 3), _DROPLET_KERNEL, mode="valid")
            burst = noise * np.exp(-time / rng.uniform(_DROPLET_TAU_MIN_S, _DROPLET_TAU_MAX_S))
            burst /= max(float(np.abs(burst).max()), 1e-12)
            if index in bubble_ids:
                f0 = rng.uniform(_BUBBLE_F0_MIN_HZ, _BUBBLE_F0_MAX_HZ)
                glide = np.minimum(time / _BUBBLE_CHIRP_S, 1.0)
                frequency = f0 * (1.0 + _BUBBLE_CHIRP * glide)
                phase = _TWO_PI * np.cumsum(frequency) / rate  # تكامل التردد = الطور
                decay = np.exp(-time / rng.uniform(_BUBBLE_TAU_MIN_S, _BUBBLE_TAU_MAX_S))
                burst = burst + _BUBBLE_LEVEL * np.sin(phase) * decay
            burst = burst * np.minimum(time / _FADE_IN_S, 1.0)  # ظهور خلال 1 ms يمنع النقرة
            burst /= max(float(np.abs(burst).max()), 1e-12)
            bank[index, :length] = burst
        return bank, lengths.astype(np.int64)

    # ------------------------------------------------------------------ الكسب والجدولة
    @staticmethod
    def _target_gains(params: AudioParams) -> dict[str, float]:
        """كسب الطبقات من المعاملات: i = clamp(intensity, 0, 1)، وG إشارة العصف في [-1, 1]."""
        level = clamp(params.intensity, 0.0, 1.0)
        gust = clamp(params.gust, -1.0, 1.0)
        wind = 0.0
        if params.wind_enabled:
            wind = 0.8 * clamp(params.wind_amount, 0.0, 1.0) * (0.6 + 0.4 * (gust + 1.0) / 2.0)
        return {
            "mid": 0.15 + 0.85 * level**0.8,
            "high": 0.75 * level**1.5,
            "droplets": 0.9 * level**0.7,
            "wind": wind,
            "master": clamp(params.master, 0.0, 1.0),
        }

    def _ramp(
        self, name: str, target: float, frames: int, previous: dict[str, float]
    ) -> np.ndarray:
        """منحدر خطي من قيمة الكتلة السابقة إلى الهدف عند آخر عينة (بلا خطوات = بلا zipper)."""
        start = previous.get(name, target)
        return np.linspace(start, target, frames + 1, dtype=np.float32)[1:]

    def _schedule_droplets(self, frames: int, level: float) -> np.ndarray:
        """يراكم نقرات هذه الكتلة (وذيل الكتلة السابقة) في مخزن ستيريو ويعيد عرض أول frames منه."""
        needed = frames + self._max_len
        if self._scratch.shape[0] < needed:
            self._scratch = np.zeros((needed, _CHANNELS), np.float32)  # يكبر مرة ثم يستقر
        acc = self._scratch[:needed]
        acc[:] = 0.0
        acc[: self._max_len] += self._tail  # ذيل نقرات الكتل السابقة
        rate_per_s = AUDIO_MAX_DROPLETS_PER_S * level**_DROP_RATE_EXPONENT
        events = int(self._rng.poisson(rate_per_s * frames / self._sample_rate))
        self.events_last_render = events
        for _ in range(events):
            index = int(self._rng.integers(0, self._bank.shape[0]))
            start = int(self._rng.integers(0, frames))
            pan = float(self._rng.uniform(0.0, 1.0))
            gain = float(self._rng.uniform(_DROP_GAIN_MIN, 1.0)) ** 2
            length = int(self._bank_lengths[index])
            sample = self._bank[index, :length] * gain
            acc[start : start + length, 0] += sample * math.cos(pan * math.pi / 2.0)  # قدرة متساوية
            acc[start : start + length, 1] += sample * math.sin(pan * math.pi / 2.0)
        self._tail[:] = acc[frames : frames + self._max_len]
        return acc[:frames]

    # ------------------------------------------------------------------ التوليد
    def render(self, frames: int, params: AudioParams) -> np.ndarray:
        """كتلة (frames, 2) float32 في [-0.98, 0.98]؛ تحفظ الحالة بين الاستدعاءات."""
        if frames <= 0:
            return np.zeros((0, _CHANNELS), np.float32)
        gains = self._target_gains(params)
        previous = gains if self._previous_gains is None else self._previous_gains
        for name, layer in self._layers.items():
            if layer.shape[0] < frames:
                self._layers[name] = np.zeros((frames, _CHANNELS), np.float32)
        mix = np.zeros((frames, _CHANNELS), np.float32)
        for name, key in (("bed_mid", "mid"), ("bed_high", "high"), ("wind", "wind")):
            block = self._layers[name][:frames]
            self._loops[name].read_into(block)
            block *= self._ramp(key, gains[key], frames, previous)[:, None]
            mix += block
        droplets = self._schedule_droplets(frames, clamp(params.intensity, 0.0, 1.0))
        mix += droplets * self._ramp("droplets", gains["droplets"], frames, previous)[:, None]
        mix *= self._ramp("master", gains["master"], frames, previous)[:, None]
        self._previous_gains = gains
        # قص ناعم: المخرج لا يتجاوز 0.98 (انظر الملاحظات في رأس الملف).
        np.tanh(_SOFT_CLIP_DRIVE * mix, out=mix)
        mix *= _SOFT_CLIP_LIMIT
        return mix

    def render_int16(self, frames: int, params: AudioParams) -> bytes:
        """نفس render لكن بصيغة int16 little-endian متشابكة القنوات (L, R, L, R...)."""
        block = self.render(frames, params)
        return np.rint(block * _INT16_MAX).astype("<i2").tobytes()