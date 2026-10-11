"""raindesk/engine/thunder_synth.py

الغرض: بناء عيّنات الرعد الجاهزة بثلاث مسافات (قريب ومتوسط وبعيد) تختلف في الطيف والغلاف.
المسؤوليات: وصف كل نوع (ThunderKind)، واختيار النوع من المسافة، وبناء العيّنة: دمدمة بغلاف
    نبضات وتموّج، و"ضربة" (boom) منخفضة قصيرة، وفرقعة متعددة الانفجارات (crackle).
الاعتماديات: NumPy وraindesk.engine.audio_noise.
النمط التصميمي: Table-driven (جدول أنواع) + دالة بناء نقية.
ملاحظات فيزيائية (وراء قيم الجدول):
    * الهواء يمتص الترددات العالية أكثر مع المسافة: القريب يحوي فرقعة عريضة النطاق
      (1.2 إلى 10 kHz) ودمدمة حتى 900 Hz، والبعيد دمدمة فقط تحت 280 Hz بلا فرقعة. (نبقي
      الحد العلوي للبعيد فوق 150 Hz عمدًا كي تُسمع على سماعات الحاسوب التي لا تعيد ما تحت
      قرابة 150 Hz.)
    * قناة البرق متعرجة ومتفرعة فتصل أجزاؤها بأزمنة مختلفة: لذلك تتكون الفرقعة القريبة من
      ثلاثة انفجارات متتالية خلال نحو 0.3 s بدل انفجار واحد (إحساس التمزّق crackle).
    * بداية القريب حادة (ثابت صعود 30 ms) وبداية البعيد بطيئة (250 ms): ضربة مفاجئة مقابل
      دويّ يتصاعد من بعيد.
    * ضربة boom: ضجيج 35 إلى 220 Hz بصعود 6 ms وتلاشٍ أسّي، تعطي "الدفعة" في بداية الرعد
      القريب والمتوسط.
مثال: sample = make_thunder_sample(np.random.default_rng(1), 44100, "near")
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np

from raindesk.engine.audio_noise import make_loop

KIND_NEAR: Final[str] = "near"
KIND_MID: Final[str] = "mid"
KIND_FAR: Final[str] = "far"
KINDS: Final[tuple[str, ...]] = (KIND_NEAR, KIND_MID, KIND_FAR)
NEAR_MAX_DISTANCE: Final[float] = 0.30  # المسافة المطبَّعة [0, 1]: أقل من هذا = قريب
MID_MAX_DISTANCE: Final[float] = 0.65  # وأقل من هذا = متوسط، وما فوقه بعيد

_TWO_PI: Final[float] = 2.0 * math.pi
_ROLL_1: Final[tuple[float, float, float]] = (0.35, 0.5, 1.2)  # عمق، تردد أدنى، أعلى (Hz)
_ROLL_2: Final[tuple[float, float, float]] = (0.20, 1.5, 3.0)
_TAIL_FADE_S: Final[float] = 0.5  # تلاشٍ خطي في آخر الدمدمة فلا نقرة نهاية
_PULSE_SPREAD: Final[float] = 0.55  # أبعد نبضة تبدأ قبل 55% من طول الدمدمة
_PULSE_AMP_RANGE: Final[tuple[float, float]] = (0.25, 0.8)  # النبضة الأولى سعتها 1
_BOOM_BAND: Final[tuple[float, float, float]] = (35.0, 220.0, -0.5)
_BOOM_ATTACK_S: Final[float] = 0.006
_BOOM_SECONDS: Final[float] = 1.5
_CRACK_SECONDS: Final[float] = 0.6
_CRACK_ATTACK_S: Final[float] = 0.002
_CRACK_OFFSET_RANGE_S: Final[tuple[float, float]] = (0.03, 0.28)
_CRACK_AMP_RANGE: Final[tuple[float, float]] = (0.3, 0.7)


@dataclass(frozen=True, slots=True)
class ThunderKind:
    """وصف نوع رعد: الطول، ونطاق الدمدمة، والنبضات، والضربة، والفرقعة."""

    seconds: float
    rumble: tuple[float, float, float]  # (الحد الأدنى Hz، الأعلى Hz، أس التردد)
    pulses: tuple[int, int]  # عدد النبضات [الأدنى، الأعلى) (integers)
    pulse_attack_s: float
    pulse_tau_range: tuple[float, float]
    boom_level: float  # 0 = بلا ضربة
    boom_tau_s: float
    crack_band: tuple[float, float, float] | None  # None = بلا فرقعة
    crack_bursts: int
    crack_tau_s: float


KIND_TABLE: Final[dict[str, ThunderKind]] = {
    KIND_NEAR: ThunderKind(
        seconds=4.5,
        rumble=(28.0, 900.0, -0.7),
        pulses=(3, 6),
        pulse_attack_s=0.03,
        pulse_tau_range=(0.5, 1.3),
        boom_level=0.9,
        boom_tau_s=0.35,
        crack_band=(1200.0, 10000.0, 0.0),
        crack_bursts=3,
        crack_tau_s=0.04,
    ),
    KIND_MID: ThunderKind(
        seconds=5.5,
        rumble=(28.0, 520.0, -0.8),
        pulses=(4, 7),
        pulse_attack_s=0.08,
        pulse_tau_range=(0.7, 1.6),
        boom_level=0.5,
        boom_tau_s=0.5,
        crack_band=(800.0, 5000.0, -0.3),
        crack_bursts=2,
        crack_tau_s=0.06,
    ),
    KIND_FAR: ThunderKind(
        seconds=7.0,
        rumble=(24.0, 280.0, -0.7),
        pulses=(4, 8),
        pulse_attack_s=0.25,
        pulse_tau_range=(1.0, 2.2),
        boom_level=0.0,
        boom_tau_s=0.0,
        crack_band=None,
        crack_bursts=0,
        crack_tau_s=0.0,
    ),
}


@dataclass(slots=True)
class ThunderSample:
    """عيّنة رعد جاهزة: دمدمة ستيريو (n, 2) وفرقعة (m, 2) (m = 0 للبعيد)، ذروة كل منهما 1."""

    kind: str
    rumble: np.ndarray
    crack: np.ndarray


def kind_for_distance(distance: float) -> str:
    """نوع الرعد لمسافة مطبَّعة في [0, 1] (0 = فوق رأسك)."""
    if distance < NEAR_MAX_DISTANCE:
        return KIND_NEAR
    if distance < MID_MAX_DISTANCE:
        return KIND_MID
    return KIND_FAR


def _pulse_envelope(rng: np.random.Generator, time: np.ndarray, spec: ThunderKind) -> np.ndarray:
    """غلاف الدمدمة: مجموع نبضات a_k (1 - exp(-(t - t_k)/attack)) exp(-(t - t_k)/tau_k).

    النبضة الأولى عند الصفر (الضربة نفسها)، والبقية تتوزع على أول 55% من الدمدمة
    (انعكاسات الصوت على التضاريس والسحب)، ثم يُضرب في تموّج بطيء يعطي إحساس التدحرج.
    """
    envelope = np.zeros(time.size)
    count = int(rng.integers(spec.pulses[0], spec.pulses[1]))
    starts = np.concatenate(
        ([0.0], np.sort(rng.uniform(0.2, _PULSE_SPREAD * spec.seconds, count - 1)))
    )
    for index, start in enumerate(starts):
        amplitude = 1.0 if index == 0 else rng.uniform(*_PULSE_AMP_RANGE)
        tau = rng.uniform(*spec.pulse_tau_range)
        elapsed = time - start
        active = elapsed > 0.0
        envelope[active] += (
            amplitude
            * (1.0 - np.exp(-elapsed[active] / spec.pulse_attack_s))
            * np.exp(-elapsed[active] / tau)
        )
    roll = np.ones(time.size)
    for depth, low, high in (_ROLL_1, _ROLL_2):
        frequency, phase = rng.uniform(low, high), rng.uniform(0.0, _TWO_PI)
        roll += depth * np.sin(_TWO_PI * frequency * time + phase)
    envelope *= np.maximum(roll, 0.0)
    envelope /= max(float(envelope.max()), 1e-12)
    return envelope * np.clip((spec.seconds - time) / _TAIL_FADE_S, 0.0, 1.0)


def _make_boom(rng: np.random.Generator, rate: int, total: int, spec: ThunderKind) -> np.ndarray:
    """ضربة منخفضة قصيرة (n, 2) بطول الدمدمة (أصفار بعد 1.5 s)."""
    boom = np.zeros((total, 2), np.float32)
    count = min(round(_BOOM_SECONDS * rate), total)
    time = np.arange(count) / rate
    envelope = np.minimum(time / _BOOM_ATTACK_S, 1.0) * np.exp(-time / spec.boom_tau_s)
    boom[:count] = make_loop(rng, count, rate, *_BOOM_BAND) * envelope[:, None].astype(np.float32)
    return boom / max(float(np.abs(boom).max()), 1e-12)


def _make_crack(rng: np.random.Generator, rate: int, spec: ThunderKind) -> np.ndarray:
    """فرقعة متعددة الانفجارات (m, 2): انفجار عند 0 وبقية خلال أول 0.3 s بسعات 0.3 إلى 0.7."""
    if spec.crack_band is None:
        return np.zeros((0, 2), np.float32)
    count = round(_CRACK_SECONDS * rate)
    time = np.arange(count) / rate
    offsets = [0.0, *np.sort(rng.uniform(*_CRACK_OFFSET_RANGE_S, spec.crack_bursts - 1))]
    envelope = np.zeros(count)
    for index, offset in enumerate(offsets):
        amplitude = 1.0 if index == 0 else rng.uniform(*_CRACK_AMP_RANGE)
        elapsed = time - offset
        active = elapsed > 0.0
        envelope[active] += (
            amplitude
            * np.minimum(elapsed[active] / _CRACK_ATTACK_S, 1.0)
            * np.exp(-elapsed[active] / spec.crack_tau_s)
        )
    crack = make_loop(rng, count, rate, *spec.crack_band) * envelope[:, None].astype(np.float32)
    return crack / max(float(np.abs(crack).max()), 1e-12)


def make_thunder_sample(rng: np.random.Generator, sample_rate: int, kind: str) -> ThunderSample:
    """يبني عيّنة رعد من النوع المطلوب (KIND_NEAR أو KIND_MID أو KIND_FAR)."""
    spec = KIND_TABLE[kind]
    total = round(spec.seconds * sample_rate)
    time = np.arange(total) / sample_rate
    envelope = _pulse_envelope(rng, time, spec).astype(np.float32)
    rumble = make_loop(rng, total, sample_rate, *spec.rumble) * envelope[:, None]
    rumble /= max(float(np.abs(rumble).max()), 1e-12)
    if spec.boom_level > 0.0:
        rumble += spec.boom_level * _make_boom(rng, sample_rate, total, spec)
        rumble /= max(float(np.abs(rumble).max()), 1e-12)
    return ThunderSample(kind, rumble.astype(np.float32), _make_crack(rng, sample_rate, spec))
