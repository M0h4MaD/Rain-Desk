"""tests/test_math_utils.py: اختبارات raindesk.engine.math_utils (دوال نقية بلا Qt)."""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from raindesk.engine.math_utils import (
    clamp,
    ease_in_out_cubic,
    ease_out_quad,
    exp_smooth,
    gust_signal,
    inv_lerp,
    lerp,
    smoothstep,
)

_TOLERANCE = 1e-9  # الحد المطلوب في المواصفة
_GRID = [i / 100.0 for i in range(101)]  # شبكة [0, 1] بخطوة 0.01
_GUST_SAMPLES = 100_000
_GUST_STEP_S = 0.013  # ثانية: خطوة أخذ العينات (تغطي عدة دورات)
_GUST_PHASES = (0.3, 1.1, 2.0)


def test_clamp_endpoints_and_nan() -> None:
    assert clamp(-1.0, 0.0, 1.0) == 0.0
    assert clamp(2.0, 0.0, 1.0) == 1.0
    assert clamp(0.4, 0.0, 1.0) == 0.4
    assert math.isnan(clamp(math.nan, 0.0, 1.0))


def test_lerp_and_inv_lerp_endpoints_and_inversion() -> None:
    assert lerp(2.0, 6.0, 0.0) == 2.0
    assert lerp(2.0, 6.0, 1.0) == 6.0
    assert lerp(2.0, 6.0, 0.25) == 3.0
    for t in (0.0, 0.3, 0.77, 1.0, 1.5):
        assert inv_lerp(2.0, 6.0, lerp(2.0, 6.0, t)) == pytest.approx(t, abs=_TOLERANCE)
    assert inv_lerp(3.0, 3.0, 9.0) == 0.0  # أطراف متساوية: بلا قسمة على صفر


def test_smoothstep_shape() -> None:
    assert smoothstep(0.0, 1.0, -5.0) == 0.0
    assert smoothstep(0.0, 1.0, 5.0) == 1.0
    assert smoothstep(0.0, 1.0, 0.5) == pytest.approx(0.5, abs=_TOLERANCE)
    assert smoothstep(1.0, 1.0, 0.9) == 0.0 and smoothstep(1.0, 1.0, 1.1) == 1.0


@pytest.mark.parametrize("easing", [ease_out_quad, ease_in_out_cubic])
def test_easing_endpoints_and_monotonic(easing: Callable[[float], float]) -> None:
    assert easing(0.0) == 0.0
    assert easing(1.0) == pytest.approx(1.0, abs=_TOLERANCE)
    values = [easing(t) for t in _GRID]
    assert all(b >= a for a, b in zip(values, values[1:], strict=False))


def test_exp_smooth_converges_to_target() -> None:
    value = 0.0
    for _ in range(600):  # 10 ثوانٍ بخطوة 1/60 مع tau = 0.25 (40 ثابت زمن)
        value = exp_smooth(value, 1.0, 1.0 / 60.0, 0.25)
    assert value == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("steps", [2, 3, 7, 60])
def test_exp_smooth_composes_exactly(steps: int) -> None:
    one_step = exp_smooth(0.2, 0.9, 0.1, 0.25)
    value = 0.2
    for _ in range(steps):
        value = exp_smooth(value, 0.9, 0.1 / steps, 0.25)
    assert value == pytest.approx(one_step, abs=_TOLERANCE)


def test_exp_smooth_edge_cases() -> None:
    assert exp_smooth(0.3, 0.9, 0.0, 0.25) == 0.3  # dt = 0: لا حركة
    assert exp_smooth(0.3, 0.9, -1.0, 0.25) == 0.3  # dt سالب: لا حركة
    assert exp_smooth(0.3, 0.9, 0.1, 0.0) == 0.9  # tau = 0: قفز


def test_gust_signal_bounded_and_not_periodic() -> None:
    period = 7.0
    peak = max(
        abs(gust_signal(i * _GUST_STEP_S, period, _GUST_PHASES)) for i in range(_GUST_SAMPLES)
    )
    assert peak <= 1.0
    shifted = [
        abs(
            gust_signal(t + 10 * period, period, _GUST_PHASES)
            - gust_signal(t, period, _GUST_PHASES)
        )
        for t in (0.5, 1.7, 3.1, 4.9)
    ]
    assert max(shifted) > 1e-3  # الدورات غير متناسبة فلا تتكرر الإشارة بعد 10T


def test_gust_signal_guards_invalid_period() -> None:
    assert -1.0 <= gust_signal(1.0, 0.0, _GUST_PHASES) <= 1.0