"""tests/test_wind_thunder.py: الرياح متعددة الطبقات والرعد بثلاث مسافات (NumPy فقط، بلا Qt ولا جهاز صوت).

القياسات هنا طيفية وزمنية لا سمعية: المركز الطيفي (centroid) وحصص النطاقات وزمن الصعود
وبنية الفرقعة. الحكم النهائي بالأذن، لكن هذه الاختبارات تمنع تراجع الخصائص التي صُمّمت عمدًا.
"""

from __future__ import annotations

import threading

import numpy as np
import pytest

from raindesk.engine import rain_audio
from raindesk.engine.rain_audio import AudioParams, RainSynth
from raindesk.engine.thunder_synth import (
    KIND_FAR,
    KIND_MID,
    KIND_NEAR,
    KINDS,
    kind_for_distance,
    make_thunder_sample,
)
from raindesk.engine.wind_model import Breath, wind_extra_gains

RATE = 44100
BLOCK = 882  # 20 ms


def _band_share(x: np.ndarray, low: float, high: float) -> float:
    mono = x.mean(axis=1) if x.ndim == 2 else x
    freq = np.fft.rfftfreq(mono.size, 1.0 / RATE)
    power = np.abs(np.fft.rfft(mono)) ** 2
    return float(power[(freq >= low) & (freq < high)].sum() / power.sum())


def _centroid(x: np.ndarray) -> float:
    mono = x.mean(axis=1) if x.ndim == 2 else x
    freq = np.fft.rfftfreq(mono.size, 1.0 / RATE)
    power = np.abs(np.fft.rfft(mono)) ** 2
    return float((freq * power).sum() / power.sum())


def _render(synth: RainSynth, params: AudioParams, seconds: float) -> np.ndarray:
    blocks = [synth.render(BLOCK, params) for _ in range(round(seconds * RATE / BLOCK))]
    return np.concatenate(blocks)


@pytest.fixture(scope="module")
def prebuilt() -> RainSynth:
    return RainSynth(np.random.default_rng(1), prebuild_thunder=True)


def _wind_only(amount: float, gust: float, seconds: float = 4.0) -> np.ndarray:
    """مساهمة الرياح وحدها = (الرياح مفعّلة) - (معطّلة) بنفس البذرة والمطر صفر."""
    on = _render(
        RainSynth(np.random.default_rng(5)), AudioParams(0.0, amount, gust, 0.3, True), seconds
    )
    off = _render(
        RainSynth(np.random.default_rng(5)), AudioParams(0.0, amount, gust, 0.3, False), seconds
    )
    return (on - off)[RATE // 2 :]


# ----------------------------------------------------------------------------- الرياح
def test_wind_gets_brighter_with_the_gust() -> None:
    calm = _wind_only(0.9, -1.0)
    gale = _wind_only(0.9, 1.0)
    assert _centroid(gale) > 2.0 * _centroid(calm)  # قياس: 124 Hz مقابل 417 Hz
    assert _band_share(gale, 1500, 9000) > 0.02  # حفيف الهواء يظهر في الذروة
    assert _band_share(calm, 1500, 9000) < 0.002  # ولا يظهر في السكون


def test_wind_is_louder_when_stronger() -> None:
    quiet = _wind_only(0.3, 0.0)
    strong = _wind_only(0.9, 0.0)
    assert np.sqrt((strong**2).mean()) > 2.0 * np.sqrt((quiet**2).mean())


def test_howl_needs_strong_wind_and_a_gust() -> None:
    assert all(v == 0.0 for k, v in wind_extra_gains(0.2, 1.0, 0.0).items() if "howl" in k)
    assert all(v == 0.0 for k, v in wind_extra_gains(0.9, -1.0, 0.0).items() if "howl" in k)
    strong = wind_extra_gains(0.9, 1.0, 0.0)
    assert strong["wind_howl_hi"] > 0.0 and strong["wind_howl_lo"] == pytest.approx(0.0)
    mild = wind_extra_gains(0.9, -0.4, 0.0)  # g = 0.3: النغمة المنخفضة تغلب
    assert mild["wind_howl_lo"] > mild["wind_howl_hi"] > 0.0


def test_extra_layers_are_silent_when_wind_is_disabled_or_zero() -> None:
    zero = _render(RainSynth(np.random.default_rng(2)), AudioParams(0.3, 0.0, 1.0, 1.0, True), 1.0)
    off = _render(RainSynth(np.random.default_rng(2)), AudioParams(0.3, 1.0, 1.0, 1.0, False), 1.0)
    base = _render(RainSynth(np.random.default_rng(2)), AudioParams(0.3, 0.0, 1.0, 1.0, False), 1.0)
    assert np.array_equal(zero, base) and np.array_equal(off, base)


def test_breath_is_bounded_moving_and_deterministic() -> None:
    values = [Breath(np.random.default_rng(3)).step(0.02) for _ in range(2)]
    assert values[0] == values[1]
    breath = Breath(np.random.default_rng(4))
    series = np.array([breath.step(0.02) for _ in range(3000)])  # دقيقة
    assert series.min() >= -1.0 and series.max() <= 1.0
    assert series.std() > 0.15  # تتحرك فعلًا ولا تثبت


def test_wind_loops_are_periodic_and_have_unequal_lengths(prebuilt: RainSynth) -> None:
    lengths = {
        name: prebuilt.loop(name).shape[0]
        for name in ("wind", "wind_mid", "wind_hiss", "wind_howl_lo", "wind_howl_hi")
    }
    assert len(set(lengths.values())) == 5  # لا تكرار متزامن بينها
    for name in lengths:
        data = prebuilt.loop(name)
        step = np.abs(np.diff(data[:, 0])).max()
        assert abs(data[0, 0] - data[-1, 0]) <= step  # لا قفزة عند الالتفاف


def test_no_clicks_at_block_boundaries() -> None:
    out = _render(RainSynth(np.random.default_rng(6)), AudioParams(0.5, 0.8, 0.4, 0.6, True), 2.0)
    diffs = np.abs(np.diff(out[:, 0]))
    boundary = diffs[BLOCK - 1 :: BLOCK]
    assert boundary.max() < 4.0 * diffs.std() + diffs.mean()


# ----------------------------------------------------------------------------- الرعد
def test_kind_boundaries() -> None:
    assert kind_for_distance(0.0) == KIND_NEAR and kind_for_distance(0.299) == KIND_NEAR
    assert kind_for_distance(0.30) == KIND_MID and kind_for_distance(0.649) == KIND_MID
    assert kind_for_distance(0.65) == KIND_FAR and kind_for_distance(1.0) == KIND_FAR


@pytest.fixture(scope="module")
def samples() -> dict[str, rain_audio.ThunderSample]:
    rng = np.random.default_rng(3)
    return {kind: make_thunder_sample(rng, RATE, kind) for kind in KINDS}


def test_far_thunder_is_low_and_has_no_crack(samples: dict[str, rain_audio.ThunderSample]) -> None:
    far = samples[KIND_FAR]
    assert far.crack.shape[0] == 0
    assert _band_share(far.rumble, 0, 400) > 0.98
    assert _band_share(samples[KIND_NEAR].rumble, 400, 3000) > 0.05  # القريب أعرض طيفًا
    assert (
        _centroid(samples[KIND_NEAR].rumble)
        > _centroid(samples[KIND_MID].rumble)
        > _centroid(far.rumble)
    )


def test_distance_ordering_of_duration_and_onset(
    samples: dict[str, rain_audio.ThunderSample],
) -> None:
    lengths = [samples[k].rumble.shape[0] for k in (KIND_NEAR, KIND_MID, KIND_FAR)]
    assert lengths == sorted(lengths) and len(set(lengths)) == 3

    def t50(kind: str) -> float:
        env = np.convolve(np.abs(samples[kind].rumble.mean(axis=1)), np.ones(441) / 441, "same")
        return float(np.argmax(env >= 0.5 * env.max())) / RATE

    assert t50(KIND_NEAR) < 0.1  # ضربة فورية
    assert t50(KIND_FAR) > 10 * max(t50(KIND_NEAR), 0.01)  # البعيد يتصاعد ببطء


def test_near_crack_is_a_multi_burst_crackle(samples: dict[str, rain_audio.ThunderSample]) -> None:
    crack = samples[KIND_NEAR].crack
    assert _centroid(crack) > 2000.0 and float(np.abs(crack).max()) == pytest.approx(1.0)
    power = (crack.mean(axis=1)) ** 2
    late = power[round(0.10 * RATE) :].sum() / power.sum()  # انفجار واحد بثابت 40 ms يعطي < 0.003
    assert late > 0.02


def test_samples_fade_to_silence_and_are_normalised(
    samples: dict[str, rain_audio.ThunderSample],
) -> None:
    for sample in samples.values():
        assert float(np.abs(sample.rumble).max()) == pytest.approx(1.0)
        assert float(np.abs(sample.rumble[-BLOCK:]).max()) < 0.01  # لا نقرة في النهاية
        assert np.isfinite(sample.rumble).all()


def test_flash_brightness_picks_the_kind() -> None:
    synth = RainSynth(np.random.default_rng(7), prebuild_thunder=True)
    for _ in range(60):
        synth.trigger_thunder(0.30)  # أسطع وميض: d <= 0.3 دائمًا
        assert synth._voices[-1].sample.kind == KIND_NEAR
    for _ in range(60):
        synth.trigger_thunder(0.12)  # أخفت وميض: d >= 0.7 دائمًا
        assert synth._voices[-1].sample.kind == KIND_FAR
    assert synth.thunder_voice_count <= 4


def test_prebuilt_thunder_does_not_build_on_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    synth = RainSynth(np.random.default_rng(8), prebuild_thunder=True)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("thunder samples must not be built at flash time")

    monkeypatch.setattr(rain_audio, "make_thunder_sample", boom)
    synth.trigger_thunder(0.2)
    assert synth.thunder_voice_count == 1


def test_lazy_build_still_works_without_prebuild() -> None:
    synth = RainSynth(np.random.default_rng(9))
    assert not synth._thunder_bank
    synth.trigger_thunder(0.2)
    assert set(synth._thunder_bank) == set(KINDS)


def test_near_thunder_pushes_the_wind_then_decays() -> None:
    synth = RainSynth(np.random.default_rng(10), prebuild_thunder=True)
    params = AudioParams(0.4, 0.6, 0.0, 0.5, True)
    synth.trigger_thunder(0.30)
    peak = 0.0
    for _ in range(round(3.0 * RATE / BLOCK)):  # التأخير الأقصى للقريب نحو 2.1 s
        synth.render(BLOCK, params)
        peak = max(peak, synth._kick)
    assert peak > 0.05  # وصل الرعد فتصاعدت العصفة
    _render(synth, params, 12.0)
    assert synth._kick < 0.005  # ثم تلاشت


def test_storm_output_stays_below_the_soft_clip_limit() -> None:
    synth = RainSynth(np.random.default_rng(11), prebuild_thunder=True)
    params = AudioParams(1.0, 1.0, 1.0, 1.0, True)
    for _ in range(4):
        synth.trigger_thunder(0.30)
    out = _render(synth, params, 8.0)
    assert float(np.abs(out).max()) <= 0.98 and np.isfinite(out).all()


def test_background_thread_build_is_safe_and_deterministic() -> None:
    result: dict[str, RainSynth] = {}

    def build() -> None:
        result["synth"] = RainSynth(np.random.default_rng(12), prebuild_thunder=True)

    worker = threading.Thread(target=build)
    worker.start()
    worker.join(timeout=60)
    reference = RainSynth(np.random.default_rng(12), prebuild_thunder=True)
    params = AudioParams(0.5, 0.5, 0.0, 0.5, True)
    assert np.array_equal(result["synth"].render(BLOCK, params), reference.render(BLOCK, params))


def test_thunder_delay_range_is_unchanged() -> None:
    assert RainSynth.thunder_delay_s(0.0) == pytest.approx(0.4)
    assert RainSynth.thunder_delay_s(1.0) == pytest.approx(6.0)


@pytest.mark.parametrize("seed", range(8))
def test_onset_sharpness_near_versus_far(seed: int) -> None:
    """بعد 30 إلى 70 ms من البداية: القريب قوي أصلًا، والبعيد لم يبدأ بعد (قياس 0.42+ و0.10-)."""

    def onset(kind: str) -> float:
        sample = make_thunder_sample(np.random.default_rng(seed), RATE, kind)
        env = np.convolve(np.abs(sample.rumble.mean(axis=1)), np.ones(441) / 441, "same")
        return float(
            env[round(0.03 * RATE) : round(0.07 * RATE)].mean() / env[: round(1.5 * RATE)].max()
        )

    assert onset(KIND_NEAR) > 0.3
    assert onset(KIND_FAR) < 0.2


# ----------------------------------------------------------------------------- منزلقا المستوى
def _rms(x: np.ndarray) -> float:
    return float(np.sqrt((x**2).mean()))


def test_wind_level_scales_wind_and_zero_silences_it() -> None:
    def wind(level: float) -> np.ndarray:
        on = _render(
            RainSynth(np.random.default_rng(5)),
            AudioParams(0.0, 0.8, 0.5, 0.3, True, wind_level=level),
            3.0,
        )
        off = _render(
            RainSynth(np.random.default_rng(5)), AudioParams(0.0, 0.8, 0.5, 0.3, False), 3.0
        )
        return (on - off)[RATE // 2 :]

    assert _rms(wind(0.0)) < 1e-6
    assert 1.7 < _rms(wind(2.0)) / _rms(wind(1.0)) < 2.3
    assert _rms(wind(0.5)) < _rms(wind(1.0))


def _thunder_run(level: float, seconds: float = 5.0) -> np.ndarray:
    """رعد قريب وحيد بمستوى ثابت؛ بذرة واحدة فتتطابق تيارات العشوائية بين الاستدعاءات."""
    synth = RainSynth(np.random.default_rng(13), prebuild_thunder=True)
    synth.trigger_thunder(0.30)
    return _render(synth, AudioParams(0.0, 0.0, 0.0, 0.7, False, thunder_level=level), seconds)


def test_thunder_level_scales_thunder() -> None:
    silent = _thunder_run(0.0)
    one = _rms(_thunder_run(1.0) - silent)
    two = _rms(_thunder_run(2.0) - silent)
    assert one > 0.01  # الرعد مسموع فعلًا فوق الخلفية
    assert 1.5 < two / one < 2.5  # قص tanh الناعم يضغط قليلًا


def test_thunder_level_change_applies_to_inflight_voices() -> None:
    """بعد كتم المنزلق أثناء الرعد تصير الكتل مطابقة لتشغيل مكتوم من البداية."""
    audible = AudioParams(0.0, 0.0, 0.0, 0.7, False, thunder_level=1.0)
    muted = AudioParams(0.0, 0.0, 0.0, 0.7, False, thunder_level=0.0)
    a = RainSynth(np.random.default_rng(13), prebuild_thunder=True)
    b = RainSynth(np.random.default_rng(13), prebuild_thunder=True)
    a.trigger_thunder(0.30)
    b.trigger_thunder(0.30)
    _render(a, audible, 1.0)
    _render(b, muted, 1.0)
    assert np.array_equal(_render(a, muted, 3.0), _render(b, muted, 3.0))


def test_default_levels_do_not_change_the_output() -> None:
    a = _render(RainSynth(np.random.default_rng(14)), AudioParams(0.5, 0.6, 0.2, 0.5, True), 1.0)
    b = _render(
        RainSynth(np.random.default_rng(14)), AudioParams(0.5, 0.6, 0.2, 0.5, True, 1.0, 1.0), 1.0
    )
    assert np.array_equal(a, b)
