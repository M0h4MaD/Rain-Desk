"""tests/test_adaptive_quality.py: اختبارات AdaptiveQuality (بلا Qt)."""

from __future__ import annotations

import pytest

from raindesk.engine.adaptive_quality import AdaptiveQuality

_FPS = 30
_BUDGET_MS = 1000.0 / _FPS
_MIN_SCALE, _MAX_SCALE = 0.5, 1.0
_OVERLOAD_FRAMES = 200
_IDLE_FRAMES = 4000  # يكفي لاستعادة كاملة (كل خطوة استعادة تحتاج 300 إطار)


def _controller() -> AdaptiveQuality:
    controller = AdaptiveQuality()
    controller.configure(True, _FPS)
    return controller


def _feed(controller: AdaptiveQuality, frames: int, interval: float, cost: float) -> None:
    for _ in range(frames):
        controller.record(interval, cost)


def test_scale_stays_inside_documented_range() -> None:
    controller = _controller()
    for _ in range(40):  # تناوب طويل بين إجهاد شديد وراحة تامة
        _feed(controller, 500, 5 * _BUDGET_MS, 3 * _BUDGET_MS)
        assert _MIN_SCALE <= controller.scale <= _MAX_SCALE
        _feed(controller, 500, _BUDGET_MS, 0.05 * _BUDGET_MS)
        assert _MIN_SCALE <= controller.scale <= _MAX_SCALE
    _feed(controller, 20000, 5 * _BUDGET_MS, 3 * _BUDGET_MS)
    assert controller.scale == pytest.approx(_MIN_SCALE)  # يستقر عند الحد الأدنى
    _feed(controller, 50000, _BUDGET_MS, 0.05 * _BUDGET_MS)
    assert controller.scale == pytest.approx(_MAX_SCALE)


def test_sustained_overload_lowers_and_sustained_idle_restores() -> None:
    controller = _controller()
    _feed(controller, _OVERLOAD_FRAMES, 2.0 * _BUDGET_MS, 1.2 * _BUDGET_MS)
    lowered = controller.scale
    assert lowered < _MAX_SCALE
    _feed(controller, _IDLE_FRAMES, _BUDGET_MS, 0.1 * _BUDGET_MS)
    assert controller.scale > lowered
    assert controller.scale == pytest.approx(_MAX_SCALE)


def test_short_overload_below_the_dwell_count_changes_nothing() -> None:
    controller = _controller()
    _feed(controller, 30, 3.0 * _BUDGET_MS, 2.0 * _BUDGET_MS)  # أقل من 60 إطارًا
    _feed(controller, 3000, _BUDGET_MS, 0.5 * _BUDGET_MS)  # ثم حمل عادي
    assert controller.scale == _MAX_SCALE


def test_cost_inside_the_hysteresis_band_never_changes_the_scale() -> None:
    controller = _controller()
    for index in range(30000):  # الكلفة تتناوب بين 0.5 و0.7 من الميزانية
        cost = (0.5 if index % 2 == 0 else 0.7) * _BUDGET_MS
        controller.record(_BUDGET_MS, cost)
        assert controller.scale == _MAX_SCALE
    # ونفس الأمر عند معامل منخفض أصلًا: لا صعود ولا هبوط داخل النطاق.
    lowered = _controller()
    _feed(lowered, 400, 3.0 * _BUDGET_MS, 2.0 * _BUDGET_MS)
    held = lowered.scale
    assert held < _MAX_SCALE
    _feed(lowered, 100, _BUDGET_MS, 0.6 * _BUDGET_MS)  # يعبر EMA إلى النطاق أولًا
    settled = lowered.scale
    for index in range(30000):
        cost = (0.5 if index % 2 == 0 else 0.7) * _BUDGET_MS
        lowered.record(_BUDGET_MS, cost)
        assert lowered.scale == settled


def test_single_huge_interval_spike_is_not_treated_as_overload() -> None:
    controller = _controller()
    _feed(controller, 100, _BUDGET_MS, 0.5 * _BUDGET_MS)
    controller.record(300_000.0, 0.5 * _BUDGET_MS)  # جهاز عاد من السكون
    _feed(controller, 2000, _BUDGET_MS, 0.5 * _BUDGET_MS)
    assert controller.scale == _MAX_SCALE


def test_disabled_controller_keeps_scale_one_but_tracks_emas() -> None:
    controller = AdaptiveQuality()
    controller.configure(False, _FPS)
    _feed(controller, 5000, 5 * _BUDGET_MS, 3 * _BUDGET_MS)
    assert controller.scale == 1.0
    assert controller.interval_ema > 0 and controller.cost_ema > 0  # للوحة التشخيص
    controller.configure(True, _FPS)
    _feed(controller, 1000, 3.0 * _BUDGET_MS, 2.0 * _BUDGET_MS)
    assert controller.scale < 1.0
    controller.configure(False, _FPS)  # التعطيل يعيد 1.0 فورًا
    assert controller.scale == 1.0


def test_reset_and_ema_convergence() -> None:
    controller = _controller()
    _feed(controller, 500, 40.0, 10.0)
    assert controller.interval_ema == pytest.approx(40.0, abs=1e-3)
    assert controller.cost_ema == pytest.approx(10.0, abs=1e-3)
    assert controller.fps == pytest.approx(25.0, abs=1e-2)
    controller.reset()
    assert controller.scale == 1.0 and controller.fps == 0.0 and controller.interval_ema == 0.0