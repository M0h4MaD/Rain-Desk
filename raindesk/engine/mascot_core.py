"""raindesk/engine/mascot_core.py

الغرض: نواة Drip: الحقول والواجهة العامة والجدولة والنظر والرمش وتطبيق الهيئة، بلا سلوكات.
المسؤوليات: الخصائص العامة التي يقرؤها المرسِم، وconfigure وset_stage وset_pointer وset_weather
    وstartle، وجدولة الظهور (Exp بمتوسط يتبع frequency)، والإخفاء والبدء، ونظرة العينين
    (المؤشر أو الرياح)، والرمش العشوائي، ونسخ الهيئة من mascot_pose إلى السمات العامة.
الاعتماديات: engine.mascot_pose وengine.mascot_pointer وengine.math_utils والمكتبة القياسية.
النمط التصميمي: Template (القاعدة تعرّف الهيكل، والصنف Mascot في mascot.py يضيف السلوكات).
ملاحظات: الثوابت (invariants): x في [left - width, right + width]؛ |scale_x| * scale_y = 1 خارج
    SPINNING؛ facing هو +1 أو -1. فُصلت عن mascot.py كي يبقى كل ملف قريبًا من 350 سطرًا.
مثال: انظر mascot.py (Mascot ترث MascotCore).
"""

from __future__ import annotations

import math
import random
from typing import Final

from raindesk.engine.mascot_pointer import PointerTracker
from raindesk.engine.mascot_pose import (
    ARM_REST_DEG,
    BLINK_S,
    JUMP_V0_PX_S,
    STEP_HZ,
    Effect,
    Expression,
    MascotState,
    blink_amount,
    compute_pose,
)
from raindesk.engine.math_utils import clamp, exp_smooth, lerp

_S = MascotState

BASE_HEIGHT_PX: Final[float] = 44.0  # px: ارتفاع الجسم عند mascot_scale = 1
BODY_WIDTH_RATIO: Final[float] = 0.92  # عرض القطرة نسبة إلى ارتفاعها (يطابق المرسِم)
_MEAN_GAP_RARE_S: Final[float] = 240.0  # s: متوسط الغياب عند frequency = 0
_MEAN_GAP_OFTEN_S: Final[float] = 45.0  # s: متوسط الغياب عند frequency = 1
_MIN_GAP_S: Final[float] = 20.0  # s: أقصر غياب بين ظهورين
_SPEED_PX_S: Final[tuple[float, float]] = (70.0, 110.0)  # px/s: سرعة المشي لكل ظهور
_VISIBLE_S: Final[tuple[float, float]] = (12.0, 35.0)  # s: زمن الظهور قبل بدء الخروج
_STAGE_SKIP: Final[float] = 400.0  # px: أضيق مسرح يسمح بالظهور
_STAGE_RETRY_S: Final[float] = 5.0  # s: إعادة المحاولة إن كان المسرح ضيقًا
_LOOK_TAU_S: Final[float] = 0.3  # s: تنعيم نظرة الرياح
_LOOK_FAST_TAU_S: Final[float] = 0.12  # s: تنعيم نظرة المؤشر (أسرع كي يبدو منتبهًا)
_LOOK_RADIUS_PX: Final[float] = 520.0  # px: ينظر إلى المؤشر ضمن هذا المدى
_LOOK_SCALE_PX: Final[float] = 240.0  # px: الإزاحة التي تعطي أقصى نظرة
_BLINK_GAP_S: Final[tuple[float, float]] = (1.8, 5.0)  # s: بين الرمشات
_DOUBLE_BLINK_CHANCE: Final[float] = 0.2
_DOUBLE_BLINK_GAP_S: Final[float] = 0.12
AFTER_SHIVER: Final[str] = "shiver"
AFTER_NORMAL: Final[str] = "behaviour"
_MOVING: Final[frozenset[MascotState]] = frozenset(
    {
        _S.ENTERING,
        _S.WALKING,
        _S.EXITING,
        _S.CURIOUS,
        _S.CHASING,
    }
)


class MascotCore:
    """Drip: الحالة الحالية تُقرأ من الخصائص العامة ويرسمها mascot_painter.

    السمات العامة: state وx وy وfacing وscale_x وscale_y وlook_dir وlook_y وexpression وeffect
        وeffect_t وblink وmouth_open وarm_l وarm_r وfoot_phase وgait وjump_v0.
    الثوابت (invariants): x في [left - width, right + width]؛ |scale_x| * scale_y = 1 خارج
        SPINNING؛ facing هو +1 أو -1؛ لا شيء يتغير إن كان غير مفعّل ولا كلفة له.
    التعقيد: step هو O(1). سلامة الخيوط: خيط الواجهة فقط. النمط: State + Scheduler.
    """

    def __init__(self, rng: random.Random) -> None:
        """rng مُحقَن (كل العشوائية منه فالتشغيل حتمي بالبذرة)."""
        self._rng = rng
        self.state = _S.HIDDEN
        self.x = self.y = 0.0
        self.facing = 1
        self.scale_x = self.scale_y = 1.0
        self.look_dir = self.look_y = 0.0
        self.expression = Expression.NEUTRAL
        self.effect = Effect.NONE
        self.effect_t = 0.0  # s: عمر المؤثر (زمن الحالة) لتحريكه في المرسِم
        self.blink = 0.0
        self.mouth_open = 0.0
        self.arm_l = self.arm_r = ARM_REST_DEG
        self.foot_phase = 0.0  # راديان: طور القدمين
        self.gait = 0.0  # 1 أثناء المشي والجري وإلا 0
        self.jump_v0 = JUMP_V0_PX_S  # سرعة إقلاع آخر قفزة (لحساب ذروتها)
        self._enabled = False
        self._frequency = 0.4
        self._scale = 1.0
        self._left = self._right = self._ground = 0.0
        self._timer = self._hidden_left = self._appeared = self._budget = 0.0
        self._duration = self._phase = 0.0
        self._speed = _SPEED_PX_S[0]
        self._target_x = self._chase_speed = self._chase_near = 0.0
        self._jump_x0 = self._jump_y0 = self._jump_vx = 0.0
        self._pending_v0 = JUMP_V0_PX_S
        self._crouch_s = 0.12
        self._hops_left = 0
        self._after_landing = AFTER_NORMAL
        self._pointer = PointerTracker()
        self._pointer_pos: tuple[float, float] | None = None
        self._rain = 0.0
        self._startle_pending = False
        self._cd_chase = self._cd_curious = self._cd_startle = self._play_window = 0.0
        self._blink_in = rng.uniform(*_BLINK_GAP_S)
        self._blink_t = -1.0
        self._blink_value = 0.0

    # ------------------------------------------------------------------ الواجهة
    @property
    def visible(self) -> bool:
        """True ما دامت الشخصية ليست HIDDEN."""
        return self.state is not _S.HIDDEN

    @property
    def height_px(self) -> float:
        """ارتفاع الجسم الفعلي بالبكسل المنطقي (44 * scale)."""
        return BASE_HEIGHT_PX * self._scale

    @property
    def width_px(self) -> float:
        """عرض الجسم الفعلي (يحدد هامش الدخول والخروج)."""
        return self.height_px * BODY_WIDTH_RATIO

    @property
    def ground_y(self) -> float:
        """مستوى الأرض الحالي (للظل في المرسِم)."""
        return self._ground

    def configure(self, enabled: bool, frequency: float, scale: float) -> None:
        """يضبط التفعيل والتكرار (0..1) والحجم (0.5..2).

        التعطيل يخفيها فورًا. إعادة التفعيل أو تغيير التكرار وهي مخفية تسحب زمن ظهور جديدًا.
        """
        frequency = clamp(frequency, 0.0, 1.0)
        self._scale = clamp(scale, 0.5, 2.0)
        if not enabled:
            self._enabled = False
            self._hide()
            return
        changed = not self._enabled or frequency != self._frequency
        self._enabled = True
        self._frequency = frequency
        if changed and self.state is _S.HIDDEN:
            self._schedule_next()

    def set_stage(self, left: float, right: float, ground_y: float) -> None:
        """يحدد المسرح: حدا الحركة الأفقي ومستوى الأرض (أسفل منطقة العمل)."""
        self._left, self._right, self._ground = left, max(left, right), ground_y
        if self.visible:
            self._clamp_x()

    def set_pointer(self, position: tuple[float, float] | None) -> None:
        """موضع المؤشر بإحداثيات النافذة (None = خارجها أو على شاشة أخرى)؛ للقراءة فقط."""
        self._pointer_pos = position

    def set_weather(self, rain: float) -> None:
        """شدة المطر 0..1: تفتح فمه لالتقاط القطرات وتجعله يرتجف في العواصف."""
        self._rain = clamp(rain, 0.0, 1.0)

    def startle(self) -> None:
        """يفزعه حدث خارجي (برق): قفزة فزع من الحالات الهادئة؛ يُتجاهل إن كان مخفيًا."""
        if self.visible and self._cd_startle <= 0.0:
            self._startle_pending = True

    # ------------------------------------------------------------------ الجدولة والإظهار
    def _schedule_next(self) -> None:
        """يسحب زمن الظهور التالي: max(20, Exp(mean = lerp(240, 45, frequency)))."""
        mean = lerp(_MEAN_GAP_RARE_S, _MEAN_GAP_OFTEN_S, self._frequency)
        self._hidden_left = max(_MIN_GAP_S, self._rng.expovariate(1.0 / mean))

    def _hide(self) -> None:
        self.state = _S.HIDDEN
        self.scale_x = self.scale_y = 1.0
        self.expression, self.effect = Expression.NEUTRAL, Effect.NONE
        self.blink = self.mouth_open = self.gait = 0.0
        self.arm_l = self.arm_r = ARM_REST_DEG
        self._timer = self._appeared = 0.0
        self._startle_pending = False
        self._pointer.reset()
        self._clamp_x()  # الثابت (x داخل المسرح + العرض) يسري حتى وهي مخفية

    def _step_hidden(self, dt: float) -> None:
        self._hidden_left -= dt
        if self._hidden_left > 0.0:
            return
        if self._right - self._left < _STAGE_SKIP:
            self._hidden_left = _STAGE_RETRY_S  # مسرح ضيق أو لم يُضبط بعد
            return
        side = self._rng.choice((-1, 1))  # يدخل من اليسار (-1) أو اليمين (+1)
        self.facing = -side
        self.x = self._left - self.width_px if side < 0 else self._right + self.width_px
        self.y = self._ground
        self._speed = self._rng.uniform(*_SPEED_PX_S)
        self._budget = self._rng.uniform(*_VISIBLE_S)
        self._appeared = self._phase = 0.0
        self._cd_chase = self._cd_curious = self._play_window = 0.0
        self._cd_startle = 0.0
        self._set_state(_S.ENTERING)

    def _set_state(self, state: MascotState) -> None:
        self.state = state
        self._timer = 0.0
        self.scale_x = self.scale_y = 1.0

    # ------------------------------------------------------------------ النظر والرمش والهيئة
    def _update_look(self, dt: float, wind_sign: float) -> None:
        """النظر: إلى المؤشر القريب وإلا نحو الرياح؛ إلى الأعلى في LOOK_UP؛ للأمام نائمًا."""
        pointer = self._pointer
        target_x, target_y, tau = clamp(wind_sign, -1.0, 1.0), 0.0, _LOOK_TAU_S
        if pointer.present and pointer.dist <= _LOOK_RADIUS_PX and self.state is not _S.SLEEPING:
            target_x = clamp(pointer.dx / _LOOK_SCALE_PX, -1.0, 1.0)
            target_y = clamp(pointer.dy / _LOOK_SCALE_PX, -1.0, 1.0)
            tau = _LOOK_FAST_TAU_S
        if self.state is _S.LOOK_UP:
            target_y = -1.0
        self.look_dir = exp_smooth(self.look_dir, target_x, dt, tau)
        self.look_y = exp_smooth(self.look_y, target_y, dt, tau)

    def _update_blink(self, dt: float) -> None:
        """رمشة عشوائية كل 1.8-5 s، وأحيانًا مزدوجة (20%)."""
        if self._blink_t >= 0.0:
            self._blink_t += dt
            self._blink_value = blink_amount(self._blink_t)
            if self._blink_t >= BLINK_S:
                self._blink_t = -1.0
                double = self._rng.random() < _DOUBLE_BLINK_CHANCE
                self._blink_in = _DOUBLE_BLINK_GAP_S if double else self._rng.uniform(*_BLINK_GAP_S)
            return
        self._blink_value = 0.0
        self._blink_in -= dt
        if self._blink_in <= 0.0:
            self._blink_t = 0.0

    def _apply_pose(self) -> None:
        """ينسخ الهيئة المحسوبة إلى السمات العامة (scale_x = turn / scale_y يحفظ المساحة)."""
        pose = compute_pose(
            self.state, self._timer, self._duration, self._phase, self._rain, self.jump_v0
        )
        self.scale_y = pose.scale_y
        self.scale_x = pose.turn / pose.scale_y
        self.arm_l, self.arm_r = pose.arm_l, pose.arm_r
        self.mouth_open, self.expression = pose.mouth_open, pose.expression
        self.effect = pose.effect
        self.blink = max(self._blink_value, pose.eyes_closed)
        self.effect_t = self._timer
        self.gait = 1.0 if self.state in _MOVING else 0.0
        self.foot_phase = math.pi * STEP_HZ * self._phase

    def _clamp_x(self) -> None:
        margin = self.width_px
        self.x = clamp(self.x, self._left - margin, self._right + margin)
