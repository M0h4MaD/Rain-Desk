"""raindesk/engine/mascot_pointer.py

الغرض: يحوّل موضع مؤشر الفأرة (عينات متقطعة) إلى إشارات تفاعل لـ Drip: القرب، والسرعة،
    والاقتراب، والسكون، والتمسيح (تحريك المؤشر ذهابًا وإيابًا فوق الجسم).
المسؤوليات: تنعيم السرعة، وكشف القفز المفاجئ (انتقال بين الشاشات)، وعدّ انعكاسات الاتجاه
    داخل صندوق الجسم، وتقديم خصائص قراءة فقط. لا يقرأ الفأرة بنفسه (يُحقن الموضع) فيبقى
    نقيًا وقابلًا للاختبار بلا Qt. لا يعترض أي مدخلات: النافذة تبقى click-through.
الاعتماديات: raindesk.engine.math_utils والمكتبة القياسية.
النمط التصميمي: Observer-less Tracker (حالة صغيرة تُحدَّث كل إطار وتُستعلَم).
    pick_reaction: دالة نقية تختار رد فعل Drip من إشارات المؤشر (التمسيح ثم الفزع ثم المطاردة
    ثم الفضول) وتترك سحب الاحتمال والتبريد لـ Mascot.
ملاحظات: التمسيح = 3 انعكاسات أفقية أو أكثر خلال 1.6 s داخل الصندوق، بين كل انعكاسين مسافة
    لا تقل عن 14 px (يتجاهل الارتعاش الصغير). السرعة مُنعَّمة أسّيًا (tau = 60 ms).
مثال: tracker.update(dt, (x, y), cx=100, bottom=1040, width=40, height=44); tracker.petting
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Final

from raindesk.engine.math_utils import exp_smooth

_VELOCITY_TAU_S: Final[float] = 0.06  # s: تنعيم السرعة
_TELEPORT_PX: Final[float] = 600.0  # px: قفزة أكبر بين عينتين تُعدّ انتقالًا لا حركة
_STILL_SPEED_PX_S: Final[float] = 40.0  # px/s: دون هذا يُعدّ المؤشر ساكنًا
_HIT_HALF_WIDTH: Final[float] = 0.65  # نصف عرض صندوق اللمس نسبة إلى عرض الجسم
_HIT_TOP: Final[float] = 1.15  # أعلى الصندوق نسبة إلى ارتفاع الجسم فوق القدم
_HIT_BELOW_PX: Final[float] = 8.0  # px: تسامح تحت القدم (الظل)
_PET_MIN_SPEED: Final[float] = 80.0  # px/s: أدنى سرعة أفقية تُحسب حركة تمسيح
_PET_MIN_TRAVEL_PX: Final[float] = 14.0  # px: أقل مسافة بين انعكاسين
_PET_WINDOW_S: Final[float] = 1.6  # s: نافذة عدّ الانعكاسات
_PET_REVERSALS: Final[int] = 3  # عدد الانعكاسات المطلوب
_PET_HISTORY: Final[int] = 8  # أقصى طوابع زمنية محفوظة


class PointerTracker:
    """يتتبع المؤشر نسبةً إلى جسم Drip؛ يُحدَّث مرة كل إطار ثم تُقرأ خصائصه.

    الثوابت (invariants): القيم المشتقة (dist وapproach وغيرها) معرّفة فقط حين present = True.
    التعقيد: update هو O(1) (القائمة الزمنية محدودة بـ 8). سلامة الخيوط: خيط الواجهة.
    """

    def __init__(self) -> None:
        self.present = False
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.dx = 0.0  # px: x المؤشر ناقص مركز الجسم
        self.dy = 0.0  # px: y المؤشر ناقص منتصف الجسم (موجب = أسفل)
        self.dist = math.inf
        self.approach = 0.0  # px/s: سرعة الاقتراب من الجسم (موجبة = يقترب)
        self.inside = False
        self.still_time = 0.0  # s: مدة السكون المتواصل
        self._clock = 0.0
        self._last_sign = 0
        self._travel = 0.0
        self._stamps: list[float] = []

    @property
    def speed(self) -> float:
        """سرعة المؤشر المنعَّمة بالبكسل في الثانية."""
        return math.hypot(self.vx, self.vy)

    @property
    def reversals(self) -> int:
        """عدد انعكاسات التمسيح خلال النافذة الأخيرة."""
        return sum(1 for stamp in self._stamps if self._clock - stamp <= _PET_WINDOW_S)

    @property
    def petting(self) -> bool:
        """True إذا كان المستخدم يمسّح Drip الآن (داخل الصندوق وبانعكاسات كافية)."""
        return self.present and self.inside and self.reversals >= _PET_REVERSALS

    def reset(self) -> None:
        """ينسى المؤشر (مثلًا عند مغادرة الشاشة أو إخفاء الشخصية)."""
        self.present = False
        self.vx = self.vy = self.approach = 0.0
        self.dist = math.inf
        self.inside = False
        self.still_time = 0.0
        self._last_sign = 0
        self._travel = 0.0
        self._stamps.clear()

    def update(
        self,
        dt: float,
        pointer: tuple[float, float] | None,
        cx: float,
        bottom: float,
        width: float,
        height: float,
    ) -> None:
        """يحدّث الحالة بموضع المؤشر (None = غير متاح) وصندوق الجسم (cx مركزه، bottom قدمه)."""
        self._clock += dt
        if pointer is None or dt <= 0.0:
            if pointer is None:
                self.reset()
            return
        px, py = pointer
        if self.present and math.hypot(px - self.x, py - self.y) < _TELEPORT_PX:
            self.vx = exp_smooth(self.vx, (px - self.x) / dt, dt, _VELOCITY_TAU_S)
            self.vy = exp_smooth(self.vy, (py - self.y) / dt, dt, _VELOCITY_TAU_S)
            moved = px - self.x
        else:  # أول عينة أو انتقال مفاجئ: لا سرعة معروفة
            self.vx = self.vy = 0.0
            self._last_sign, self._travel, moved = 0, 0.0, 0.0
            self._stamps.clear()
        self.present, self.x, self.y = True, px, py
        self.dx = px - cx
        self.dy = py - (bottom - height / 2.0)
        self.dist = math.hypot(self.dx, self.dy)
        closing = -(self.dx * self.vx + self.dy * self.vy)
        self.approach = closing / self.dist if self.dist > 1.0 else 0.0
        self.inside = (
            abs(self.dx) <= _HIT_HALF_WIDTH * width
            and bottom - _HIT_TOP * height <= py <= bottom + _HIT_BELOW_PX
        )
        self.still_time = self.still_time + dt if self.speed < _STILL_SPEED_PX_S else 0.0
        self._track_petting(moved)

    def _track_petting(self, moved: float) -> None:
        """يعدّ انعكاسات الاتجاه الأفقي داخل الصندوق (مسافة دنيا بين الانعكاسين)."""
        if not self.inside or abs(self.vx) < _PET_MIN_SPEED:
            if not self.inside:
                self._last_sign, self._travel = 0, 0.0
            return
        sign = 1 if self.vx > 0 else -1
        self._travel += abs(moved)
        if self._last_sign != 0 and sign != self._last_sign and self._travel >= _PET_MIN_TRAVEL_PX:
            self._stamps.append(self._clock)
            del self._stamps[:-_PET_HISTORY]
            self._travel = 0.0
        if self._last_sign == 0 or sign != self._last_sign:
            self._last_sign = sign


# ---------------------------------------------------------------------------
# قرارات التفاعل
# ---------------------------------------------------------------------------
STARTLE_SPEED_PX_S: Final[float] = 1100.0  # px/s: اندفاع المؤشر الذي يفزعه
STARTLE_DIST_PX: Final[float] = 170.0  # px: لا يفزع إلا إن كان المؤشر قريبًا
CHASE_SPEED_PX_S: Final[float] = 250.0  # px/s: حركة مؤشر تدعوه للعب
CHASE_RANGE_PX: Final[float] = 520.0  # px: أبعد مسافة تُعدّ دعوة للعب
CURIOUS_RANGE_PX: Final[float] = 260.0  # px: المؤشر الساكن ضمن هذا المدى يثير فضوله
CURIOUS_DWELL_S: Final[float] = 1.0  # s: سكون المؤشر المطلوب قبل أن يقترب
PLAY_HEIGHT_PX: Final[float] = 340.0  # px: ارتفاع منطقة اللعب فوق الأرض (قرب شريط المهام)
PLAY_BELOW_PX: Final[float] = 80.0  # px: تسامح تحت الأرض (فوق شريط المهام نفسه)


class Reaction(StrEnum):
    """ردود فعل Drip تجاه المؤشر."""

    NONE = "none"
    PET = "pet"
    STARTLE = "startle"
    CHASE = "chase"
    CURIOUS = "curious"


def in_play_zone(pointer: PointerTracker, ground_y: float) -> bool:
    """True إذا كان المؤشر قرب خط الأرض (منطقة شريط المهام) حيث يلعب Drip."""
    return pointer.present and -PLAY_BELOW_PX <= ground_y - pointer.y <= PLAY_HEIGHT_PX


def pick_reaction(
    pointer: PointerTracker,
    ground_y: float,
    *,
    startle_ready: bool,
    chase_ready: bool,
    curious_ready: bool,
) -> Reaction:
    """يختار رد الفعل بالأولوية: تمسيح > فزع (اندفاع قريب) > مطاردة > فضول.

    التبريد (cooldown) يحدده المستدعي عبر *_ready. المطاردة والفضول يشترطان منطقة اللعب فلا
    يتحرك Drip إن كان مؤشرك يعمل في أعلى الشاشة.
    """
    if not pointer.present:
        return Reaction.NONE
    if pointer.petting:
        return Reaction.PET
    approaching = pointer.approach > 0.6 * pointer.speed
    if (
        startle_ready
        and pointer.speed > STARTLE_SPEED_PX_S
        and pointer.dist < STARTLE_DIST_PX
        and approaching
    ):
        return Reaction.STARTLE
    if not in_play_zone(pointer, ground_y):
        return Reaction.NONE
    if chase_ready and pointer.speed >= CHASE_SPEED_PX_S and pointer.dist <= CHASE_RANGE_PX:
        return Reaction.CHASE
    if curious_ready and pointer.dist <= CURIOUS_RANGE_PX and pointer.still_time >= CURIOUS_DWELL_S:
        return Reaction.CURIOUS
    return Reaction.NONE
