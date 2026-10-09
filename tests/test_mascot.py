"""tests/test_mascot.py: سلوك Drip (المحرك فقط، بلا Qt): الحالات والفيزياء والجدولة والتفاعل."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterator

import pytest

from raindesk.core.constants import GRAVITY_PX_S2
from raindesk.engine.mascot import BASE_HEIGHT_PX, Effect, Expression, Mascot, MascotState

_S = MascotState
_STAGE = (0.0, 1920.0, 1040.0)  # يسار ويمين وخط الأرض
_GROUND = _STAGE[2]
_DT = 1.0 / 30.0
_FINE = 1.0 / 60.0
_HOUR_S = 3600.0
_BEHAVIOURS = {
    _S.WALKING,
    _S.IDLE,
    _S.LOOK_UP,
    _S.CROUCHING,
    _S.SHAKING,
    _S.DANCING,
    _S.SLEEPING,
    _S.WAVING,
    _S.SPINNING,
    _S.SHIVERING,
}
_REACTIONS = {_S.PETTED, _S.STARTLED, _S.CURIOUS, _S.CHASING, _S.WAVING}
_CALM = {
    _S.WALKING,
    _S.IDLE,
    _S.LOOK_UP,
    _S.SHAKING,
    _S.DANCING,
    _S.SLEEPING,
    _S.WAVING,
    _S.SPINNING,
}
# الانتقالات الصالحة فقط (غير المذكورة ممنوعة).
_ALLOWED: dict[MascotState, set[MascotState]] = {
    _S.HIDDEN: {_S.ENTERING},
    _S.ENTERING: _BEHAVIOURS | {_S.EXITING},
    _S.CURIOUS: _BEHAVIOURS | _REACTIONS | {_S.EXITING},
    _S.CHASING: _BEHAVIOURS | _REACTIONS | {_S.EXITING},
    _S.PETTED: {_S.CROUCHING, _S.STARTLED},
    _S.CROUCHING: {_S.JUMPING},
    _S.JUMPING: {_S.LANDING},
    _S.STARTLED: {_S.LANDING},
    _S.LANDING: _BEHAVIOURS | {_S.CROUCHING, _S.EXITING},
    _S.SHIVERING: _BEHAVIOURS | {_S.EXITING},
    _S.EXITING: {_S.HIDDEN},
    **{state: _BEHAVIOURS | _REACTIONS | {_S.EXITING} for state in _CALM},
}
Pointer = Callable[[float, Mascot], "tuple[float, float] | None"]


def _make(
    seed: int = 3, frequency: float = 1.0, scale: float = 1.0, enabled: bool = True
) -> Mascot:
    mascot = Mascot(random.Random(seed))
    mascot.configure(enabled, frequency, scale)
    mascot.set_stage(*_STAGE)
    return mascot


def _gestures(t: float, m: Mascot) -> tuple[float, float] | None:
    """سيناريو مؤشر دوري (60 s): غائب، ساكن قريب، مسح سريع، تمسيح، اندفاع، غائب."""
    phase = t % 60.0
    near = _GROUND - 30.0
    if phase < 10.0:
        return None
    if phase < 20.0:
        return min(m.x + 180.0, 1800.0), near
    if phase < 30.0:
        return m.x + 250.0 * math.sin(2.0 * math.pi * 0.5 * phase), near
    if phase < 40.0:
        return m.x + 16.0 * math.sin(2.0 * math.pi * 3.0 * phase), near + 12.0
    if phase < 44.0:
        return m.x + max(10.0, 400.0 - 2500.0 * (phase - 40.0)), near
    return None


def _run(
    mascot: Mascot,
    seconds: float,
    dt: float = _DT,
    wind: float = 0.0,
    pointer: Pointer | None = None,
) -> Iterator[Mascot]:
    """يقدّم الشخصية seconds ثانية (مع مؤشر مبرمج اختياريًا) ويعيدها بعد كل خطوة."""
    clock = 0.0
    for _ in range(round(seconds / dt)):
        clock += dt
        mascot.set_pointer(pointer(clock, mascot) if pointer else None)
        mascot.step(dt, wind)
        yield mascot


def _calm_mascot(seed: int = 5) -> Mascot:
    """شخصية ظاهرة وهادئة في وسط المسرح (لتجارب التفاعل المضبوطة)."""
    mascot = _make(seed=seed)
    for _ in _run(mascot, 1800.0, dt=_FINE):
        if mascot.state in {_S.IDLE, _S.LOOK_UP} and 500.0 < mascot.x < 1400.0:
            # حقل خاص هنا فقط: نمدّد زمن الظهور كي لا تنسحب الشخصية أثناء التجربة المضبوطة.
            mascot._budget = mascot._appeared + 120.0
            return mascot
    raise AssertionError("Drip never became calm in the middle of the stage")


def _states_during(mascot: Mascot, seconds: float, pointer: Pointer) -> list[MascotState]:
    return [m.state for m in _run(mascot, seconds, dt=_FINE, pointer=pointer)]


# --------------------------------------------------------------------- آلة الحالات
def test_long_run_with_interaction_has_only_valid_transitions_and_visits_every_state() -> None:
    mascot = _make()
    previous = mascot.state
    visited = {previous}
    expressions: set[Expression] = set()
    effects: set[Effect] = set()
    clock = 0.0
    for _ in range(round(3 * _HOUR_S / _DT)):
        clock += _DT
        mascot.set_pointer(_gestures(clock, mascot))
        mascot.set_weather(0.5 + 0.5 * math.sin(clock / 300.0))
        if clock % 70.0 < _DT:
            mascot.startle()  # برق دوري
        mascot.step(_DT, 0.0)
        if mascot.state is not previous:
            assert mascot.state in _ALLOWED[previous], (previous, mascot.state)
            previous = mascot.state
            visited.add(previous)
        assert mascot.facing in (-1, 1)
        assert -1.0 <= mascot.look_dir <= 1.0 and -1.0 <= mascot.look_y <= 1.0
        assert 0.0 <= mascot.blink <= 1.0 and 0.0 <= mascot.mouth_open <= 1.0
        assert math.isfinite(mascot.x) and math.isfinite(mascot.y)
        if mascot.state is not _S.SPINNING:
            assert mascot.scale_x * mascot.scale_y == pytest.approx(1.0, abs=1e-9)
        expressions.add(mascot.expression)
        effects.add(mascot.effect)
    assert visited == set(MascotState)  # كل الحالات التسع عشرة زُرتها
    assert expressions == set(Expression) and effects == set(Effect)


def test_stays_within_stage_bounds_plus_width() -> None:
    for scale in (0.5, 1.0, 2.0):
        mascot = _make(seed=5, scale=scale)
        margin = mascot.width_px
        for _ in _run(mascot, _HOUR_S, pointer=_gestures):
            assert _STAGE[0] - margin - 1e-9 <= mascot.x <= _STAGE[1] + margin + 1e-9


def test_shrinking_the_stage_pulls_a_visible_mascot_back_inside() -> None:
    mascot = _make(seed=2)
    for _ in _run(mascot, 600.0):
        if mascot.visible and mascot.x > 1000.0:
            break
    assert mascot.visible and mascot.x > 1000.0
    mascot.set_stage(0.0, 800.0, 700.0)
    assert mascot.x <= 800.0 + mascot.width_px
    for _ in _run(mascot, 120.0):
        assert mascot.x <= 800.0 + mascot.width_px + 1e-9


def test_visible_time_before_exit_is_between_12_and_35_seconds_without_interaction() -> None:
    mascot = _make(seed=4)
    started = clock = 0.0
    durations: list[float] = []
    previous = mascot.state
    for _ in _run(mascot, 4 * _HOUR_S):
        clock += _DT
        if mascot.state is not previous:
            if mascot.state is _S.ENTERING:
                started = clock
            elif mascot.state is _S.EXITING:
                durations.append(clock - started)
            previous = mascot.state
    assert len(durations) > 100
    # القفز لا يُقطع في الهواء (تهيؤ + طيران + هبوط)، والنطتان المتتاليتان أطول: هامش 3.5 s.
    assert min(durations) >= 12.0 - _DT and max(durations) <= 35.0 + 3.5


def test_enters_from_outside_an_edge_at_walking_speed() -> None:
    mascot = _make(seed=6)
    for _ in _run(mascot, 600.0):
        if mascot.state is _S.ENTERING:
            break
    first_x = mascot.x
    mascot.step(0.04, 0.0)
    speed = abs(mascot.x - first_x) / 0.04
    assert 70.0 <= speed <= 110.0 + 1e-6
    assert (mascot.x - first_x) * mascot.facing > 0  # يمشي في اتجاه وجهه


# --------------------------------------------------------------------- القفز والهبوط
def test_every_jump_apex_matches_the_ballistic_formula_within_five_percent() -> None:
    mascot = _make(seed=8)
    apexes: list[tuple[float, float]] = []  # (الذروة، المتوقعة)
    lowest: float | None = None
    for _ in _run(mascot, 2 * _HOUR_S, dt=1.0 / 120.0):
        if mascot.state in (_S.JUMPING, _S.STARTLED):
            lowest = mascot.y if lowest is None else min(lowest, mascot.y)
            expected = mascot.jump_v0**2 / (2.0 * GRAVITY_PX_S2)
        elif lowest is not None:
            apexes.append((_GROUND - lowest, expected))
            lowest = None
    assert len(apexes) > 40
    assert any(abs(e - 75.1) < 0.2 for _, e in apexes)  # القفزة الكبيرة 520 px/s
    assert any(e < 30.0 for _, e in apexes)  # ونطات صغيرة
    for apex, expected in apexes:
        assert apex == pytest.approx(expected, rel=0.05)


def test_landing_squash_envelope_returns_to_one_within_a_second() -> None:
    mascot = _make(seed=8)
    steps: list[float] = []
    big = deepest = 0
    previous = mascot.state
    for _ in _run(mascot, 2 * _HOUR_S, dt=1.0 / 120.0):
        if mascot.state is _S.LANDING:
            steps.append(mascot.scale_y)
            assert mascot.scale_y > 0.7  # الضغط الأقصى 1 - 0.28 = 0.72
            assert mascot.scale_x * mascot.scale_y == pytest.approx(1.0, abs=1e-9)
        elif previous is _S.LANDING:
            assert len(steps) / 120.0 <= 1.0  # الهبوط كله أقل من ثانية
            assert steps[-1] == pytest.approx(1.0, abs=1e-3)  # عاد إلى 1
            if mascot.jump_v0 == -520.0:
                big += 1
                deepest += min(steps) < 0.8  # القفزة الكبيرة تضغط فعلًا
            steps = []
        previous = mascot.state
    assert big > 10 and deepest == big


def test_anticipation_squashes_before_the_jump() -> None:
    mascot = _make(seed=8)
    lowest = 1.0
    for _ in _run(mascot, 2 * _HOUR_S, dt=1.0 / 120.0):
        if mascot.state is _S.CROUCHING:
            lowest = min(lowest, mascot.scale_y)
    assert lowest == pytest.approx(0.8, abs=0.02)


# --------------------------------------------------------------------- التعطيل والجدولة
def test_disabled_mascot_stays_hidden_forever_even_with_interaction() -> None:
    mascot = _make(enabled=False)
    for _ in _run(mascot, _HOUR_S, pointer=_gestures):
        mascot.startle()
        assert mascot.state is _S.HIDDEN and not mascot.visible


def test_disabling_hides_immediately_and_reenabling_waits_at_least_twenty_seconds() -> None:
    mascot = _make(seed=2)
    for _ in _run(mascot, 600.0):
        if mascot.visible:
            break
    assert mascot.visible
    mascot.configure(False, 1.0, 1.0)
    assert mascot.state is _S.HIDDEN and mascot.effect is Effect.NONE
    mascot.configure(True, 1.0, 1.0)
    for _ in _run(mascot, 19.0):
        assert mascot.state is _S.HIDDEN


def _gaps(frequency: float, hours: float, seed: int = 1) -> list[float]:
    """الأزمنة بين الاختفاء والظهور التالي (ثوانٍ)."""
    mascot = _make(seed=seed, frequency=frequency)
    gaps: list[float] = []
    clock = hidden_since = 0.0
    previous = mascot.state
    for _ in _run(mascot, hours * _HOUR_S, dt=0.05):
        clock += 0.05
        if mascot.state is not previous:
            if mascot.state is _S.HIDDEN:
                hidden_since = clock
            elif previous is _S.HIDDEN and hidden_since > 0.0:
                gaps.append(clock - hidden_since)
            previous = mascot.state
    return gaps


def test_scheduler_respects_minimum_gap_and_frequency_scaling() -> None:
    often, rare = _gaps(1.0, 8.0), _gaps(0.0, 24.0)
    assert len(often) > 250 and len(rare) > 50
    assert min(often) >= 20.0 - 0.05
    # E[max(20, Exp(mean))] = 20 + mean * exp(-20 / mean): نحو 48.8 s عند 45 وسط 240.8 عند 240.
    mean_often, mean_rare = sum(often) / len(often), sum(rare) / len(rare)
    assert 41.0 <= mean_often <= 58.0
    assert 180.0 <= mean_rare <= 310.0
    assert mean_rare > 3.0 * mean_often


def test_stays_hidden_until_a_wide_enough_stage_is_set() -> None:
    mascot = Mascot(random.Random(1))
    mascot.configure(True, 1.0, 1.0)  # بلا set_stage: المسرح بعرض صفر
    for _ in _run(mascot, 600.0, dt=0.05):
        assert mascot.state is _S.HIDDEN


def test_determinism_same_seed_same_trajectory_with_pointer() -> None:
    def trajectory(seed: int) -> list[tuple[str, float, float]]:
        mascot = _make(seed=seed)
        return [
            (m.state.value, round(m.x, 6), round(m.y, 6))
            for m in _run(mascot, 600.0, pointer=_gestures)
        ]

    assert trajectory(9) == trajectory(9)
    assert trajectory(9) != trajectory(10)


def test_size_properties_follow_scale() -> None:
    mascot = _make(scale=2.0)
    assert mascot.height_px == pytest.approx(2.0 * BASE_HEIGHT_PX)
    assert mascot.width_px == pytest.approx(0.92 * mascot.height_px)
    mascot.configure(True, 1.0, 9.0)  # يُقصّ إلى 2
    assert mascot.height_px == pytest.approx(2.0 * BASE_HEIGHT_PX)


# --------------------------------------------------------------------- النظر والرمش
def test_look_direction_follows_the_wind_when_no_pointer() -> None:
    mascot = _make()
    for _ in _run(mascot, 5.0, wind=1.0):
        pass
    assert mascot.look_dir > 0.95
    for _ in _run(mascot, 5.0, wind=-1.0):
        pass
    assert mascot.look_dir < -0.95


def test_eyes_follow_a_nearby_pointer_and_ignore_a_far_one() -> None:
    mascot = _calm_mascot()
    for offset, expect in ((150.0, 1), (-150.0, -1)):
        for _ in _run(mascot, 2.0, dt=_FINE, pointer=lambda _t, m, o=offset: (m.x + o, m.y - 20)):
            pass
        assert mascot.look_dir * expect > 0.4
    for _ in _run(mascot, 2.0, dt=_FINE, pointer=lambda _t, m: (m.x, m.y - 200)):
        pass
    assert mascot.look_y < -0.3  # المؤشر فوقه فينظر للأعلى
    for _ in _run(mascot, 3.0, dt=_FINE, wind=0.0, pointer=lambda _t, m: (m.x + 900, m.y)):
        pass
    assert abs(mascot.look_dir) < 0.2  # بعيد جدًا: يعود لنظرة الرياح (صفر)


def test_blinks_happen_at_a_natural_rate() -> None:
    mascot = _make(seed=7)
    blinks = 0
    visible_s = 0.0
    closed = False
    for _ in _run(mascot, 2 * _HOUR_S, dt=_FINE):
        if mascot.visible and mascot.state not in (_S.SLEEPING, _S.PETTED):
            visible_s += _FINE
            now_closed = mascot.blink > 0.5
            blinks += now_closed and not closed
            closed = now_closed
    assert visible_s > 600.0
    assert 1.0 / 6.0 <= blinks / visible_s <= 1.0 / 1.5  # رمشة كل 1.5-6 s


# --------------------------------------------------------------------- التفاعل مع المؤشر
def test_petting_by_wiggling_over_the_body_makes_him_happy_then_hop() -> None:
    mascot = _calm_mascot()
    clock = 0.0

    def wiggle(_t: float, m: Mascot) -> tuple[float, float]:
        nonlocal clock
        clock += _FINE
        return m.x + 16.0 * math.sin(2.0 * math.pi * 3.0 * clock), m.y - 18.0

    seen = {}
    for m in _run(mascot, 4.0, dt=_FINE, pointer=wiggle):
        if m.state is _S.PETTED:
            seen["expression"], seen["effect"] = m.expression, m.effect
    assert seen == {"expression": Expression.LOVE, "effect": Effect.HEARTS}
    after = _states_during(mascot, 14.0, lambda _t, m: (m.x, m.y - 18.0))  # يكفّ عن المسح
    assert _S.CROUCHING in after  # نطات الفرح بعد التمسيح


def test_wiggling_beside_him_is_not_petting() -> None:
    mascot = _calm_mascot()
    clock = 0.0

    def beside(_t: float, m: Mascot) -> tuple[float, float]:
        nonlocal clock
        clock += _FINE
        return m.x + 140.0 + 16.0 * math.sin(2.0 * math.pi * 3.0 * clock), m.y - 18.0

    assert _S.PETTED not in _states_during(mascot, 5.0, beside)


def _rush(offset_start: float, speed: float) -> Pointer:
    clock = 0.0

    def pointer(_t: float, m: Mascot) -> tuple[float, float]:
        nonlocal clock
        clock += _FINE
        return m.x + max(10.0, offset_start - speed * clock), m.y - 20.0

    return pointer


def test_a_fast_rush_startles_him_then_he_shivers_and_the_cooldown_holds() -> None:
    mascot = _calm_mascot()
    states = _states_during(mascot, 4.0, _rush(400.0, 2500.0))
    assert _S.STARTLED in states and _S.SHIVERING in states
    assert states.index(_S.STARTLED) < states.index(_S.SHIVERING)
    # نفس الاندفاع بعد ثوانٍ قليلة (أقل من تبريد 8 s) لا يفزعه ثانية.
    assert _S.STARTLED not in _states_during(mascot, 3.0, _rush(400.0, 2500.0))


def test_a_slow_pointer_never_startles_him() -> None:
    mascot = _calm_mascot()
    assert _S.STARTLED not in _states_during(mascot, 6.0, _rush(500.0, 90.0))


def _hold(dx: float, dy: float) -> Pointer:
    anchor: list[float] = []

    def pointer(_t: float, m: Mascot) -> tuple[float, float]:
        if not anchor:
            anchor.extend((min(m.x + dx, 1850.0), _GROUND + dy))
        return anchor[0], anchor[1]

    return pointer


def test_a_still_pointer_near_the_taskbar_makes_him_curious_and_wave() -> None:
    mascot = _calm_mascot()
    states: list[MascotState] = []
    first_wave: tuple[float, int] | None = None
    pointer = _hold(200.0, -30.0)
    anchor_x = 0.0
    for m in _run(mascot, 12.0, dt=_FINE, pointer=pointer):
        anchor_x = pointer(0.0, m)[0]
        states.append(m.state)
        if m.state is _S.WAVING and first_wave is None:
            first_wave = (m.x, m.facing)
    assert _S.CURIOUS in states and first_wave is not None
    assert states.index(_S.CURIOUS) < states.index(_S.WAVING)
    wave_x, wave_facing = first_wave
    assert abs(anchor_x - wave_x) <= 75.0  # اقترب من المؤشر قبل التلويح
    assert (anchor_x - wave_x) * wave_facing >= 0.0  # ووجهه نحوه


def test_a_still_pointer_high_on_the_screen_does_not_attract_him() -> None:
    mascot = _calm_mascot()
    assert _S.CURIOUS not in _states_during(mascot, 15.0, _hold(120.0, -700.0))


def test_after_waving_a_fast_sweep_invites_him_to_chase_and_catch_the_pointer() -> None:
    mascot = _calm_mascot()
    target = [0.0]
    phase = {"t": 0.0}

    def pointer(_t: float, m: Mascot) -> tuple[float, float]:
        phase["t"] += _FINE
        if phase["t"] == _FINE:
            target[0] = min(m.x + 200.0, 1500.0)
        if 9.0 < phase["t"] < 9.6:  # بعد التلويح: مسح سريع نحو اليمين
            target[0] += 600.0 * _FINE
        return target[0], _GROUND - 30.0

    states = [m.state for m in _run(mascot, 16.0, dt=_FINE, pointer=pointer)]
    assert _S.WAVING in states and _S.CHASING in states
    assert abs(mascot.x - target[0]) < 80.0  # أمسك المؤشر أو اقترب منه
    assert _S.CROUCHING in states[states.index(_S.CHASING) :]  # ونط فرحًا


def test_lightning_startles_a_calm_drip_but_not_a_hidden_or_recently_startled_one() -> None:
    hidden = _make()
    hidden.startle()
    for _ in _run(hidden, 0.2):
        assert hidden.state is _S.HIDDEN
    mascot = _calm_mascot()
    mascot.startle()
    mascot.step(_FINE, 0.0)
    assert mascot.state is _S.STARTLED and mascot.effect is Effect.ALERT
    for _ in _run(mascot, 1.0, dt=_FINE):
        pass
    mascot.startle()  # أقل من 3 s من الفزعة السابقة
    mascot.step(_FINE, 0.0)
    assert mascot.state is not _S.STARTLED


def test_storm_makes_him_shiver_sometimes_and_a_drizzle_never() -> None:
    def shivers(rain: float) -> int:
        mascot = _make(seed=11)
        mascot.set_weather(rain)
        return sum(1 for m in _run(mascot, 2 * _HOUR_S) if m.state is _S.SHIVERING)

    assert shivers(1.0) > 0
    assert shivers(0.3) == 0


def test_losing_the_pointer_cancels_curiosity_and_chasing() -> None:
    mascot = _calm_mascot()
    clock = 0.0

    def vanishing(_t: float, m: Mascot) -> tuple[float, float] | None:
        nonlocal clock
        clock += _FINE
        return (min(m.x + 200.0, 1800.0), _GROUND - 30.0) if clock < 1.6 else None

    states = _states_during(mascot, 20.0, vanishing)
    assert all(state is not _S.CURIOUS for state in states[-600:])  # لا يعلق في الفضول