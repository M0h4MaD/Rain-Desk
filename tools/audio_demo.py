"""tools/audio_demo.py

الغرض: توليد ملفات WAV تجريبية لصوت المطر بدون تشغيل التطبيق، لسماعها وتقييمها وضبطها.
المسؤوليات: رسم 10 ثوانٍ (قابلة للتغيير) بثلاث شدّات (منخفضة 0.2 ومتوسطة 0.6 وعالية 1.0) بنفس
    كتل 20 ms التي يستعملها المشغّل الحقيقي، وكتابتها بصيغة 16 بت ستيريو، وطباعة RMS والذروة.
المخرجات: rain_demo_low.wav وrain_demo_mid.wav وrain_demo_high.wav في المجلد المحدد.
الاستعمال: python tools/audio_demo.py [--outdir DIR] [--seconds N] [--seed S]
"""

from __future__ import annotations

import argparse
import math
import sys
import wave
from pathlib import Path
from typing import Final

import numpy as np

# python tools/audio_demo.py يضيف مجلد tools فقط إلى المسار، فنضيف جذر المشروع يدويًا.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raindesk.core.constants import AUDIO_BLOCK_MS, AUDIO_SAMPLE_RATE  # noqa: E402
from raindesk.engine.rain_audio import AudioParams, RainSynth  # noqa: E402

_INTENSITIES: Final[tuple[tuple[str, float], ...]] = (("low", 0.2), ("mid", 0.6), ("high", 1.0))
_DEFAULT_SECONDS: Final[float] = 10.0
_DEFAULT_SEED: Final[int] = 12345
_VOLUME: Final[float] = 0.9  # يطابق مستوى صوت مرتفعًا نسبيًا: master = volume^2 = 0.81
_WIND_AMOUNT: Final[float] = 0.5
_GUST_PERIOD_S: Final[float] = 7.0  # دورة عصف مماثلة للافتراضي في الإعدادات
_INT16_FULL_SCALE: Final[float] = 32767.0


def _render(intensity: float, seconds: float, seed: int) -> bytes:
    """يولّد seconds ثانية بكتل 20 ms ويعيد بايتات int16 متشابكة."""
    synth = RainSynth(np.random.default_rng(seed), sample_rate=AUDIO_SAMPLE_RATE)
    block_frames = round(AUDIO_SAMPLE_RATE * AUDIO_BLOCK_MS / 1000.0)
    blocks = round(seconds * 1000.0 / AUDIO_BLOCK_MS)
    chunks: list[bytes] = []
    for index in range(blocks):
        elapsed = index * AUDIO_BLOCK_MS / 1000.0
        gust = math.sin(2.0 * math.pi * elapsed / _GUST_PERIOD_S)
        params = AudioParams(intensity, _WIND_AMOUNT, gust, _VOLUME * _VOLUME, True)
        chunks.append(synth.render_int16(block_frames, params))
    return b"".join(chunks)


def _write_wav(path: Path, data: bytes) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(AUDIO_SAMPLE_RATE)
        handle.writeframes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render demo WAV files of the rain sound.")
    parser.add_argument("--outdir", type=Path, default=Path("."), help="output directory")
    parser.add_argument(
        "--seconds", type=float, default=_DEFAULT_SECONDS, help="length of each file"
    )
    parser.add_argument("--seed", type=int, default=_DEFAULT_SEED, help="random seed")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    args.outdir.mkdir(parents=True, exist_ok=True)
    for label, intensity in _INTENSITIES:
        data = _render(intensity, args.seconds, args.seed)
        path = args.outdir / f"rain_demo_{label}.wav"
        _write_wav(path, data)
        samples = np.frombuffer(data, dtype="<i2").astype(np.float64) / _INT16_FULL_SCALE
        rms_db = 20.0 * math.log10(max(float(np.sqrt(np.mean(samples**2))), 1e-9))
        peak_db = 20.0 * math.log10(max(float(np.abs(samples).max()), 1e-9))
        print(f"{path.resolve()}  intensity={intensity:.1f}  RMS {rms_db:6.1f} dBFS  "
              f"peak {peak_db:6.1f} dBFS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())