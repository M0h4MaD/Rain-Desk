"""raindesk/ui/audio/audio_player.py

الغرض: يدفع صوت RainSynth إلى جهاز الإخراج الافتراضي عبر QAudioSink في وضع push.
المسؤوليات: تحميل QtMultimedia كسولًا عند أول استعمال، وفتح الجهاز عند الحاجة وإغلاقه بعد
    2 s من الصمت، ومؤقّت 20 ms يملأ المخزن بكتل جاهزة، وغلاف ظهور واختفاء 250 ms (fade)، وتتبّع
    توفّر الصوت (جهاز غائب، خطأ، تغيير جهاز) وإبلاغه، دون أن يرفع أي استثناء إلى الواجهة.
الاعتماديات: PySide6 (QtCore، وQtMultimedia كسولًا) وraindesk.engine.rain_audio وraindesk.core.
النمط التصميمي: Producer مبني على المؤقّت (push mode) مع State Machine صغيرة لحالة الجهاز.
ملاحظات: الصوت معطّل افتراضيًا ولا يُحمَّل QtMultimedia إلا عند تفعيله فعلًا. توفّر الصوت
    "مجهول" قبل أول محاولة ويُعامَل كمتاح. الكتلة تولَّد على خيط الواجهة (نحو 0.1 ms لكل كتلة).
    مستوى الصوت يُطبَّق مربّعًا: master = volume^2 * fade (إدراك الجهارة لوغاريتمي تقريبًا).
مثال: player.set_volume(0.35); player.set_enabled(True); player.update_params(0.6, 0.4, 0.1, True)
"""

from __future__ import annotations

import importlib
import logging
import time
from typing import Any, Final

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal

from raindesk.core.constants import (
    AUDIO_BLOCK_MS,
    AUDIO_BUFFER_MS,
    AUDIO_FADE_MS,
    AUDIO_IDLE_RELEASE_S,
    AUDIO_SAMPLE_RATE,
)
from raindesk.engine.math_utils import clamp
from raindesk.engine.rain_audio import AudioParams, RainSynth

_LOG = logging.getLogger(__name__)

_CHANNELS: Final[int] = 2
_BYTES_PER_FRAME: Final[int] = 4  # int16 * قناتان
_MS_PER_SECOND: Final[float] = 1000.0
_MAX_BLOCKS_PER_TICK: Final[int] = 3  # أقصى كتل نملأ بها المخزن في نبضة واحدة (تعويض تأخر قصير)
_DEVICE_CHANGE_DEBOUNCE_MS: Final[int] = 500  # ms: دمج إشعارات تغيّر أجهزة الإخراج
_FADE_STEP_PER_BLOCK: Final[float] = AUDIO_BLOCK_MS / AUDIO_FADE_MS  # تقدّم الغلاف لكل كتلة
_DEFAULT_VOLUME: Final[float] = 0.35


class RainAudioPlayer(QObject):
    """مشغّل صوت المطر. كل الدوال العامة آمنة الاستدعاء من خيط الواجهة ولا ترفع استثناءات."""

    availability_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mm: Any = None  # وحدة QtMultimedia بعد التحميل الكسول
        self._mm_failed = False
        self._devices: Any = None  # QMediaDevices (يُنشأ مع التحميل)
        self._availability: bool | None = None  # None = لم تُجرَّب بعد (يُعامل كمتاح)
        self._enabled = False
        self._active = True
        self._volume = _DEFAULT_VOLUME
        self._intensity = 0.0
        self._wind_amount = 0.0
        self._gust = 0.0
        self._wind_enabled = True
        self._fade = 0.0  # غلاف الظهور والاختفاء الحالي في [0, 1]
        self._target = 0.0  # هدف الغلاف: 1 عند التشغيل الفعلي وإلا 0
        self._silent_since: float | None = None
        self._synth: RainSynth | None = None
        self._sink: Any = None
        self._io: Any = None
        self._block_frames = round(AUDIO_SAMPLE_RATE * AUDIO_BLOCK_MS / _MS_PER_SECOND)
        self._block_bytes = self._block_frames * _BYTES_PER_FRAME
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(AUDIO_BLOCK_MS)
        self._timer.timeout.connect(self._on_timer)
        self._device_timer = QTimer(self)
        self._device_timer.setSingleShot(True)
        self._device_timer.setInterval(_DEVICE_CHANGE_DEBOUNCE_MS)
        self._device_timer.timeout.connect(self._on_devices_changed)

    # ------------------------------------------------------------------ الواجهة العامة
    @property
    def is_available(self) -> bool:
        """False فقط بعد محاولة فاشلة (لا جهاز، لا QtMultimedia، خطأ)؛ المجهول يُعد متاحًا."""
        return self._availability is not False

    def set_enabled(self, enabled: bool) -> None:
        """تفعيل الصوت أو إيقافه (الإيقاف يخفت 250 ms ثم يُحرَّر الجهاز بعد 2 s من الصمت)."""
        self._enabled = enabled
        self._sync()

    def set_volume(self, volume: float) -> None:
        """مستوى الصوت في [0, 1] (يُطبَّق مربّعًا)."""
        self._volume = clamp(volume, 0.0, 1.0)

    def set_active(self, active: bool) -> None:
        """False أثناء إيقاف المطر مؤقتًا (ملء الشاشة، قفل...) فيخفت الصوت أيضًا."""
        self._active = active
        self._sync()

    def update_params(
        self, intensity: float, wind_amount: float, gust: float, wind_enabled: bool
    ) -> None:
        """معاملات الصوت الحية (تُستدعى كل إطار محاكاة)؛ تُقرأ عند توليد الكتلة التالية."""
        self._intensity = intensity
        self._wind_amount = wind_amount
        self._gust = gust
        self._wind_enabled = wind_enabled

    def shutdown(self) -> None:
        """يوقف المؤقّتات ويحرّر الجهاز فورًا (عند إغلاق التطبيق)."""
        self._timer.stop()
        self._device_timer.stop()
        self._release_device()

    # ------------------------------------------------------------------ تحميل QtMultimedia
    def _load_multimedia(self) -> bool:
        """يحمّل QtMultimedia عند أول حاجة؛ False إذا لم تتوفر (يُسجَّل مرة واحدة)."""
        if self._mm is not None:
            return True
        if self._mm_failed:
            return False
        try:
            self._mm = importlib.import_module("PySide6.QtMultimedia")
        except ImportError as exc:
            _LOG.warning("QtMultimedia is not available: %s", exc)
            self._mm_failed = True
            return False
        self._devices = self._mm.QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(self._on_outputs_changed)
        return True

    # ------------------------------------------------------------------ حالة التوفر
    def _set_availability(self, available: bool) -> None:
        previous = self.is_available
        self._availability = available
        if available != previous:
            self.availability_changed.emit(available)

    def _fail(self, reason: str) -> None:
        """يسجّل السبب ويحرّر الجهاز ويعلن أن الصوت غير متاح (دون رفع استثناء)."""
        _LOG.warning("audio unavailable: %s", reason)
        self._release_device()
        self._set_availability(False)

    # ------------------------------------------------------------------ فتح الجهاز وإغلاقه
    def _sync(self) -> None:
        """يوفّق الجهاز والغلاف مع (مفعّل ونشط): يفتح الجهاز عند الحاجة ويضبط هدف الغلاف."""
        wanted = self._enabled and self._active
        self._target = 1.0 if wanted else 0.0
        if wanted and self._sink is None and self._availability is not False:
            self._open_device()

    def _open_device(self) -> bool:
        if not self._load_multimedia():
            self._set_availability(False)
            return False
        mm = self._mm
        device = mm.QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self._fail("no default audio output device")
            return False
        audio_format = mm.QAudioFormat()
        audio_format.setSampleRate(AUDIO_SAMPLE_RATE)
        audio_format.setChannelCount(_CHANNELS)
        audio_format.setSampleFormat(mm.QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(audio_format):
            audio_format.setSampleRate(device.preferredFormat().sampleRate())
            if not device.isFormatSupported(audio_format):
                self._fail("the output device does not support 16-bit stereo")
                return False
        rate = int(audio_format.sampleRate())
        if self._synth is None or self._synth.sample_rate != rate:
            started = time.perf_counter()
            self._synth = RainSynth(np.random.default_rng(), sample_rate=rate)
            _LOG.info("rain synth built in %.0f ms", (time.perf_counter() - started) * 1000.0)
        self._block_frames = round(rate * AUDIO_BLOCK_MS / _MS_PER_SECOND)
        self._block_bytes = self._block_frames * _BYTES_PER_FRAME
        sink = mm.QAudioSink(device, audio_format, self)
        sink.setBufferSize(round(rate * _BYTES_PER_FRAME * AUDIO_BUFFER_MS / _MS_PER_SECOND))
        sink.stateChanged.connect(self._on_state_changed)
        stream = sink.start()  # وضع push: يعيد QIODevice نكتب فيه الكتل
        if stream is None:
            sink.deleteLater()
            self._fail("could not start the audio sink")
            return False
        self._sink, self._io = sink, stream
        self._fade = 0.0  # كل تشغيل جديد يبدأ بظهور تدريجي (لا نقرة)
        self._silent_since = None
        self._timer.start()
        self._set_availability(True)
        return True

    def _release_device(self) -> None:
        """يوقف المؤقّت ويغلق الجهاز ويصفّر ذيل المولّد؛ آمن عند عدم وجود جهاز."""
        self._timer.stop()
        sink, self._sink, self._io = self._sink, None, None
        if sink is not None:
            try:
                sink.stateChanged.disconnect(self._on_state_changed)
            except (RuntimeError, TypeError):
                pass
            sink.stop()
            sink.deleteLater()
        if self._synth is not None:
            self._synth.reset()
        self._fade = 0.0
        self._silent_since = None

    # ------------------------------------------------------------------ الدفع
    def _on_timer(self) -> None:
        try:
            self._pump()
        except Exception as exc:  # noqa: BLE001  لا يجوز أن يخرج خطأ صوتي إلى حلقة الواجهة
            self._fail(f"unexpected audio error: {exc!r}")

    def _pump(self) -> None:
        sink, stream, synth = self._sink, self._io, self._synth
        if sink is None or stream is None or synth is None:
            self._timer.stop()
            return
        for _ in range(_MAX_BLOCKS_PER_TICK):
            if sink.bytesFree() < self._block_bytes:
                break  # المخزن ممتلئ بما يكفي: ننتظر النبضة التالية
            delta = clamp(self._target - self._fade, -_FADE_STEP_PER_BLOCK, _FADE_STEP_PER_BLOCK)
            self._fade += delta
            master = self._volume * self._volume * self._fade
            params = AudioParams(
                self._intensity, self._wind_amount, self._gust, master, self._wind_enabled
            )
            stream.write(synth.render_int16(self._block_frames, params))
        self._maybe_release_when_silent()

    def _maybe_release_when_silent(self) -> None:
        """بعد اختفاء كامل لمدة 2 s يُحرَّر الجهاز فلا يبقى مفتوحًا بلا حاجة (توفير طاقة)."""
        if self._target == 0.0 and self._fade <= 0.0:
            now = time.monotonic()
            if self._silent_since is None:
                self._silent_since = now
            elif now - self._silent_since >= AUDIO_IDLE_RELEASE_S:
                self._release_device()
        else:
            self._silent_since = None

    # ------------------------------------------------------------------ أحداث الجهاز
    def _on_state_changed(self, state: Any) -> None:
        mm = self._mm
        if mm is None or self._sink is None:
            return
        if state == mm.QAudio.State.StoppedState and self._sink.error() != mm.QAudio.Error.NoError:
            self._fail(f"audio sink stopped with error {self._sink.error()}")

    def _on_outputs_changed(self) -> None:
        """تغيّرت أجهزة الإخراج (توصيل سماعة مثلًا): ننتظر استقرار الإشعارات ثم نعيد الفتح."""
        self._device_timer.start()

    def _on_devices_changed(self) -> None:
        """يغلق الجهاز الحالي ويعيد المحاولة (قد يصير الصوت متاحًا بعد غيابه أو العكس)."""
        was_open = self._sink is not None
        self._release_device()
        self._availability = None  # نعيد التقييم من الصفر
        if was_open or (self._enabled and self._active):
            self._sync()