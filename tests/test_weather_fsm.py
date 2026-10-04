"""tests/test_weather_fsm.py: اختبارات آلة الطقس ونموذج البرق (بلا Qt)."""

from __future__ import annotations

import random

import pytest

from raindesk.config.schema import PRESETS
from raindesk.engine.weather_fsm import (
    TRANSITIONS,
    LightningModel,
    WeatherState,
    WeatherStateMachine,
)

_DT = 0.05  # ثانية: يطابق سقف dt في الإنتاج
_TOLERANCE = 1e-9
_DWELL_LOW, _DWELL_HIGH = 0.6, 1.4
_MEAN_CALM_S, _MEAN_WILD_S = 180.0, 40.0
_PEAK_LIMIT = 0.30
_MAX_FLASHES_PER_SECOND = 3  # WCAG 2.1 SC 2.3.1


def _machine(seed: int, variability: float) -> WeatherStateMachine:
    machine = WeatherStateMachine(random.Random(seed))
    machine.set_variability(variability)
    machine.set_enabled(True)
    return machine


def test_transition_rows_sum_to_one_and_exclude_self() -> None:
    assert set(TRANSITIONS) == set(WeatherState)
    for state, row in TRANSITIONS.items():
        assert sum(row.values()) == pytest.approx(1.0, abs=_TOLERANCE)
        assert state not in row


def test_dwell_and_blend_times_stay_inside_documented_bounds() -> None:
    for variability in (0.0, 0.5, 1.0):
        machine = _machine(seed=1, variability=variability)
        mean = _MEAN_CALM_S + (_MEAN_WILD_S - _MEAN_CALM_S) * variability
        blend_expected = 15.0 + (5.0 - 15.0) * variability
        samples = {machine.dwell_s}
        previous_state = machine.state
        for _ in range(int(8 * 3600 / _DT)):  # ثماني ساعات محاكاة
            machine.step(_DT)
            if machine.state != previous_state:
                samples.add(machine.dwell_s)  # بدأ مكوث جديد
                previous_state = machine.state
        assert len(samples) > 3
        for dwell in samples:
            assert _DWELL_LOW * mean - _TOLERANCE <= dwell <= _DWELL_HIGH * mean + _TOLERANCE
        assert machine.blend_s == pytest.approx(blend_expected, abs=_TOLERANCE)


def test_long_run_with_fixed_seed_visits_all_five_states() -> None:
    machine = _machine(seed=12345, variability=1.0)
    visited = {machine.state}
    for _ in range(int(6 * 3600 / _DT)):
        machine.step(_DT)
        visited.add(machine.state)
    assert visited == set(WeatherState)


def test_same_seed_gives_identical_trajectory() -> None:
    first, second = _machine(5, 0.7), _machine(5, 0.7)
    for _ in range(20000):
        first.step(_DT)
        second.step(_DT)
        assert (first.state, first.next_state) == (second.state, second.next_state)
    assert first.blended_values() == second.blended_values()


def test_blended_values_match_presets_at_the_blend_ends() -> None:
    machine = _machine(seed=3, variability=1.0)
    assert machine.blend == 0.0
    assert machine.blended_values() == PRESETS[machine.state.value]  # blend = 0
    while machine.state == machine.next_state:  # ننتظر بدء المزج
        machine.step(_DT)
    start, target = machine.state, machine.next_state
    assert start != target and 0.0 <= machine.blend <= 1.0
    for key, value in machine.blended_values().items():
        low, high = sorted((PRESETS[start.value][key], PRESETS[target.value][key]))
        assert low - _TOLERANCE <= value <= high + _TOLERANCE
    while machine.state == start:  # ننتظر انتهاء المزج
        machine.step(_DT)
    assert machine.state == target  # blend = 1 يعني أن التالية صارت الحالية
    assert machine.blend == 0.0
    assert machine.blended_values() == PRESETS[target.value]


def test_disabled_machine_does_not_move_and_big_dt_is_handled() -> None:
    machine = WeatherStateMachine(random.Random(8))
    snapshot = (machine.state, machine.next_state, machine.blend)
    machine.step(10_000.0)
    assert (machine.state, machine.next_state, machine.blend) == snapshot
    machine.set_enabled(True)
    machine.step(1_000_000.0)  # dt هائل يعبر عدة مراحل دون استثناء
    assert 0.0 <= machine.blend <= 1.0


def test_lightning_is_off_by_default_and_when_disabled() -> None:
    model = LightningModel(random.Random(1))
    for _ in range(int(120 / _DT)):
        model.step(_DT)
        assert model.alpha == 0.0
    model.configure(True, 1.0)
    model.configure(False, 1.0)
    assert model.alpha == 0.0


def _run_lightning(seed: int, frequency: float, seconds: float) -> tuple[float, list[float]]:
    """يشغّل النموذج ويعيد (أقصى alpha، أزمنة بدايات الومضات)."""
    model = LightningModel(random.Random(seed))
    model.configure(True, frequency)
    dt = 0.005  # خطوة دقيقة تلتقط الومضات الثانية
    peak, flash_times = 0.0, []
    previous = 0.0
    time = 0.0
    for _ in range(int(seconds / dt)):
        model.step(dt)
        time += dt
        peak = max(peak, model.alpha)
        if model.alpha > previous + 1e-4:  # ارتفاع مفاجئ = بداية ومضة (أولى أو ثانية)
            flash_times.append(time)
        previous = model.alpha
    return peak, flash_times


@pytest.mark.parametrize("frequency", [0.0, 0.5, 1.0])
def test_lightning_peak_gap_and_flash_rate_are_within_safety_limits(frequency: float) -> None:
    peak, flashes = _run_lightning(seed=11, frequency=frequency, seconds=1800.0)
    assert 0.0 < peak <= _PEAK_LIMIT + _TOLERANCE
    assert len(flashes) > 3
    for start in flashes:  # في أي نافذة طولها ثانية لا تزيد الومضات على ثلاث
        in_window = [t for t in flashes if start <= t < start + 1.0]
        assert len(in_window) <= _MAX_FLASHES_PER_SECOND


def test_lightning_events_respect_minimum_gap() -> None:
    model = LightningModel(random.Random(21))
    model.configure(True, 1.0)  # أعلى تكرار
    starts, last_count = [], 0
    time = 0.0
    dt = 0.01
    for _ in range(int(3600 / dt)):
        model.step(dt)
        time += dt
        if model.event_count != last_count:
            starts.append(time)
            last_count = model.event_count
    assert len(starts) > 50
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    assert min(gaps) >= 5.0 - 2 * dt