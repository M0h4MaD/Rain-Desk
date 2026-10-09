"""tests/test_rain_audio.py: اختبارات RainSynth (NumPy فقط، بلا Qt ولا جهاز صوت)."""

from __future__ import annotations

import numpy as np

from raindesk.engine.rain_audio import AudioParams, RainSynth

_RATE = 44100
_BLOCK = 882  # 20 ms
_SEED = 3
_LOOP_NAMES = ("bed_mid", "bed_high", "wind")
_SEAMLESS_SIGMAS = 4.0
_MIN_BAND_POWER_FRACTION = 0.90
_MID_LOW_HZ, _MID_HIGH_HZ = 300.0, 9000.0
_POISSON_SIGMAS = 3.0
_MAX_OUTPUT = 0.99
_SILENCE = 1e-6


def _synth(seed: int = _SEED) -> RainSynth:
    return RainSynth(np.random.default_rng(seed), sample_rate=_RATE)


def _params(
    intensity: float = 0.5, wind: float = 0.5, gust: float = 0.0,
    master: float = 1.0, wind_enabled: bool = True,
) -> AudioParams:
    return AudioParams(intensity, wind, gust, master, wind_enabled)


def _render_blocks(synth: RainSynth, blocks: int, params: AudioParams) -> np.ndarray:
    return np.concatenate([synth.render(_BLOCK, params) for _ in range(blocks)])


def test_each_noise_loop_is_seamless() -> None:
    synth = _synth()
    for name in _LOOP_NAMES:
        loop = synth.loop(name)
        for channel in range(2):
            samples = loop[:, channel]
            step_std = float(np.std(np.diff(samples)))
            assert abs(float(samples[0] - samples[-1])) <= _SEAMLESS_SIGMAS * step_std, name


def test_loops_have_the_documented_rms_and_decorrelated_channels() -> None:
    synth = _synth()
    for name in _LOOP_NAMES:
        loop = synth.loop(name)
        for channel in range(2):
            assert abs(float(np.sqrt(np.mean(loop[:, channel] ** 2))) - 0.2) < 1e-3
        assert abs(float(np.corrcoef(loop[:, 0], loop[:, 1])[0, 1])) < 0.1  # عرض ستيريو


def test_bed_mid_power_lies_in_the_documented_band() -> None:
    loop = _synth().loop("bed_mid")
    spectrum = np.abs(np.fft.rfft(loop[:, 0])) ** 2
    freq = np.fft.rfftfreq(loop.shape[0], 1.0 / _RATE)
    in_band = spectrum[(freq >= _MID_LOW_HZ) & (freq <= _MID_HIGH_HZ)].sum()
    assert in_band / spectrum.sum() >= _MIN_BAND_POWER_FRACTION


def test_render_shape_dtype_finiteness_and_bounds_at_maximum_settings() -> None:
    synth = _synth()
    block = synth.render(_RATE, _params(1.0, 1.0, 1.0, 1.0))
    assert block.shape == (_RATE, 2) and block.dtype == np.float32
    assert np.isfinite(block).all()
    assert float(np.abs(block).max()) <= _MAX_OUTPUT
    assert synth.render(0, _params()).shape == (0, 2)


def test_same_seed_and_parameters_give_identical_output() -> None:
    results = [_render_blocks(_synth(11), 60, _params(0.7, 0.6, 0.4)) for _ in range(2)]
    np.testing.assert_array_equal(results[0], results[1])
    assert not np.array_equal(results[0], _render_blocks(_synth(12), 60, _params(0.7, 0.6, 0.4)))


def test_rms_grows_monotonically_with_intensity() -> None:
    levels = []
    for intensity in (0.1, 0.5, 0.9):
        block = _render_blocks(_synth(), 100, _params(intensity))
        levels.append(float(np.sqrt(np.mean(block**2))))
    assert levels[0] < levels[1] < levels[2]


def test_master_zero_gives_silence() -> None:
    block = _render_blocks(_synth(), 50, _params(1.0, 1.0, 1.0, master=0.0))
    assert float(np.abs(block).max()) < _SILENCE


def test_wind_layer_follows_the_enable_flag() -> None:
    with_wind = _render_blocks(_synth(), 100, _params(0.0, 1.0, 1.0, wind_enabled=True))
    without = _render_blocks(_synth(), 100, _params(0.0, 1.0, 1.0, wind_enabled=False))
    assert float(np.sqrt(np.mean(with_wind**2))) > float(np.sqrt(np.mean(without**2)))


def test_droplet_events_follow_the_poisson_mean() -> None:
    intensity = 0.5
    seeds = range(1, 11)  # نجمع عشر تشغيلات كي لا يعتمد الاختبار على بذرة واحدة محظوظة أو سيئة
    blocks_per_run = 500  # 500 كتلة * 20 ms = 10 ثوانٍ لكل تشغيل
    total = 0
    for seed in seeds:
        synth = _synth(seed)
        params = _params(intensity)
        for _ in range(blocks_per_run):
            synth.render(_BLOCK, params)
            total += synth.events_last_render
    mean = 220.0 * intensity**1.2 * (blocks_per_run * _BLOCK / _RATE) * len(seeds)
    assert abs(total - mean) <= _POISSON_SIGMAS * mean**0.5


def test_no_discontinuity_at_block_boundaries() -> None:
    """القفزة عند حدود الكتل لا تتجاوز أكبر قفزة بين عينتين داخل الكتل.

    ملاحظة منهجية: المعيار الحرفي "3 أضعاف الفرق النموذجي" هش إحصائيًا هنا لأن فروق العينات
    ثقيلة الذيل (بدايات نقرات القطرات حادة بطبيعتها)، فتتجاوز 3 انحرافات معيارية في مواضع
    عادية داخل الكتل نفسها. لذلك نقارن حدود الكتل بأكبر فرق داخلي: انقطاع حقيقي (قفزة DC أو
    التفاف حلقة خاطئ أو ذيل مفقود) يتجاوزه بوضوح، أما التوليد السليم فلا.
    """
    synth = _synth()
    blocks = 100  # ثانيتان بكتل 20 ms
    signal = _render_blocks(synth, blocks, _params(0.8, 0.7, 0.2))
    steps = np.abs(np.diff(signal, axis=0))  # steps[k] = |x[k+1] - x[k]|
    boundary_steps = np.arange(1, blocks) * _BLOCK - 1  # الفرق عبر كل حد بين كتلتين
    inner_mask = np.ones(steps.shape[0], dtype=bool)
    inner_mask[boundary_steps] = False
    assert float(steps[boundary_steps].max()) <= float(steps[inner_mask].max())


def test_block_size_does_not_change_the_noise_beds() -> None:
    """الحلقات تُقرأ بلا قفزة مهما كان حجم الكتلة: كتل صغيرة تعطي نفس عينات استدعاء واحد.

    مع intensity = 0 لا نقرات (المعدل صفر) والكسب ثابت، فالمخرج يعتمد على قراءة الحلقات
    وحدها؛ أي خطأ في حفظ الموضع بين الكتل أو في الالتفاف عند نهاية الحلقة يظهر كفرق.
    """
    params = _params(0.0, 0.8, 0.5)
    frames = 9 * _RATE  # أطول من الحلقة (8 ثوانٍ) كي نعبر نقطة الالتفاف
    single = _synth(9).render(frames, params)
    pieces = []
    chunker = _synth(9)
    for size in (_BLOCK, 1, 4410, 17, 882, 100_000):  # أحجام متفاوتة تشمل 1
        pieces.append(chunker.render(size, params))
    remaining = frames - sum(piece.shape[0] for piece in pieces)
    pieces.append(chunker.render(remaining, params))
    np.testing.assert_allclose(np.concatenate(pieces), single, atol=1e-7)


def test_int16_output_is_interleaved_little_endian_and_matches_float() -> None:
    first, second = _synth(5), _synth(5)
    params = _params(0.6)
    data = first.render_int16(_BLOCK, params)
    reference = second.render(_BLOCK, params)
    assert len(data) == _BLOCK * 2 * 2  # إطارات * قناتان * 2 بايت
    decoded = np.frombuffer(data, dtype="<i2").reshape(-1, 2).astype(np.float64) / 32767.0
    assert float(np.abs(decoded - reference).max()) <= 1.0 / 32767.0 + 1e-6


def test_reset_clears_tail_and_ramps() -> None:
    synth = _synth()
    _render_blocks(synth, 20, _params(1.0))
    synth.reset()
    block = synth.render(_BLOCK, _params(0.0, 0.0, 0.0, master=0.0))
    assert float(np.abs(block).max()) < _SILENCE

    # --------------------------------------------------------------------------- الرعد
_THUNDER_MIN_DELAY_S = 0.4
_THUNDER_MAX_DELAY_S = 6.0
_THUNDER_LENGTH_S = 5.0
_BRIGHT_FLASH = 0.30
_DIM_FLASH = 0.12


def _thunder_only(seed: int, peaks: list[float], seconds: float = 12.0) -> np.ndarray:
    """مخرج الرعد وحده: الفرق بين مولّدين متطابقين أُطلق على أحدهما رعد (بلا مطر ولا رياح)."""
    params = _params(0.0, 0.0, 0.0, wind_enabled=False)
    plain, thunder = _synth(seed), _synth(seed)
    for peak in peaks:
        thunder.trigger_thunder(peak)
    frames = round(seconds * _RATE)
    return thunder.render(frames, params) - plain.render(frames, params)


def test_thunder_is_silent_before_the_earliest_delay_then_audible_then_ends() -> None:
    diff = _thunder_only(4, [_BRIGHT_FLASH])
    earliest = round(_THUNDER_MIN_DELAY_S * _RATE)
    latest_end = round((_THUNDER_MAX_DELAY_S + _THUNDER_LENGTH_S + 0.1) * _RATE)
    assert float(np.abs(diff[: earliest - 1]).max()) == 0.0  # لا صوت قبل أقصر تأخير ممكن
    assert float(np.abs(diff).max()) > 0.02  # ثم رعد مسموع
    assert float(np.abs(diff[latest_end:]).max()) == 0.0  # وينتهي كله قبل 11.1 ثانية


def test_closer_flash_gives_louder_thunder() -> None:
    close = _thunder_only(6, [_BRIGHT_FLASH])
    far = _thunder_only(6, [_DIM_FLASH])
    assert float(np.sqrt(np.mean(close**2))) > 1.5 * float(np.sqrt(np.mean(far**2)))


def test_thunder_delay_follows_the_documented_range() -> None:
    assert RainSynth.thunder_delay_s(0.0) == _THUNDER_MIN_DELAY_S
    assert RainSynth.thunder_delay_s(1.0) == _THUNDER_MAX_DELAY_S
    assert RainSynth.thunder_delay_s(-5.0) == _THUNDER_MIN_DELAY_S  # خارج المجال يُقصّ
    assert RainSynth.thunder_delay_s(9.0) == _THUNDER_MAX_DELAY_S


def test_simultaneous_thunders_are_capped_at_four() -> None:
    synth = _synth()
    for _ in range(10):
        synth.trigger_thunder(0.2)
    assert synth.thunder_voice_count == 4


def test_thunder_is_deterministic_for_the_same_seed() -> None:
    first = _thunder_only(8, [0.25, 0.15])
    second = _thunder_only(8, [0.25, 0.15])
    np.testing.assert_array_equal(first, second)


def test_output_stays_bounded_with_four_thunders_over_heavy_rain() -> None:
    synth = _synth()
    for _ in range(4):
        synth.trigger_thunder(_BRIGHT_FLASH)
    block = synth.render(12 * _RATE, _params(1.0, 1.0, 1.0, 1.0))
    assert float(np.abs(block).max()) <= _MAX_OUTPUT


def test_thunder_does_not_depend_on_the_block_size() -> None:
    params = _params(0.0, 0.0, 0.0, wind_enabled=False)
    frames = 12 * _RATE
    single = _synth(9)
    single.trigger_thunder(0.2)
    reference = single.render(frames, params)
    chunked = _synth(9)
    chunked.trigger_thunder(0.2)
    pieces = [chunked.render(size, params) for size in (_BLOCK, 1, 4410, 17, 100_000)]
    pieces.append(chunked.render(frames - sum(piece.shape[0] for piece in pieces), params))
    np.testing.assert_allclose(np.concatenate(pieces), reference, atol=1e-7)


def test_reset_drops_pending_thunder() -> None:
    synth = _synth()
    synth.trigger_thunder(0.2)
    synth.reset()
    assert synth.thunder_voice_count == 0