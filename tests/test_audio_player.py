"""tests/test_audio_player.py: مشغّل الصوت مع QtMultimedia مزيَّفة (بلا جهاز صوت حقيقي).

يغطي: البناء غير المتزامن للمولّد (الواجهة لا تتجمد)، والإغلاق أو التعطيل أثناء البناء، وفشل
البناء، وكشف توقف الجهاز بخطأ بالاستطلاع (بدل إشارة stateChanged التي كانت تسقط بـ TypeError).
"""

from __future__ import annotations

import logging
import threading
import time
import types
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from raindesk.ui.audio import audio_player
from raindesk.ui.audio.audio_player import RainAudioPlayer


class _FakeSignal:
    def connect(self, _slot: object) -> None:
        pass


class _FakeIO:
    def __init__(self) -> None:
        self.written = 0

    def write(self, data: bytes) -> None:
        self.written += len(data)


class _FakeSink:
    def __init__(self, device: object, fmt: object, parent: object = None) -> None:
        self.io = _FakeIO()
        self._state = _FakeQAudio.State.ActiveState
        self._error = _FakeQAudio.Error.NoError

    def setBufferSize(self, size: int) -> None:  # noqa: N802
        self.buffer_size = size

    def start(self) -> _FakeIO:
        return self.io

    def state(self) -> object:
        return self._state

    def error(self) -> object:
        return self._error

    def bytesFree(self) -> int:  # noqa: N802
        return 1 << 20

    def stop(self) -> None:
        pass

    def deleteLater(self) -> None:  # noqa: N802
        pass


class _FakeQAudio:
    class State:
        StoppedState = "stopped"
        ActiveState = "active"
        IdleState = "idle"

    class Error:
        NoError = 0
        IOError = 1


class _FakeFormat:
    class SampleFormat:
        Int16 = 2

    def __init__(self) -> None:
        self._rate = 0

    def setSampleRate(self, rate: int) -> None:  # noqa: N802
        self._rate = rate

    def sampleRate(self) -> int:  # noqa: N802
        return self._rate

    def setChannelCount(self, _count: int) -> None:  # noqa: N802
        pass

    def setSampleFormat(self, _fmt: object) -> None:  # noqa: N802
        pass


class _FakeDevice:
    def isNull(self) -> bool:  # noqa: N802
        return False

    def isFormatSupported(self, _fmt: object) -> bool:  # noqa: N802
        return True


class _FakeDevices:
    audioOutputsChanged = _FakeSignal()  # noqa: N815

    def __init__(self, _parent: object = None) -> None:
        pass

    @staticmethod
    def defaultAudioOutput() -> _FakeDevice:  # noqa: N802
        return _FakeDevice()


_FAKE_MM = types.SimpleNamespace(
    QMediaDevices=_FakeDevices, QAudioFormat=_FakeFormat, QAudioSink=_FakeSink, QAudio=_FakeQAudio
)


class _GatedSynth:
    """بديل RainSynth: يبني عند فتح البوابة (لضبط التوقيت بلا انتظار حقيقي)."""

    gate = threading.Event()
    fail = False

    def __init__(
        self, _rng: object, sample_rate: int = 44100, prebuild_thunder: bool = False
    ) -> None:
        assert prebuild_thunder  # المشغّل يجب أن يبني الرعد في الخيط الخلفي
        assert _GatedSynth.gate.wait(10.0)
        if _GatedSynth.fail:
            raise RuntimeError("boom")
        self.sample_rate = sample_rate
        self.thunder: list[float] = []

    def render_int16(self, frames: int, _params: object) -> bytes:
        return bytes(frames * 4)

    def reset(self) -> None:
        pass

    def trigger_thunder(self, peak: float) -> None:
        self.thunder.append(peak)


class _FakePower:
    """بديل platform_win.power: يسجّل الطلبات فقط."""

    calls: list[str] = []

    @staticmethod
    def begin_responsive_timing() -> object:
        _FakePower.calls.append("begin")
        return "token"

    @staticmethod
    def end_responsive_timing(boost: object) -> None:
        _FakePower.calls.append(f"end:{boost}")

    TimingBoost = object


@pytest.fixture
def player(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(
        audio_player, "importlib", types.SimpleNamespace(import_module=lambda _n: _FAKE_MM)
    )
    monkeypatch.setattr(audio_player, "RainSynth", _GatedSynth)
    monkeypatch.setattr(audio_player, "power", _FakePower)
    _FakePower.calls = []
    _GatedSynth.gate = threading.Event()
    _GatedSynth.fail = False
    instance = RainAudioPlayer()
    yield instance
    _GatedSynth.gate.set()
    instance.shutdown()


def _spin(app: QApplication, condition: Any, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def test_enable_returns_immediately_and_opens_after_the_build(
    qapp: QApplication, player: RainAudioPlayer
) -> None:
    started = time.perf_counter()
    player.set_enabled(True)
    assert time.perf_counter() - started < 0.2  # لا انتظار للبناء
    assert player._sink is None and player._synth is None  # ما زال يُبنى
    _GatedSynth.gate.set()
    assert _spin(qapp, lambda: player._sink is not None)
    assert player.is_available and player._timer.isActive()
    assert _spin(qapp, lambda: player._sink.io.written > 0)  # بدأ الدفع
    player.trigger_thunder(0.2)
    assert player._synth is not None and player._synth.thunder == [0.2]


def test_shutdown_while_building_is_clean(qapp: QApplication, player: RainAudioPlayer) -> None:
    player.set_enabled(True)
    _GatedSynth.gate.set()
    player.shutdown()  # يجمع الخيط قبل الرجوع
    qapp.processEvents()
    assert player._sink is None and not player._timer.isActive()


def test_disabled_during_the_build_keeps_the_device_closed(
    qapp: QApplication, player: RainAudioPlayer
) -> None:
    player.set_enabled(True)
    player.set_enabled(False)
    _GatedSynth.gate.set()
    assert _spin(qapp, lambda: player._synth is not None)
    qapp.processEvents()
    assert player._sink is None  # لم يُفتح الجهاز بلا حاجة، والمولّد محفوظ لإعادة التفعيل
    player.set_enabled(True)
    assert player._sink is not None  # الآن فتح فورًا (المولّد جاهز)


def test_build_failure_marks_audio_unavailable(qapp: QApplication, player: RainAudioPlayer) -> None:
    seen: list[bool] = []
    player.availability_changed.connect(seen.append)
    _GatedSynth.fail = True
    player.set_enabled(True)
    _GatedSynth.gate.set()
    assert _spin(qapp, lambda: not player.is_available)
    assert seen == [False] and player._sink is None


def test_sink_stopped_with_error_is_detected_by_polling(
    qapp: QApplication, player: RainAudioPlayer
) -> None:
    _GatedSynth.gate.set()
    player.set_enabled(True)
    assert _spin(qapp, lambda: player._sink is not None)
    player._sink._state = _FakeQAudio.State.StoppedState
    player._sink._error = _FakeQAudio.Error.IOError
    assert _spin(qapp, lambda: not player.is_available)
    assert player._sink is None


def test_idle_stopped_without_error_is_not_a_failure(
    qapp: QApplication, player: RainAudioPlayer
) -> None:
    _GatedSynth.gate.set()
    player.set_enabled(True)
    assert _spin(qapp, lambda: player._sink is not None)
    player._sink._state = _FakeQAudio.State.StoppedState  # بلا خطأ
    _spin(qapp, lambda: False, 0.2)
    assert player.is_available and player._sink is not None


def test_no_state_changed_connection_remains() -> None:
    source = audio_player.__file__
    text = open(source, encoding="utf-8").read()
    assert "stateChanged.connect" not in text  # سبب TypeError القديم


def test_sink_buffer_is_250_ms(qapp: QApplication, player: RainAudioPlayer) -> None:
    _GatedSynth.gate.set()
    player.set_enabled(True)
    assert _spin(qapp, lambda: player._sink is not None)
    assert player._sink.buffer_size == 44100 * 4 * 250 // 1000  # معدل 44.1 kHz، 4 بايت للإطار


def test_responsive_timing_is_requested_while_the_device_is_open(
    qapp: QApplication, player: RainAudioPlayer
) -> None:
    _GatedSynth.gate.set()
    player.set_enabled(True)
    assert _spin(qapp, lambda: player._sink is not None)
    assert _FakePower.calls == ["begin"]
    player.set_enabled(False)
    player.shutdown()
    assert _FakePower.calls == ["begin", "end:token"]  # يُلغى الطلب عند إغلاق الجهاز


def test_underruns_are_counted_after_the_grace_period_and_reported(
    qapp: QApplication, player: RainAudioPlayer, caplog: pytest.LogCaptureFixture
) -> None:
    _GatedSynth.gate.set()
    player.set_enabled(True)
    assert _spin(qapp, lambda: player._sink is not None)
    player._sink._state = _FakeQAudio.State.IdleState
    _spin(qapp, lambda: False, 0.1)
    assert player._underruns == 0  # ضمن فترة السماح بعد الفتح: لا نعدّ
    player._opened_at -= 5.0
    player._last_report -= 20.0
    with caplog.at_level(logging.WARNING, logger=audio_player.__name__):
        assert _spin(qapp, lambda: any("audio underruns" in r.message for r in caplog.records))
    assert player._underruns > 0
    assert "max timer gap" in caplog.records[-1].message


def test_no_underrun_is_counted_while_the_sink_is_active(
    qapp: QApplication, player: RainAudioPlayer
) -> None:
    _GatedSynth.gate.set()
    player.set_enabled(True)
    assert _spin(qapp, lambda: player._sink is not None)
    player._opened_at -= 5.0
    _spin(qapp, lambda: False, 0.2)
    assert player._underruns == 0
