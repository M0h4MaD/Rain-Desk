"""raindesk/engine/mascot.py

الغرض: Drip: القطرة اللطيفة التي تمشي وترقص وتلعب مع مؤشرك (بلا Qt).
المسؤوليات: السلوكات العشوائية (مشي، وقوف، التقاط المطر، قفز، نفض، رقص، نوم، تلويح، دوران،
    نطات، ارتجاف)، وردود الفعل على المؤشر (فضول، مطاردة، تمسيح، فزع) وعلى البرق، وخطوات
    الحالات الـ 19، والفيزياء الباليستية التحليلية.
الاعتماديات: engine.mascot_core (النواة) وmascot_pose (الهيئة) وmascot_pointer (إشارات المؤشر)
    وmath_utils وcore.constants (DT_MAX_S).
النمط التصميمي: State (آلة منتهية) + Scheduler عشوائي؛ الرسم في ui/painters/mascot_painter.
ملاحظات: التفاعل بصري فقط: يُحقن موضع المؤشر (set_pointer) ولا تعترض الشخصية أي مدخلات،
    فتبقى النافذة click-through. الظهور التالي ~ max(20, Exp(mean = lerp(240, 45, frequency))).
    مدة الظهور المرئي تُحسب من بدء ENTERING حتى بدء EXITING.
مثال: drip = Mascot(random.Random(7)); drip.configure(True, 0.4, 1.0); drip.set_pointer((300, 900))
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from typing import Final

from raindesk.core.constants import DT_MAX_S
from raindesk.engine import mascot_tuning as tune
from raindesk.engine.mascot_core import (
    AFTER_NORMAL,
    AFTER_SHIVER,
    BASE_HEIGHT_PX,
    BODY_WIDTH_RATIO,
    MascotCore,
)
from raindesk.engine.mascot_pointer import Reaction, in_play_zone, pick_reaction
from raindesk.engine.mascot_pose import (
    HOP_V0_PX_S,
    JUMP_V0_PX_S,
    LANDING_S,
    STARTLE_V0_PX_S,
    STEP_HZ,
    Effect,
    Expression,
    MascotState,
    flight_time,
    jump_offset,
)
from raindesk.engine.math_utils import clamp

__all__ = ["BASE_HEIGHT_PX", "BODY_WIDTH_RATIO", "Effect", "Expression", "Mascot", "MascotState"]

_S = MascotState

_CALM: Final[frozenset[MascotState]] = frozenset(
    {
        _S.WALKING,
        _S.IDLE,
        _S.LOOK_UP,
        _S.SHAKING,
        _S.DANCING,
        _S.SLEEPING,
        _S.WAVING,
        _S.SPINNING,
    }
)
_REACTIVE: Final[frozenset[MascotState]] = _CALM | {_S.CURIOUS, _S.CHASING}
_STARTLEABLE: Final[frozenset[MascotState]] = _REACTIVE | {_S.PETTED}
_TIMED: Final[frozenset[MascotState]] = frozenset(
    {
        _S.IDLE,
        _S.LOOK_UP,
        _S.SHAKING,
        _S.DANCING,
        _S.SLEEPING,
        _S.WAVING,
        _S.SPINNING,
        _S.SHIVERING,
    }
)
_GROUND: Final[frozenset[MascotState]] = _TIMED | {_S.CROUCHING, _S.LANDING, _S.PETTED}


class Mascot(MascotCore):
    """Drip كاملة: النواة (MascotCore) مع السلوكات وردود الفعل وخطوات الحالات.

    السمات العامة موثقة في MascotCore. التعقيد: step هو O(1). سلامة الخيوط: الواجهة فقط.
    """

    def __init__(self, rng: random.Random) -> None:
        """rng مُحقَن (كل العشوائية منه فالتشغيل حتمي بالبذرة)."""
        super().__init__(rng)

        self._begin: dict[str, Callable[[], None]] = {
            "walk": self._begin_walk,
            "jump": self._begin_big_jump,
            "hops": self._begin_hops,
            "idle": lambda: self._begin_timed(_S.IDLE, "idle"),
            "look_up": lambda: self._begin_timed(_S.LOOK_UP, "look_up"),
            "shake": lambda: self._begin_timed(_S.SHAKING, "shake"),
            "dance": lambda: self._begin_timed(_S.DANCING, "dance"),
            "sleep": lambda: self._begin_timed(_S.SLEEPING, "sleep"),
            "wave": self._begin_wave,
            "shiver": lambda: self._begin_timed(_S.SHIVERING, "shiver"),
            "spin": lambda: self._begin_timed(_S.SPINNING, "spin"),
        }
        self._handlers: dict[MascotState, Callable[[float], None]] = {
            _S.ENTERING: self._step_entering,
            _S.WALKING: self._step_walking,
            _S.CURIOUS: self._step_curious,
            _S.CHASING: self._step_chasing,
            _S.PETTED: self._step_petted,
            _S.CROUCHING: self._step_crouching,
            _S.JUMPING: self._step_flight,
            _S.STARTLED: self._step_flight,
            _S.LANDING: self._step_landing,
            _S.EXITING: self._step_exiting,
        }

    def step(self, dt: float, wind_sign: float) -> None:
        """يقدّم الحالة بزمن dt ثانية؛ wind_sign في [-1, 1] اتجاه الرياح الذي تنظر إليه العينان."""
        if not self._enabled:
            return
        dt = clamp(dt, 0.0, DT_MAX_S)
        if self.visible:
            self._pointer.update(
                dt, self._pointer_pos, self.x, self._ground, self.width_px, self.height_px
            )
        else:
            self._pointer.reset()
        self._update_look(dt, wind_sign)
        if not self.visible:
            self._step_hidden(dt)
            return
        self._timer += dt
        self._appeared += dt
        self._cd_chase, self._cd_curious, self._cd_startle, self._play_window = (
            max(0.0, value - dt)
            for value in (self._cd_chase, self._cd_curious, self._cd_startle, self._play_window)
        )
        self._update_blink(dt)
        self._react()
        if self.state in _REACTIVE and self._appeared >= self._budget:
            self._begin_exit()
        else:
            handler = self._handlers.get(self.state)
            if handler is not None:
                handler(dt)
            elif self._timer >= self._duration:  # كل الحالات المؤقتة
                self._finish_timed()
        self._apply_pose()
        if self.visible:
            if self.state in _GROUND:
                self.y = self._ground
            self._clamp_x()

    # ------------------------------------------------------------------ ردود الفعل
    def _react(self) -> None:
        """يقيّم البرق ثم المؤشر ويبدّل الحالة عند الحاجة (من الحالات الهادئة فقط)."""
        if self._startle_pending:
            self._startle_pending = False
            if self.state in _STARTLEABLE and self._cd_startle <= 0.0:
                self._begin_startle(self._rng.choice((-1, 1)), tune.COOLDOWN_LIGHTNING_S)
                return
        if self.state not in _REACTIVE:
            return
        pointer = self._pointer
        reaction = pick_reaction(
            pointer,
            self._ground,
            startle_ready=self._cd_startle <= 0.0,
            chase_ready=self._cd_chase <= 0.0 and self.state is not _S.CHASING,
            curious_ready=self._cd_curious <= 0.0 and self.state not in (_S.CURIOUS, _S.CHASING),
        )
        if reaction is Reaction.PET:
            self._set_state(_S.PETTED)
            self._duration = tune.PET_MIN_S
        elif reaction is Reaction.STARTLE:
            self._begin_startle(-1 if pointer.dx > 0 else 1, tune.COOLDOWN_STARTLE_S)
        elif reaction is Reaction.CHASE:
            accept = self._play_window > 0.0 or self._rng.random() < tune.CHASE_CHANCE
            self._cd_chase = tune.COOLDOWN_CHASE_S if accept else tune.COOLDOWN_DECLINED_S
            if accept:
                self._set_state(_S.CHASING)
                self._chase_speed = self._rng.uniform(*tune.CHASE_SPEED_PX_S)
                self._chase_near = 0.0
        elif reaction is Reaction.CURIOUS:
            self._cd_curious = tune.COOLDOWN_CURIOUS_S
            self._begin_curious()

    def _begin_startle(self, away: int, cooldown: float) -> None:
        """قفزة فزع: يبتعد في اتجاه away ثم يرتجف قليلًا بعد الهبوط."""
        self._cd_startle = cooldown
        self._hops_left = 0
        self._after_landing = AFTER_SHIVER
        self._launch(STARTLE_V0_PX_S, away * tune.STARTLE_VX_PX_S, _S.STARTLED)

    def _begin_curious(self) -> None:
        pointer = self._pointer
        if abs(pointer.dx) <= tune.WAVE_DISTANCE_PX:
            self._begin_wave()
            return
        self._set_state(_S.CURIOUS)
        self.facing = 1 if pointer.dx > 0 else -1

    # ------------------------------------------------------------------ السلوكات
    def _behaviour_table(self) -> tuple[list[str], list[float]]:
        """أسماء السلوكات وأوزانها؛ الارتجاف يدخل مع المطر الغزير فقط."""
        names = [name for name, _ in tune.BEHAVIOURS]
        weights = [weight for _, weight in tune.BEHAVIOURS]
        excess = (self._rain - tune.SHIVER_RAIN_FROM) / (1.0 - tune.SHIVER_RAIN_FROM)
        shiver = tune.SHIVER_MAX_WEIGHT * clamp(excess, 0.0, 1.0)
        if shiver > 0.0:
            names.append("shiver")
            weights.append(shiver)
        return names, weights

    def _next_behaviour(self) -> None:
        """يختار السلوك العشوائي التالي أو يخرج إن انتهى زمن الظهور."""
        if self._appeared >= self._budget:
            self._begin_exit()
            return
        names, weights = self._behaviour_table()
        self._begin[self._rng.choices(names, weights=weights)[0]]()

    def _begin_timed(self, state: MascotState, key: str) -> None:
        self._set_state(state)
        self._duration = self._rng.uniform(*tune.DURATIONS[key])

    def _finish_timed(self) -> None:
        if self.state is _S.WAVING:
            self._play_window = tune.PLAY_WINDOW_S  # بعد التلويح يقبل دعوة اللعب فورًا
        self._next_behaviour()

    def _begin_wave(self) -> None:
        if self._pointer.present:
            self.facing = 1 if self._pointer.dx > 0 else -1
        self._begin_timed(_S.WAVING, "wave")

    def _begin_walk(self) -> None:
        margin = self.width_px
        low, high = self._left + margin, self._right - margin
        direction = self._rng.choice((-1, 1))
        distance = self._rng.uniform(*tune.WALK_DISTANCE_PX)
        if not low <= self.x + direction * distance <= high:
            direction = -direction  # لا نمشي نحو الحافة القريبة
        self._target_x = clamp(self.x + direction * distance, low, high)
        self.facing = 1 if self._target_x >= self.x else -1
        self._set_state(_S.WALKING)

    def _begin_exit(self) -> None:
        self._set_state(_S.EXITING)
        self.facing = -1 if self.x < (self._left + self._right) / 2.0 else 1  # أقرب حافة

    def _begin_big_jump(self) -> None:
        self._pending_v0, self._crouch_s = JUMP_V0_PX_S, 0.12
        self._start_crouch()

    def _begin_hops(self) -> None:
        self._hops_left = tune.FROLIC_HOPS
        self._start_hop()

    def _start_hop(self) -> None:
        self._hops_left -= 1
        self._pending_v0, self._crouch_s = HOP_V0_PX_S, tune.HOP_CROUCH_S
        self._start_crouch()

    def _start_crouch(self) -> None:
        self._set_state(_S.CROUCHING)
        self._duration = self._crouch_s

    def _launch(self, v0: float, vx: float, state: MascotState) -> None:
        """إقلاع باليستي تحليلي: y = y0 + v0*t + g*t^2/2 (لا تكامل عددي فلا يتراكم خطأ)."""
        self.jump_v0 = v0
        self._jump_x0, self._jump_y0, self._jump_vx = self.x, self._ground, vx
        if vx != 0.0:
            self.facing = 1 if vx > 0 else -1
        self._set_state(state)

    # ------------------------------------------------------------------ خطوات الحالات
    def _advance_walk(self, dt: float, speed: float, rate: float = 1.0) -> None:
        """يمشي في اتجاه facing مع ارتداد خطوة (قدم تلامس الأرض ثم ترتفع)."""
        self._phase += dt * rate
        self.x += self.facing * speed * dt
        bob = tune.BOB_PX * self._scale * abs(math.sin(math.pi * STEP_HZ * self._phase))
        self.y = self._ground - bob

    def _move_toward(self, target: float, speed: float, dt: float, rate: float = 1.0) -> float:
        """يتحرك نحو target داخل المسرح ولا يتجاوزه؛ يعيد المسافة المتبقية."""
        margin = self.width_px
        goal = clamp(target, self._left + margin, self._right - margin)
        delta = goal - self.x
        if abs(delta) > 1e-6:
            self.facing = 1 if delta > 0 else -1
        self._phase += dt * rate
        self.x += math.copysign(min(abs(delta), speed * dt), delta)
        bob = tune.BOB_PX * self._scale * abs(math.sin(math.pi * STEP_HZ * self._phase))
        self.y = self._ground - bob
        return abs(goal - self.x)

    def _step_entering(self, dt: float) -> None:
        self._advance_walk(dt, self._speed)
        margin = self.width_px
        if (self.facing > 0 and self.x >= self._left + margin) or (
            self.facing < 0 and self.x <= self._right - margin
        ):
            self.y = self._ground
            self._next_behaviour()

    def _step_walking(self, dt: float) -> None:
        if self._move_toward(self._target_x, self._speed, dt) <= 0.5:
            self.y = self._ground
            self._next_behaviour()

    def _step_curious(self, dt: float) -> None:
        """يقترب من المؤشر الساكن ثم يلوّح؛ يتخلى إن اختفى المؤشر أو طال الوقت."""
        pointer = self._pointer
        if not pointer.present or self._timer > tune.CURIOUS_MAX_S:
            self._next_behaviour()
            return
        self._move_toward(pointer.x, self._speed * tune.CURIOUS_SPEED_FACTOR, dt)
        if abs(pointer.x - self.x) <= tune.WAVE_DISTANCE_PX:
            self.y = self._ground
            self._begin_wave()

    def _step_chasing(self, dt: float) -> None:
        """يجري خلف المؤشر؛ إذا أمسكه (قريبًا 0.4 s) يفرح بنطتين."""
        pointer = self._pointer
        if (
            not pointer.present
            or self._timer > tune.CHASE_MAX_S
            or not in_play_zone(pointer, self._ground)
        ):
            self._next_behaviour()
            return
        remaining = self._move_toward(pointer.x, self._chase_speed, dt, rate=1.6)
        self._chase_near = self._chase_near + dt if remaining <= tune.CHASE_CATCH_PX else 0.0
        if self._chase_near >= tune.CHASE_CATCH_S:
            self._play_window = 0.0
            self.y = self._ground
            self._begin_hops()

    def _step_petted(self, dt: float) -> None:
        """يستمتع بالتمسيح؛ المسح المستمر يمدّد الوقت (حتى 8 s) ثم ينط فرحًا."""
        pointer = self._pointer
        if pointer.present and pointer.inside and pointer.speed > tune.PET_KEEP_SPEED_PX_S:
            self._duration = min(max(self._duration, self._timer + tune.PET_HOLD_S), tune.PET_MAX_S)
        if self._timer >= self._duration:
            self._begin_hops()

    def _step_crouching(self, dt: float) -> None:
        """Anticipation ثم إقلاع بالسرعة المخطط لها (قفزة كبيرة أو نطة)."""
        if self._timer < self._crouch_s:
            return
        v0 = self._pending_v0
        vx = 0.0
        if abs(v0) >= abs(JUMP_V0_PX_S):  # قفزة كبيرة: تقدّم أفقي صغير بعيدًا عن الحافة
            near_edge = self.width_px * 2.0
            if (self.facing > 0 and self.x > self._right - near_edge) or (
                self.facing < 0 and self.x < self._left + near_edge
            ):
                self.facing = -self.facing
            vx = self.facing * tune.HOP_VX_PX_S
        self._launch(v0, vx, _S.JUMPING)

    def _step_flight(self, dt: float) -> None:
        """يطير تحليليًا؛ عند انتهاء الزمن يهبط تمامًا على الأرض ويبدأ منحنى الهبوط."""
        t = self._timer
        total = flight_time(self.jump_v0)
        if t >= total:
            self.x = self._jump_x0 + self._jump_vx * total
            self.y = self._ground
            self._set_state(_S.LANDING)
            self._timer = t - total  # بقية الإطار تدخل في منحنى الهبوط
            return
        self.y = self._jump_y0 + jump_offset(t, self.jump_v0)
        self.x = self._jump_x0 + self._jump_vx * t

    def _step_landing(self, dt: float) -> None:
        if self._timer < LANDING_S:
            return
        if self._after_landing == AFTER_SHIVER:
            self._after_landing = AFTER_NORMAL
            self._begin_timed(_S.SHIVERING, "shiver")
        elif self._hops_left > 0:
            self._start_hop()
        else:
            self._next_behaviour()

    def _step_exiting(self, dt: float) -> None:
        self._advance_walk(dt, self._speed)
        margin = self.width_px
        if self.x <= self._left - margin or self.x >= self._right + margin:
            self._hide()
            self._schedule_next()
