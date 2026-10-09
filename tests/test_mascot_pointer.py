"""tests/test_mascot_pointer.py: وحدات Drip النقية: متتبع المؤشر ومنتقي ردود الفعل والهيئة."""

from __future__ import annotations

import math

import pytest

from raindesk.core.constants import GRAVITY_PX_S2
from raindesk.engine.mascot_pointer import PointerTracker, Reaction, in_play_zone, pick_reaction
from raindesk.engine.mascot_pose import (
    ARM_REST_DEG,
    HOP_V0_PX_S,
    JUMP_V0_PX_S,
    LANDING_S,
    Effect,
    Expression,
    MascotState,
    blink_amount,
    compute_pose,
    crouch_scale,
    flight_scale,
    flight_time,
    jump_offset,
    landing_scale,
)

_S = MascotState
_DT = 1.0 / 60.0
_CX, _BOTTOM, _WIDTH, _HEIGHT = 500.0, 1040.0, 40.0, 44.0  # جسم Drip النموذجي


def _feed(
    tracker: PointerTracker, positions: list[tuple[float, float] | None], dt: float = _DT
) -> None:
    for position in positions:
        tracker.update(dt, position, _CX, _BOTTOM, _WIDTH, _HEIGHT)


def _wiggle(
    seconds: float, amplitude: float, hz: float, y: float = _BOTTOM - 18.0
) -> list[tuple[float, float]]:
    steps = round(seconds / _DT)
    return [(_CX + amplitude * math.sin(2.0 * math.pi * hz * k * _DT), y) for k in range(steps)]


# --------------------------------------------------------------------- متتبع المؤشر
def test_tracker_starts_absent_and_forgets_when_the_pointer_leaves() -> None:
    tracker = PointerTracker()
    assert not tracker.present and not tracker.petting and tracker.speed == 0.0
    _feed(tracker, [(600.0, 1000.0)] * 5)
    assert tracker.present
    _feed(tracker, [None])
    assert not tracker.present and tracker.dist == math.inf and tracker.still_time == 0.0


def test_tracker_measures_offset_distance_and_inside_box() -> None:
    tracker = PointerTracker()
    _feed(tracker, [(_CX + 100.0, _BOTTOM - _HEIGHT / 2.0)])
    assert tracker.dx == pytest.approx(100.0)
    assert tracker.dy == pytest.approx(0.0)
    assert tracker.dist == pytest.approx(100.0)
    assert not tracker.inside
    _feed(tracker, [(_CX + 10.0, _BOTTOM - 20.0)])
    assert tracker.inside
    _feed(tracker, [(_CX + 10.0, _BOTTOM - 120.0)])  # فوق الرأس
    assert not tracker.inside


def test_tracker_speed_and_approach_reflect_motion_toward_the_body() -> None:
    tracker = PointerTracker()
    start = _CX + 400.0
    _feed(tracker, [(start - 600.0 * k * _DT, _BOTTOM - 20.0) for k in range(30)])
    assert tracker.speed == pytest.approx(600.0, rel=0.1)
    assert tracker.approach == pytest.approx(600.0, rel=0.1)  # يقترب
    _feed(tracker, [(_CX + 600.0 * k * _DT, _BOTTOM - 20.0) for k in range(30)])
    assert tracker.approach < 0.0  # يبتعد


def test_tracker_still_time_accumulates_only_while_still() -> None:
    tracker = PointerTracker()
    _feed(tracker, [(700.0, 1000.0)] * 90)
    assert tracker.still_time == pytest.approx(89 * _DT, abs=_DT)
    _feed(tracker, [(700.0 + 40.0 * k, 1000.0) for k in range(10)])
    assert tracker.still_time == 0.0


def test_a_teleport_between_screens_is_not_a_fast_motion() -> None:
    tracker = PointerTracker()
    _feed(tracker, [(100.0, 100.0)] * 5 + [(1800.0, 900.0)])
    assert tracker.speed == 0.0 and tracker.present


def test_petting_needs_three_reversals_over_the_body() -> None:
    tracker = PointerTracker()
    _feed(tracker, _wiggle(0.2, 16.0, 3.0))
    assert not tracker.petting  # لم تكتمل ثلاثة انعكاسات بعد
    _feed(tracker, _wiggle(1.5, 16.0, 3.0))
    assert tracker.petting and tracker.reversals >= 3


def test_tiny_jitter_and_wiggles_beside_the_body_are_not_petting() -> None:
    jitter = PointerTracker()
    _feed(jitter, _wiggle(2.0, 3.0, 8.0))  # سعة 3 px: دون المسافة الدنيا بين الانعكاسين
    assert not jitter.petting
    beside = PointerTracker()
    _feed(beside, [(x + 140.0, y) for x, y in _wiggle(2.0, 16.0, 3.0)])
    assert not beside.petting


def test_petting_fades_after_the_wiggling_stops() -> None:
    tracker = PointerTracker()
    _feed(tracker, _wiggle(1.5, 16.0, 3.0))
    assert tracker.petting
    _feed(tracker, [(_CX, _BOTTOM - 18.0)] * 150)  # ساكن 2.5 s
    assert not tracker.petting


# --------------------------------------------------------------------- منتقي ردود الفعل
def _tracker_with(
    position: tuple[float, float], speed: float = 0.0, still: float = 0.0, petting: bool = False
) -> PointerTracker:
    """متتبع بقيم مضبوطة يدويًا (نختبر منطق الاختيار لا فيزياء التتبع)."""
    tracker = PointerTracker()
    _feed(tracker, [position])
    tracker.vx, tracker.vy = speed, 0.0
    tracker.approach = speed if position[0] > _CX else -speed
    tracker.still_time = still
    if petting:
        tracker._stamps = [tracker._clock] * 3
        tracker.inside = True
    return tracker


_READY = {"startle_ready": True, "chase_ready": True, "curious_ready": True}


def test_no_pointer_means_no_reaction() -> None:
    assert pick_reaction(PointerTracker(), _BOTTOM, **_READY) is Reaction.NONE


def test_petting_beats_everything() -> None:
    tracker = _tracker_with((_CX + 5.0, _BOTTOM - 20.0), speed=1500.0, petting=True)
    assert pick_reaction(tracker, _BOTTOM, **_READY) is Reaction.PET


def test_a_close_fast_approach_startles_unless_on_cooldown() -> None:
    tracker = _tracker_with((_CX + 120.0, _BOTTOM - 20.0), speed=1500.0)
    tracker.approach = 1500.0
    assert pick_reaction(tracker, _BOTTOM, **_READY) is Reaction.STARTLE
    cooling = {**_READY, "startle_ready": False}
    assert pick_reaction(tracker, _BOTTOM, **cooling) is Reaction.CHASE  # يتحول لدعوة لعب


def test_fast_motion_far_away_or_moving_away_does_not_startle() -> None:
    far = _tracker_with((_CX + 400.0, _BOTTOM - 20.0), speed=1500.0)
    far.approach = 1500.0
    assert pick_reaction(far, _BOTTOM, **_READY) is not Reaction.STARTLE
    leaving = _tracker_with((_CX + 100.0, _BOTTOM - 20.0), speed=1500.0)
    leaving.approach = -1500.0
    assert pick_reaction(leaving, _BOTTOM, **_READY) is not Reaction.STARTLE


def test_chase_and_curiosity_need_the_play_zone_near_the_taskbar() -> None:
    near, high = (_CX + 250.0, _BOTTOM - 30.0), (_CX + 250.0, _BOTTOM - 700.0)
    assert in_play_zone(_tracker_with(near), _BOTTOM)
    assert not in_play_zone(_tracker_with(high), _BOTTOM)
    assert pick_reaction(_tracker_with(near, speed=400.0), _BOTTOM, **_READY) is Reaction.CHASE
    assert pick_reaction(_tracker_with(high, speed=400.0), _BOTTOM, **_READY) is Reaction.NONE
    still = _tracker_with((_CX + 200.0, _BOTTOM - 30.0), still=1.5)
    assert pick_reaction(still, _BOTTOM, **_READY) is Reaction.CURIOUS
    assert (
        pick_reaction(_tracker_with((_CX + 200.0, _BOTTOM - 30.0), still=0.4), _BOTTOM, **_READY)
        is Reaction.NONE
    )
    assert (
        pick_reaction(still, _BOTTOM, startle_ready=True, chase_ready=True, curious_ready=False)
        is Reaction.NONE
    )


# --------------------------------------------------------------------- الهيئة والمنحنيات
def test_flight_physics_formulas() -> None:
    assert flight_time(JUMP_V0_PX_S) == pytest.approx(2.0 * 520.0 / GRAVITY_PX_S2)
    apex = min(jump_offset(k * 0.001, JUMP_V0_PX_S) for k in range(600))
    assert -apex == pytest.approx(520.0**2 / (2.0 * GRAVITY_PX_S2), rel=1e-3)
    assert jump_offset(flight_time(HOP_V0_PX_S), HOP_V0_PX_S) == pytest.approx(0.0, abs=1e-9)


def test_landing_squash_shape_and_decay() -> None:
    assert landing_scale(0.0) == pytest.approx(0.72)  # 1 - 0.28 عند الارتطام
    assert landing_scale(LANDING_S) == pytest.approx(1.0, abs=1e-3)
    assert max(landing_scale(k * 0.005) for k in range(160)) > 1.0  # يتجاوز 1 مرة (follow-through)
    assert landing_scale(0.0, HOP_V0_PX_S) > landing_scale(0.0, JUMP_V0_PX_S)  # النطة أخف ضغطًا


def test_crouch_and_flight_scales() -> None:
    assert crouch_scale(0.0, 0.12) == 1.0
    assert crouch_scale(0.12, 0.12) == pytest.approx(0.8)
    assert crouch_scale(0.5, 0.12) == pytest.approx(0.8)  # لا يتجاوز الحد
    assert flight_scale(0.0, JUMP_V0_PX_S) == pytest.approx(0.8)  # يبدأ من الضغط
    assert flight_scale(0.1, JUMP_V0_PX_S) > 1.0  # ثم يتمدد
    assert flight_scale(flight_time(JUMP_V0_PX_S) / 2.0, JUMP_V0_PX_S) < flight_scale(
        0.1, JUMP_V0_PX_S
    )


def test_blink_curve_is_a_triangle() -> None:
    assert blink_amount(-0.01) == 0.0 and blink_amount(0.0) == 0.0
    assert blink_amount(0.07) == pytest.approx(1.0)
    assert blink_amount(0.14) == 0.0 and blink_amount(1.0) == 0.0


def _pose(state: MascotState, t: float = 0.3, rain: float = 0.5, duration: float = 1.0):  # noqa: ANN202
    return compute_pose(state, t, duration, 0.4, rain, JUMP_V0_PX_S)


def test_each_state_has_its_signature_pose() -> None:
    assert _pose(_S.SLEEPING, t=2.0).effect is Effect.ZZZ and _pose(_S.SLEEPING).eyes_closed == 1.0
    assert _pose(_S.SLEEPING, t=0.5).mouth_open == pytest.approx(1.0)  # ذروة التثاؤب
    assert (
        _pose(_S.PETTED).expression is Expression.LOVE and _pose(_S.PETTED).effect is Effect.HEARTS
    )
    assert _pose(_S.STARTLED, t=0.1).expression is Expression.SURPRISED
    assert _pose(_S.STARTLED, t=0.1).effect is Effect.ALERT
    assert (
        _pose(_S.SHIVERING).expression is Expression.SCARED
        and _pose(_S.SHIVERING).effect is Effect.SWEAT
    )
    assert _pose(_S.WAVING).arm_r > 100.0 and _pose(_S.WAVING).arm_l == ARM_REST_DEG
    assert (
        _pose(_S.DANCING).expression is Expression.HAPPY
        and _pose(_S.DANCING).arm_l != _pose(_S.DANCING).arm_r
    )
    assert _pose(_S.JUMPING, t=0.2).arm_l > 90.0
    assert _pose(_S.IDLE).expression is Expression.NEUTRAL and _pose(_S.IDLE).effect is Effect.NONE
    assert _pose(_S.HIDDEN).scale_y == 1.0


def test_looking_up_catches_raindrops_only_when_it_rains() -> None:
    assert _pose(_S.LOOK_UP, rain=0.8).mouth_open > 0.5
    assert _pose(_S.LOOK_UP, rain=0.8).effect is Effect.SPARKLE
    assert _pose(_S.LOOK_UP, rain=0.1).mouth_open == 0.0


def test_spinning_never_collapses_to_zero_width_and_makes_a_full_turn() -> None:
    turns = [_pose(_S.SPINNING, t=k * 0.8 / 200.0, duration=0.8).turn for k in range(201)]
    assert turns[0] == pytest.approx(1.0) and turns[-1] == pytest.approx(1.0)
    assert min(abs(turn) for turn in turns) >= 0.14 - 1e-9
    assert min(turns) < 0.0  # يمرّ بالجهة المعاكسة (دورة كاملة)


def test_walking_arms_swing_in_opposition() -> None:
    left, right = [], []
    for k in range(40):
        pose = compute_pose(_S.WALKING, 0.0, 1.0, k * 0.05, 0.0, JUMP_V0_PX_S)
        left.append(pose.arm_l - ARM_REST_DEG)
        right.append(pose.arm_r - ARM_REST_DEG)
    assert all(a == pytest.approx(-b) for a, b in zip(left, right, strict=True))
    assert max(left) > 10.0 and min(left) < -10.0