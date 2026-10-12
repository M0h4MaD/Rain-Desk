from __future__ import annotations

import numpy as np
import pytest

from raindesk.core.constants import AUDIO_SAMPLE_RATE
from raindesk.engine.rain_audio import AudioParams, RainSynth
from raindesk.engine.wind_model import Breath

_RATE = AUDIO_SAMPLE_RATE
_BLOCK = 882


def test_block_size_does_not_change_the_noise_beds(monkeypatch: pytest.MonkeyPatch) -> None:
    """الحلقات تُقرأ بلا قفزة مهما كان حجم الكتلة: كتل صغيرة تعطي نفس عينات استدعاء واحد.

    مع intensity = 0 لا نقرات والكسب ثابت. نثبّت «التنفّس» (Breath) عند صفر لأنه يتقدّم مرة
    واحدة لكل كتلة بتصميمه (فيتغيّر مع حجم الكتلة)، فيبقى المخرج معتمدًا على قراءة الحلقات
    (ومنها حلقات الرياح) وحدها؛ أي خطأ في حفظ الموضع أو في الالتفاف يظهر كفرق.
    """
    monkeypatch.setattr(Breath, "step", lambda self, dt: 0.0)
    params = AudioParams(0.0, 0.8, 0.5, 1.0, True)
    frames = 9 * _RATE  # أطول من الحلقة (8 ثوانٍ) كي نعبر نقطة الالتفاف
    single = RainSynth(np.random.default_rng(9)).render(frames, params)
    chunker = RainSynth(np.random.default_rng(9))
    pieces = [chunker.render(size, params) for size in (_BLOCK, 1, 4410, 17, 882, 100_000)]
    pieces.append(chunker.render(frames - sum(piece.shape[0] for piece in pieces), params))
    np.testing.assert_allclose(np.concatenate(pieces), single, atol=1e-7)


def _thunder_rms(seed: int, flash_peak: float) -> float:
    synth = RainSynth(
        np.random.default_rng(seed), loop_seconds=1.0, droplet_bank_size=16, prebuild_thunder=True
    )
    synth.trigger_thunder(flash_peak)
    out = synth.render(12 * _RATE, AudioParams(0.0, 0.0, 0.0, 1.0, False))
    return float(np.sqrt(np.mean(out**2)))


def test_closer_flash_gives_louder_thunder() -> None:
    """وميض أسطع (أقرب) يعطي رعدًا أعلى في المتوسط عبر عدة بذور.

    المسافة تحوي مكوّنًا عشوائيًا (30%) وعيّنات الرعد متباينة، فلا تصحّ مقارنة بذرة واحدة بعتبة
    ضيقة؛ نقارن متوسط النسبة على 6 بذور (المقيس نحو 1.3، وطفرة بلا أثر للمسافة تعطي 0.85). الحلقات والبنك
    مصغّران للسرعة ولا يؤثران في الرعد.
    """
    ratios = [_thunder_rms(seed, 0.30) / _thunder_rms(seed, 0.12) for seed in range(6)]
    assert float(np.mean(ratios)) > 1.15