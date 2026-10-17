"""raindesk/ui/audio/audio_player.py

الغرض: يدفع صوت RainSynth إلى جهاز الإخراج الافتراضي عبر QAudioSink في وضع push.
المسؤوليات: تحميل QtMultimedia كسولًا عند أول استعمال، وفتح الجهاز عند الحاجة وإغلاقه بعد
    2 s من الصمت، ومؤقّت 20 ms يملأ المخزن بكتل جاهزة، وغلاف ظهور واختفاء 250 ms (fade)، وتتبّع
    توفّر الصوت (جهاز غائب، خطأ، تغيير جهاز) وإبلاغه، دون أن يرفع أي استثناء إلى الواجهة.
    حالة الجهاز تُفحص دوريًا داخل المؤقّت (لا نربط إشارة stateChanged: انظر الملاحظات).
    بناء المولّد (حلقات الضجيج وبنك القطرات وعيّنات الرعد) يجري على خيط خلفي فلا تتجمد الواجهة.
الاعتماديات: PySide6 (QtCore، وQtMultimedia كسولًا) وraindesk.engine.rain_audio وraindesk.core.
النمط التصميمي: Producer مبني على المؤقّت (push mode) مع State Machine صغيرة لحالة الجهاز.
ملاحظات: الصوت معطّل افتراضيًا ولا يُحمَّل QtMultimedia إلا عند تفعيله فعلًا. توفّر الصوت
    "مجهول" قبل أول محاولة ويُعامَل كمتاح. الكتلة تولَّد على خيط الواجهة (نحو 0.5 ms لكل كتلة)،
    أما البناء الأولي (ثانية أو أكثر) فيجري على خيط خلفي: عمل NumPy الثقيل (irfft وexp) يفرج
    عن GIL فلا يتأخر الرسم أكثر من بضعة ms (قياس: أقصى فجوة 4 ms)؛ والخيط daemon فلا يمنع
    إغلاق التطبيق. الجهاز لا يُفتح إلا بعد اكتمال البناء (يُستطلَع كل 50 ms).
    لا نربط sink.stateChanged لأن PySide6 يفشل أحيانًا في تحويل معامل QAudio::State إلى slot
    بايثون (TypeError: Cannot call meta function ... QAudio::State) فيسقط الصوت؛ فحص
    state() وerror() كل نبضة (20 ms) أبسط وأمتن ولا كلفة تُذكر.
    التقطّع على Windows 11: مؤقّت الواجهة قد يتأخر (حجب النافذة الشفافة وpower throttling وانشغال
    الرسم)، فنكبّر مخزن الجهاز إلى 250 ms ونملأه بسرعة بعد كل تأخر ونطلب مؤقّتات دقيقة
    (platform_win/power.py) ونسجّل عدد الانقطاعات والفجوات لتشخيص ما يبقى.
    مستوى الصوت يُطبَّق مربّعًا: master = volume^2 * fade (إدراك الجهارة لوغاريتمي تقريبًا).
مثال: player.set_volume(0.35); player.set_enabled(True); player.update_params(0.6, 0.4, 0.1, True)
"""

from __future__ import annotations

import importlib
import logging
import threading
import time
from typing import Any, Final

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal

from raindesk.core.constants import (
    AUDIO_BLOCK_MS,
    AUDIO_FADE_MS,
    AUDIO_IDLE_RELEASE_S,
    AUDIO_SAMPLE_RATE,
)
from raindesk.engine.math_utils import clamp
from raindesk.engine.rain_audio import AudioParams, RainSynth
from raindesk.platform_win import power

_LOG = logging.getLogger(__name__)

_CHANNELS: Final[int] = 2
_BYTES_PER_FRAME: Final[int] = 4  # int16 * قناتان
_MS_PER_SECOND: Final[float] = 1000.0
_MAX_BLOCKS_PER_TICK: Final[int] = 8  # أقصى كتل نملأ بها المخزن في نبضة واحدة (تعويض تأخر المؤقّت)
_SINK_BUFFER_MS: Final[int] = 250  # ms: مخزن الجهاز؛ أكبر من الأصل (100) ليتحمّل تأخر مؤقّت الواجهة
_UNDERRUN_GRACE_S: Final[float] = 1.0  # ثانية بعد الفتح لا نعدّ فيها الفراغ (الملء الأولي)
_UNDERRUN_LOG_INTERVAL_S: Final[float] = 10.0  # ثانية بين رسائل تحذير الفراغ
_DEVICE_CHANGE_DEBOUNCE_MS: Final[int] = 500  # ms: دمج إشعارات تغيّر أجهزة الإخراج
_FADE_STEP_PER_BLOCK: Final[float] = AUDIO_BLOCK_MS / AUDIO_FADE_MS  # تقدّم الغلاف لكل كتلة
_DEFAULT_VOLUME: Final[float] = 0.35
_DEFAULT_LEVEL: Final[float] = 0.5  # منزلق الرياح/الرعد: 0.5 = المستوى الأصلي
_LEVEL_SCALE: Final[float] = 2.0  # منزلق [0, 1] -> مضاعف [0, 2]
_BUILD_POLL_MS: Final[int] = 50  # ms: استطلاع اكتمال بناء المولّد
_BUILD_JOIN_S: Final[float] = 3.0  # ثانية: أقصى انتظار لخيط البناء عند الإغلاق


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
        self._wind_volume = _DEFAULT_LEVEL
        self._thunder_volume = _DEFAULT_LEVEL
        self._intensity = 0.0
        self._wind_amount = 0.0
        self._gust = 0.0
        self._wind_enabled = True
        self._fade = 0.0  # غلاف الظهور والاختفاء الحالي في [0, 1]
        self._target = 0.0  # هدف الغلاف: 1 عند التشغيل الفعلي وإلا 0
        self._silent_since: float | None = None
        self._synth: RainSynth | None = None
        self._build_thread: threading.Thread | None = None
        self._build_result: RainSynth | None = None  # يكتبه الخيط الخلفي مرة واحدة فقط
        self._build_error: BaseException | None = None
        self._build_started = 0.0
        self._build_closing = False  # True بعد shutdown: نتجاهل ناتج البناء
        self._sink: Any = None
        self._io: Any = None
        self._timing_boost: power.TimingBoost | None = None
        self._opened_at = 0.0
        self._last_tick = 0.0
        self._max_gap_ms = 0.0  # أطول فجوة بين نبضتين منذ آخر تقرير
        self._underruns = 0  # مرات وجد فيها الجهاز مخزنه فارغًا (انقطاع مسموع)
        self._underruns_reported = 0
        self._last_report = 0.0
        self._block_frames = round(AUDIO_SAMPLE_RATE * AUDIO_BLOCK_MS / _MS_PER_SECOND)
        self._block_bytes = self._block_frames * _BYTES_PER_FRAME
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(AUDIO_BLOCK_MS)
        self._timer.timeout.connect(self._on_timer)
        self._build_timer = QTimer(self)
        self._build_timer.setInterval(_BUILD_POLL_MS)
        self._build_timer.timeout.connect(self._poll_build)
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

    def set_wind_volume(self, level: float) -> None:
        """مستوى الرياح في [0, 1] (0.5 = الأصلي، 1 = ضعف، 0 = صامت)."""
        self._wind_volume = clamp(level, 0.0, 1.0)

    def set_thunder_volume(self, level: float) -> None:
        """مستوى الرعد في [0, 1] (0.5 = الأصلي، 1 = ضعف، 0 = صامت)."""
        self._thunder_volume = clamp(level, 0.0, 1.0)

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

    def trigger_thunder(self, flash_peak: float) -> None:
        """يجدول رعدًا بعد وميض برق بشدة flash_peak؛ لا شيء إن لم يكن الصوت قيد التشغيل الفعلي.

        أول رعد يبني صيغ الرعد (نحو 0.1 s مرة واحدة)، وبعده لا كلفة تُذكر.
        """
        if self._synth is None or self._sink is None or self._target <= 0.0:
            return
        self._synth.trigger_thunder(flash_peak)

    def shutdown(self) -> None:
        """يوقف المؤقّتات ويحرّر الجهاز فورًا (عند إغلاق التطبيق)."""
        self._build_closing = True
        self._timer.stop()
        self._device_timer.stop()
        self._build_timer.stop()
        self._release_device()
        thread = self._build_thread
        if thread is not None and thread.is_alive():
            thread.join(_BUILD_JOIN_S)  # daemon: إن لم ينته لا يمنع الخروج

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
            self._start_build(rate)  # غير متزامن: يعود _poll_build إلى هنا بعد الاكتمال
            return True
        self._block_frames = round(rate * AUDIO_BLOCK_MS / _MS_PER_SECOND)
        self._block_bytes = self._block_frames * _BYTES_PER_FRAME
        sink = mm.QAudioSink(device, audio_format, self)
        sink.setBufferSize(round(rate * _BYTES_PER_FRAME * _SINK_BUFFER_MS / _MS_PER_SECOND))
        stream = sink.start()  # وضع push: يعيد QIODevice نكتب فيه الكتل
        if stream is None:
            sink.deleteLater()
            self._fail("could not start the audio sink")
            return False
        self._sink, self._io = sink, stream
        self._fade = 0.0  # كل تشغيل جديد يبدأ بظهور تدريجي (لا نقرة)
        self._silent_since = None
        self._timing_boost = power.begin_responsive_timing()
        self._opened_at = time.monotonic()
        self._last_tick = 0.0
        self._max_gap_ms = 0.0
        self._underruns = self._underruns_reported = 0
        self._last_report = self._opened_at
        self._timer.start()
        self._set_availability(True)
        return True

    # ------------------------------------------------------------------ بناء المولّد (خيط خلفي)
    def _start_build(self, rate: int) -> None:
        """يبدأ بناء RainSynth على خيط daemon إن لم يكن هناك بناء جارٍ."""
        thread = self._build_thread
        if thread is not None and thread.is_alive():
            return
        self._build_result, self._build_error = None, None
        self._build_started = time.perf_counter()
        self._build_thread = threading.Thread(
            target=self._build_worker, args=(rate,), name="raindesk-audio-build", daemon=True
        )
        self._build_thread.start()
        self._build_timer.start()

    def _build_worker(self, rate: int) -> None:
        """جسم الخيط الخلفي: لا يلمس أي كائن Qt؛ يكتب النتيجة أو الخطأ ثم ينتهي."""
        try:
            self._build_result = RainSynth(
                np.random.default_rng(), sample_rate=rate, prebuild_thunder=True
            )
        except BaseException as exc:  # noqa: BLE001  يُنقَل الخطأ إلى خيط الواجهة ليُسجَّل
            self._build_error = exc

    def _poll_build(self) -> None:
        """على خيط الواجهة: ينتظر انتهاء البناء ثم يكمل فتح الجهاز إن كان الصوت ما زال مطلوبًا."""
        thread = self._build_thread
        if thread is not None and thread.is_alive():
            return
        self._build_timer.stop()
        self._build_thread = None
        if self._build_closing:
            return
        if self._build_error is not None:
            self._fail(f"could not build the rain synth: {self._build_error!r}")
            return
        self._synth, self._build_result = self._build_result, None
        _LOG.info(
            "rain synth built in %.0f ms (background thread)",
            (time.perf_counter() - self._build_started) * 1000.0,
        )
        if self._enabled and self._active and self._sink is None:
            self._open_device()

    def _release_device(self) -> None:
        """يوقف المؤقّت ويغلق الجهاز ويصفّر ذيل المولّد؛ آمن عند عدم وجود جهاز."""
        self._timer.stop()
        power.end_responsive_timing(self._timing_boost)
        self._timing_boost = None
        sink, self._sink, self._io = self._sink, None, None
        if sink is not None:
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
        if self._sink_failed(sink):
            return
        self._watch_underruns(sink)
        for _ in range(_MAX_BLOCKS_PER_TICK):
            if sink.bytesFree() < self._block_bytes:
                break  # المخزن ممتلئ بما يكفي: ننتظر النبضة التالية
            delta = clamp(self._target - self._fade, -_FADE_STEP_PER_BLOCK, _FADE_STEP_PER_BLOCK)
            self._fade += delta
            master = self._volume * self._volume * self._fade
            params = AudioParams(
                self._intensity,
                self._wind_amount,
                self._gust,
                master,
                self._wind_enabled,
                thunder_level=self._thunder_volume * _LEVEL_SCALE,
                wind_level=self._wind_volume * _LEVEL_SCALE,
            )
            stream.write(synth.render_int16(self._block_frames, params))
        self._maybe_release_when_silent()

    def _watch_underruns(self, sink: Any) -> None:
        """يقيس فجوات المؤقّت ويعدّ انقطاعات الصوت (المخزن فارغ) ويسجّلها كل 10 s عند وجودها.

        في وضع push تعني IdleState أن الجهاز استهلك كل ما كتبناه، أي أن النبضة تأخرت أكثر من
        حجم المخزن؛ هذا هو سبب التقطّع المسموع، وتساعد الأرقام على معرفة من يؤخّر الواجهة.
        """
        now = time.monotonic()
        if self._last_tick:
            self._max_gap_ms = max(self._max_gap_ms, (now - self._last_tick) * _MS_PER_SECOND)
        self._last_tick = now
        mm = self._mm
        idle = getattr(mm.QAudio.State, "IdleState", None) if mm is not None else None
        if idle is not None and now - self._opened_at > _UNDERRUN_GRACE_S and sink.state() == idle:
            self._underruns += 1
        if now - self._last_report >= _UNDERRUN_LOG_INTERVAL_S:
            if self._underruns > self._underruns_reported:
                _LOG.warning(
                    "audio underruns: %d in the last %.0f s (max timer gap %.0f ms, buffer %d ms)",
                    self._underruns - self._underruns_reported,
                    now - self._last_report,
                    self._max_gap_ms,
                    _SINK_BUFFER_MS,
                )
            self._underruns_reported = self._underruns
            self._max_gap_ms = 0.0
            self._last_report = now

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
    def _sink_failed(self, sink: Any) -> bool:
        """يفحص الجهاز: إن توقف بخطأ نعلن عدم التوفر ونعيد True (يُستدعى كل نبضة)."""
        mm = self._mm
        if mm is None:
            return False
        if sink.state() == mm.QAudio.State.StoppedState and sink.error() != mm.QAudio.Error.NoError:
            self._fail(f"audio sink stopped with error {sink.error()}")
            return True
        return False

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
