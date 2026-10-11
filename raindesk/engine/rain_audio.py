"""raindesk/engine/rain_audio.py

الغرض: صوت مطر مولَّد برمجيًا بالكامل (بلا ملفات صوت): فراش مطر مستمر، ونقرات قطرات فردية،
    ورياح من خمس طبقات (جسم وهبوب وحفيف وصفير) تتعدّل بإشارة العصف وتتنفّس ببطء، ورعد بثلاث
    مسافات (قريب ومتوسط وبعيد) يلي وميض البرق.
المسؤوليات: مزج حلقات الضجيج الدورية (المبنية في audio_noise) وبنك نقرات قطرات، وجدولة أحداث
    بواسون، وجدولة الرعد (التأخير والكسب واختيار النوع)، ومنحدرات خطية للكسب، وقص ناعم
    للمخرج، وإخراج float32 أو int16.
الاعتماديات: NumPy وraindesk.core.constants وraindesk.engine (math_utils وweather_fsm
    وaudio_noise وwind_model وthunder_synth).
النمط التصميمي: Block-based Synthesizer ذو حالة (مواضع الحلقات والذيل والكسب بين الكتل).
ملاحظات رياضية:
    1) الحلقة الدورية: طيف على شبكة N نقطة (سعة مشكَّلة وأطوار عشوائية) ثم irfft: دورية بدورة
       N بالضبط بالبناء (التفاصيل في audio_noise.py).
    2) قص المخرج: y = 0.98 * tanh(1.2 x). لأن |tanh| < 1 فالمخرج لا يتجاوز 0.98 أبدًا مهما
       كانت الكتل المجموعة، والإشارات الصغيرة تبقى شبه خطية (الميل 0.98 * 1.2 = 1.18)، فلا يُسمع
       تشويه عند المستويات المنخفضة، ولا يحدث قص حاد (hard clipping) المزعج.
    3) حبّات السكون (zipper noise): كل كسب يتغير بمنحدر خطي عبر الكتلة لا بخطوة.
    4) الرعد: يصل بعد الوميض بتأخير d / 343 ثانية (سرعة الصوت 343 m/s)، فنعيّن التأخير بين 0.4 s
       (نحو 137 m) و6 s (نحو 2 km). يُختار نوع العيّنة (قريب أو متوسط أو بعيد) من المسافة:
       القريب فرقعة متعددة الانفجارات وضربة ودمدمة حتى 900 Hz، والبعيد دمدمة ناعمة بلا فرقعة
       (الهواء يمتص العالي أكثر). تفاصيل البناء في thunder_synth.py.
    5) الرياح: خمس حلقات بأطوال غير متناسبة تُمزج بكسب يتبع قوة الرياح والعصفة (wind_model.py)،
       مع تنفّس بطيء مستقل. بعد وصول رعد قريب تتصاعد العصفة الفعّالة لثوانٍ (kick) فتعلو الرياح
       بعد الرعد كما يحدث قبل العواصف.
مثال: synth = RainSynth(np.random.default_rng(1)); block = synth.render(882, params)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Final

import numpy as np

from raindesk.core.constants import (
    AUDIO_DROPLET_BANK_SIZE,
    AUDIO_LOOP_SECONDS,
    AUDIO_MAX_DROPLETS_PER_S,
    AUDIO_SAMPLE_RATE,
)
from raindesk.engine.audio_noise import band_window as _band_window  # noqa: F401  (توافق)
from raindesk.engine.audio_noise import make_loop as _make_loop
from raindesk.engine.math_utils import clamp, lerp
from raindesk.engine.thunder_synth import (
    KINDS,
    ThunderSample,
    kind_for_distance,
    make_thunder_sample,
)
from raindesk.engine.weather_fsm import LIGHTNING_PEAK_MAX
from raindesk.engine.wind_model import (
    BREATH_DEPTH,
    EXTRA_LAYERS,
    WIND_LOOP_SPECS,
    Breath,
    wind_extra_gains,
)

_CHANNELS: Final[int] = 2
_TWO_PI: Final[float] = 2.0 * math.pi
_INT16_MAX: Final[int] = 32767
_SOFT_CLIP_LIMIT: Final[float] = 0.98
_SOFT_CLIP_DRIVE: Final[float] = 1.2

# --- أشكال الحلقات: (الحد الأدنى Hz، الحد الأعلى Hz، أس التردد في السعة) ---
_BED_MID: Final[tuple[float, float, float]] = (300.0, 9000.0, -0.5)  # وردي (-3 dB/أوكتاف)
_BED_HIGH: Final[tuple[float, float, float]] = (4000.0, 12000.0, 0.0)  # مسطّح

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

# --- الرعد (الأنواع وأطيافها في thunder_synth) ---
_THUNDER_LEVEL: Final[float] = 0.6  # ذروة الرعد القريب جدًا قبل القص (يبقى أهدأ من أن يفزع)
_THUNDER_VARIANTS: Final[int] = 2  # عدد الصيغ المولَّدة لكل نوع (تنوّع بين الأحداث)
_THUNDER_DELAY_MIN_S: Final[float] = 0.4  # نحو 137 m عند 343 m/s
_THUNDER_DELAY_MAX_S: Final[float] = 6.0  # نحو 2 km
_THUNDER_MAX_VOICES: Final[int] = 4  # أقصى رعود متزامنة (الأقدم يُسقَط)
_THUNDER_GAIN_FLOOR: Final[float] = 0.4  # كسب الرعد البعيد جدًا نسبةً للقريب جدًا
_THUNDER_CLOSENESS_EXPONENT: Final[float] = 1.5
_THUNDER_RANDOM_WEIGHT: Final[float] = 0.3  # وزن العشوائية في المسافة (الباقي من سطوع الوميض)
_KICK_AMOUNT: Final[float] = 0.35  # دفع العصفة بعد رعد قريب جدًا (في مقياس g في [0, 1])
_KICK_TAU_S: Final[float] = 2.5  # ثابت تلاشي دفع العصفة
_FLASH_MIN_FRACTION: Final[float] = 0.4  # أخفت وميض = 0.12 / 0.30 من الذروة العظمى


@dataclass(slots=True)
class AudioParams:
    """معاملات كتلة صوت: intensity وwind_amount وmaster في [0, 1]، وgust في [-1, 1].

    wind_level وthunder_level مضاعفا مستوى الرياح والرعد في [0, 2] (1 = المستوى الأصلي، 0 =
    صامت، 2 = ضعف)؛ يُطبَّقان عند المزج فيؤثران في الرعد الجاري فور تحريك المنزلق.
    """

    intensity: float
    wind_amount: float
    gust: float
    master: float
    wind_enabled: bool
    thunder_level: float = 1.0
    wind_level: float = 1.0


@dataclass(slots=True)
class _ThunderVoice:
    """رعد قيد التشغيل: ينتظر delay عيّنة ثم يُقرأ من position بكسب gain."""

    sample: ThunderSample
    delay: int
    position: int
    gain: float
    crack_gain: float
    kick: float = 0.0  # دفع العصفة الذي يبدأ عند وصول هذا الرعد


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
    """مولّد صوت المطر بالكتل. الحالة بين الاستدعاءات: مواضع الحلقات والكسب والذيل والرعود."""

    def __init__(
        self,
        rng: np.random.Generator,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        loop_seconds: float = AUDIO_LOOP_SECONDS,
        droplet_bank_size: int = AUDIO_DROPLET_BANK_SIZE,
        prebuild_thunder: bool = False,
    ) -> None:
        """prebuild_thunder=True يبني عيّنات الرعد هنا (للاستدعاء من خيط خلفي) بدل أول رعد."""
        self._rng = rng
        self._sample_rate = int(sample_rate)
        samples = max(round(loop_seconds * self._sample_rate), 2)
        specs: dict[str, tuple[float, float, float, float | None]] = {
            "bed_mid": (*_BED_MID, None),
            "bed_high": (*_BED_HIGH, None),
            **WIND_LOOP_SPECS,
        }
        self._loops: dict[str, _Loop] = {}
        for name, (low, high, exponent, seconds) in specs.items():
            length = samples if seconds is None else max(round(seconds * self._sample_rate), 2)
            data = _make_loop(rng, length, self._sample_rate, low, high, exponent)
            self._loops[name] = _Loop(data, int(rng.integers(0, length)))  # إزاحة بدء عشوائية
        self._bank, self._bank_lengths = self._make_droplet_bank(max(int(droplet_bank_size), 1))
        self._max_len = int(self._bank_lengths.max())
        self._tail = np.zeros((self._max_len, _CHANNELS), np.float32)
        self._scratch = np.zeros((0, _CHANNELS), np.float32)
        self._layers = {name: np.zeros((0, _CHANNELS), np.float32) for name in self._loops}
        self._previous_gains: dict[str, float] | None = None  # None = أول كتلة: بلا منحدر
        self.events_last_render = 0
        self._thunder_bank: dict[str, list[ThunderSample]] = {}  # يُبنى مرة واحدة (prepare_thunder)
        self._voices: list[_ThunderVoice] = []
        self._breath = Breath(rng)  # تنفّس الرياح البطيء
        self._kick = 0.0  # دفع العصفة بعد وصول رعد (يتلاشى أسّيًا)
        if prebuild_thunder:
            self.prepare_thunder()

    # ------------------------------------------------------------------ خصائص
    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def thunder_voice_count(self) -> int:
        """عدد الرعود الجارية حاليًا (المنتظرة والمُشغَّلة)."""
        return len(self._voices)

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
        self._voices = []
        self._kick = 0.0

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
        lengths = rng.integers(round(_DROPLET_MIN_S * rate), round(_DROPLET_MAX_S * rate) + 1, size)
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

    # ------------------------------------------------------------------ الرعد
    @staticmethod
    def thunder_delay_s(distance: float) -> float:
        """التأخير بين الوميض والرعد: lerp(0.4, 6.0, distance) ثانية (distance في [0, 1])."""
        return lerp(_THUNDER_DELAY_MIN_S, _THUNDER_DELAY_MAX_S, clamp(distance, 0.0, 1.0))

    def prepare_thunder(self) -> None:
        """يبني عيّنات الرعد لكل الأنواع (نحو 0.4 s إجمالًا على حاسوب عادي)؛ آمنة من أي خيط.

        يُفضَّل استدعاؤها (أو prebuild_thunder=True) من خيط خلفي كي لا يتعطل الرسم عند أول
        وميض؛ وإن لم تُستدعَ يبنيها أول trigger_thunder على الخيط الذي استُدعي منه.
        """
        if self._thunder_bank:
            return
        self._thunder_bank = {
            kind: [
                make_thunder_sample(self._rng, self._sample_rate, kind)
                for _ in range(_THUNDER_VARIANTS)
            ]
            for kind in KINDS
        }

    def trigger_thunder(self, flash_peak: float) -> None:
        """يجدول رعدًا يلي وميضًا بشدة flash_peak (من نموذج البرق، حتى 0.30).

        المسافة المفترضة d في [0, 1]: 70% من سطوع الوميض (الأسطع أقرب) و30% عشوائية. يترتب
        عليها: نوع العيّنة (قريب لـ d < 0.30 ومتوسط لـ d < 0.65 وإلا بعيد)، والتأخير
        lerp(0.4, 6, d) ثانية، والكسب 0.6 * (0.4 + 0.6 (1 - d)^1.5)، وكسب الفرقعة
        (1 - d)^2، ودفع عصفة 0.35 (1 - d) يبدأ عند وصول الرعد. أقصى 4 رعود متزامنة؛ الأقدم
        يُسقَط.
        """
        self.prepare_thunder()  # لا شيء إن كانت جاهزة
        brightness = clamp(flash_peak / LIGHTNING_PEAK_MAX, 0.0, 1.0)
        closeness = clamp(
            (brightness - _FLASH_MIN_FRACTION) / (1.0 - _FLASH_MIN_FRACTION), 0.0, 1.0
        )
        distance = clamp(
            (1.0 - _THUNDER_RANDOM_WEIGHT) * (1.0 - closeness)
            + _THUNDER_RANDOM_WEIGHT * float(self._rng.uniform(0.0, 1.0)),
            0.0,
            1.0,
        )
        near = 1.0 - distance
        gain = _THUNDER_GAIN_FLOOR + (1.0 - _THUNDER_GAIN_FLOOR) * near**_THUNDER_CLOSENESS_EXPONENT
        variants = self._thunder_bank[kind_for_distance(distance)]
        sample = variants[int(self._rng.integers(0, len(variants)))]
        self._voices.append(
            _ThunderVoice(
                sample=sample,
                delay=round(self.thunder_delay_s(distance) * self._sample_rate),
                position=0,
                gain=_THUNDER_LEVEL * gain,
                crack_gain=near**2,
                kick=_KICK_AMOUNT * near,
            )
        )
        if len(self._voices) > _THUNDER_MAX_VOICES:
            self._voices.pop(0)

    def _mix_thunder(self, mix: np.ndarray, frames: int, level: float = 1.0) -> None:
        """يضيف الرعود الجارية إلى mix؛ التأخير والموضع بالعينات فلا يتأثران بحجم الكتلة."""
        kept: list[_ThunderVoice] = []
        for voice in self._voices:
            offset = 0
            if voice.delay > 0:
                if voice.delay >= frames:
                    voice.delay -= frames  # لم يحن موعده في هذه الكتلة
                    kept.append(voice)
                    continue
                offset, voice.delay = voice.delay, 0  # يبدأ داخل هذه الكتلة
            if voice.position == 0:
                self._kick = max(self._kick, voice.kick)  # وصل الرعد: تتصاعد العصفة لثوانٍ
            rumble, crack = voice.sample.rumble, voice.sample.crack
            count = min(frames - offset, rumble.shape[0] - voice.position)
            if count > 0:
                segment = rumble[voice.position : voice.position + count] * (voice.gain * level)
                crack_count = min(count, crack.shape[0] - voice.position)
                if crack_count > 0:
                    segment[:crack_count] += crack[
                        voice.position : voice.position + crack_count
                    ] * (voice.gain * voice.crack_gain)
                mix[offset : offset + count] += segment
                voice.position += count
            if voice.position < rumble.shape[0]:
                kept.append(voice)
        self._voices = kept

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
        self._kick *= math.exp(-frames / (self._sample_rate * _KICK_TAU_S))
        breath = self._breath.step(frames / self._sample_rate)
        gust = clamp(params.gust + 2.0 * self._kick, -1.0, 1.0)  # الدفع في مقياس g = (G+1)/2
        gains = self._target_gains(replace(params, gust=gust))
        if params.wind_enabled:
            gains["wind"] *= 1.0 + BREATH_DEPTH * breath
            gains.update(wind_extra_gains(params.wind_amount, gust, breath))
        else:
            gains.update(dict.fromkeys(EXTRA_LAYERS, 0.0))
        wind_level = clamp(params.wind_level, 0.0, 2.0)
        for name in ("wind", *EXTRA_LAYERS):
            gains[name] *= wind_level
        previous = gains if self._previous_gains is None else self._previous_gains
        for name, layer in self._layers.items():
            if layer.shape[0] < frames:
                self._layers[name] = np.zeros((frames, _CHANNELS), np.float32)
        mix = np.zeros((frames, _CHANNELS), np.float32)
        layer_keys = {"bed_mid": "mid", "bed_high": "high", "wind": "wind"}
        layer_keys.update({name: name for name in EXTRA_LAYERS})
        for name, key in layer_keys.items():
            block = self._layers[name][:frames]
            self._loops[name].read_into(block)
            block *= self._ramp(key, gains[key], frames, previous)[:, None]
            mix += block
        droplets = self._schedule_droplets(frames, clamp(params.intensity, 0.0, 1.0))
        mix += droplets * self._ramp("droplets", gains["droplets"], frames, previous)[:, None]
        self._mix_thunder(mix, frames, clamp(params.thunder_level, 0.0, 2.0))
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
