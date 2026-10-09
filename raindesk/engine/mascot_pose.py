"""raindesk/engine/mascot_pose.py

الغرض: طبقة الحركة (Pose) لـ Drip: تعدّد الحالات والتعابير والمؤثرات، وتحسب هيئة الجسم
    (ضغط/تمدد، الذراعان، الفم، التعبير) كدالة نقية من الحالة وزمنها، بلا Qt ولا عشوائية.
المسؤوليات: MascotState وExpression وEffect وPose، ومنحنيات الحركة: هبوط مهتز مخمَّد،
    تهيؤ القفز، تمدد الطيران، تنفس، اهتزاز، رقص، إغفاءة، تلويح، دوران، ارتجاف، وغمزة العين.
الاعتماديات: raindesk.core.constants (GRAVITY_PX_S2) وengine.math_utils والمكتبة القياسية.
النمط التصميمي: Strategy بالدوال (كل حالة تُترجم إلى Pose)، وفصل المنطق (mascot.py) عن الحركة.
ملاحظات أكاديمية: مبادئ Lasseter (1987) "Principles of Traditional Animation Applied to 3D
    Computer Animation": Anticipation (ضغط ما قبل القفز وانحناءة التهيؤ)، وSquash and Stretch
    (scale_x * scale_y = 1 حفظًا للمساحة)، وFollow-through (الهبوط s(t) = 1 - A*exp(-t/0.10)*
    cos(2*pi*t/0.22) يتجاوز ثم يستقر)، وSecondary Action (الذراعان والعينان والفم تتحرك
    مع الحركة الرئيسية)، وAppeal (ملامح كبيرة ومستديرة). القفزة تحليلية y = v0*t + g*t^2/2.
مثال: pose = compute_pose(MascotState.WAVING, t=0.4, duration=2.0, phase=0.0, rain=0.5, v0=-520)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from raindesk.core.constants import GRAVITY_PX_S2
from raindesk.engine.math_utils import clamp, ease_in_out_cubic, lerp


class MascotState(StrEnum):
    """حالات Drip: الأساسية العشر ثم حالات الشخصية والتفاعل مع المؤشر."""

    HIDDEN = "hidden"
    ENTERING = "entering"
    WALKING = "walking"
    IDLE = "idle"
    LOOK_UP = "look_up"
    CROUCHING = "crouching"
    JUMPING = "jumping"
    LANDING = "landing"
    SHAKING = "shaking"
    EXITING = "exiting"
    DANCING = "dancing"
    SLEEPING = "sleeping"
    WAVING = "waving"
    SPINNING = "spinning"
    SHIVERING = "shivering"
    CURIOUS = "curious"
    CHASING = "chasing"
    PETTED = "petted"
    STARTLED = "startled"


class Expression(StrEnum):
    """تعبيرات الوجه التي يرسمها المرسِم."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    SURPRISED = "surprised"
    SCARED = "scared"
    SLEEPY = "sleepy"
    LOVE = "love"


class Effect(StrEnum):
    """مؤثرات صغيرة تطفو فوق الرأس (يحركها effect_t في المرسِم)."""

    NONE = "none"
    HEARTS = "hearts"
    SWEAT = "sweat"
    ALERT = "alert"
    ZZZ = "zzz"
    SPARKLE = "sparkle"


# ---------------------------------------------------------------------------
# ثوابت الحركة
# ---------------------------------------------------------------------------
JUMP_V0_PX_S: Final[float] = -520.0  # px/s: القفزة الكبيرة (ذروتها 75 px)
HOP_V0_PX_S: Final[float] = -280.0  # px/s: نطة الفرح الصغيرة (ذروتها نحو 22 px)
STARTLE_V0_PX_S: Final[float] = -340.0  # px/s: قفزة الفزع
CROUCH_S: Final[float] = 0.12  # s: زمن التهيؤ (anticipation)
CROUCH_SCALE_Y: Final[float] = 0.8  # أدنى scale_y عند نهاية التهيؤ
LANDING_S: Final[float] = 0.8  # s: مدة LANDING (الانحراف المتبقي 0.28*exp(-8) < 1e-4)
ARM_REST_DEG: Final[float] = 12.0  # درجة عن وضع التدلي (موجب = يبتعد/يرتفع)
_STRETCH_MAX: Final[float] = 0.12  # أقصى تمدد رأسي أثناء الطيران السريع
_TAKEOFF_BLEND_S: Final[float] = 0.08  # s: انتقال scale_y من الضغط إلى التمدد عند الإقلاع
_SQUASH_AMPLITUDE: Final[float] = 0.28  # سعة اهتزاز الهبوط للقفزة الكبيرة
_SQUASH_TAU_S: Final[float] = 0.10  # s: ثابت اضمحلال الاهتزاز
_SQUASH_PERIOD_S: Final[float] = 0.22  # s: دورة الاهتزاز
_MIN_SQUASH_RATIO: Final[float] = 0.4  # النطات الصغيرة تهبط بنسبة من الضغط الكامل على الأقل
_SHAKE_HZ: Final[float] = 12.0
_SHAKE_AMPLITUDE: Final[float] = 0.12
_BREATH_HZ: Final[float] = 0.5  # Hz: تنفس الوقوف
_BREATH_AMPLITUDE: Final[float] = 0.025
_DOZE_HZ: Final[float] = 0.3  # Hz: تنفس النوم البطيء
_DOZE_AMPLITUDE: Final[float] = 0.03
_YAWN_S: Final[float] = 1.0  # s: مدة التثاؤب في بداية SLEEPING
_YAWN_ARMS_DEG: Final[float] = 140.0  # تمطّي الذراعين أثناء التثاؤب
_DANCE_HZ: Final[float] = 2.2  # نبضة في الثانية
_DANCE_SQUASH: Final[float] = 0.07
_DANCE_ARM_MID_DEG: Final[float] = 65.0
_DANCE_ARM_SWING_DEG: Final[float] = 45.0
_WAVE_BASE_DEG: Final[float] = 135.0
_WAVE_SWING_DEG: Final[float] = 25.0
_WAVE_HZ: Final[float] = 3.0
_WALK_ARM_SWING_DEG: Final[float] = 24.0
_STEP_HZ: Final[float] = 2.2  # خطوة في الثانية (الأذرع والقدمان والارتداد)
_SHIVER_HZ: Final[float] = 22.0
_SHIVER_AMPLITUDE: Final[float] = 0.035
_PET_WIGGLE_HZ: Final[float] = 6.0
_PET_WIGGLE_AMPLITUDE: Final[float] = 0.05
_CATCH_RAIN_MIN: Final[float] = 0.3  # شدة مطر تجعله يفتح فمه ويلتقط القطرات
_BLINK_S: Final[float] = 0.14  # s: مدة الرمشة
_MIN_TURN: Final[float] = 0.14  # أقل عرض نسبي أثناء الدوران (شريحة رفيعة بدل الاختفاء)
_TWO_PI: Final[float] = 2.0 * math.pi

STEP_HZ: Final[float] = _STEP_HZ


@dataclass(slots=True)
class Pose:
    """هيئة الجسم في لحظة: ما يحتاجه المرسِم بعد الموضع (x, y) والاتجاه.

    الحقول: scale_y (الضغط/التمدد)، turn (عامل الدوران الأفقي في [-1, 1]، 1 = أمامي)،
        arm_l وarm_r بالدرجات، mouth_open في [0, 1]، eyes_closed في [0, 1]، التعبير والمؤثر.
    """

    scale_y: float = 1.0
    turn: float = 1.0
    arm_l: float = ARM_REST_DEG
    arm_r: float = ARM_REST_DEG
    mouth_open: float = 0.0
    eyes_closed: float = 0.0
    expression: Expression = Expression.NEUTRAL
    effect: Effect = Effect.NONE


def flight_time(v0: float) -> float:
    """زمن طيران قفزة بسرعة إقلاع v0 (سالبة للأعلى): 2*|v0|/g ثانية."""
    return 2.0 * abs(v0) / GRAVITY_PX_S2


def jump_offset(t: float, v0: float) -> float:
    """إزاحة رأسية (للأسفل موجبة) بعد t ثانية من الإقلاع: v0*t + g*t^2/2 (ذروتها سالبة)."""
    return v0 * t + 0.5 * GRAVITY_PX_S2 * t * t


def landing_scale(t: float, v0: float = JUMP_V0_PX_S) -> float:
    """s(t) = 1 - A*exp(-t/0.10)*cos(2*pi*t/0.22)؛ A = 0.28 للقفزة الكبيرة وأقل للنطات.

    scale_y = s وscale_x = 1/s فتُحفظ المساحة. الاهتزاز مخمَّد فيعود إلى 1 خلال أقل من ثانية.
    """
    ratio = clamp(abs(v0) / abs(JUMP_V0_PX_S), _MIN_SQUASH_RATIO, 1.0)
    return 1.0 - _SQUASH_AMPLITUDE * ratio * math.exp(-t / _SQUASH_TAU_S) * math.cos(
        _TWO_PI * t / _SQUASH_PERIOD_S
    )


def crouch_scale(t: float, duration: float) -> float:
    """Anticipation: يضغط الجسم من 1 إلى 0.8 بمنحنى slow-in/slow-out خلال duration."""
    progress = clamp(t / max(duration, 1e-6), 0.0, 1.0)
    return lerp(1.0, CROUCH_SCALE_Y, ease_in_out_cubic(progress))


def flight_scale(t: float, v0: float) -> float:
    """تمدد الطيران: يزداد مع |vy|، وينتقل من ضغط الإقلاع إلى التمدد خلال 80 ms."""
    speed = abs(v0 + GRAVITY_PX_S2 * t)
    stretched = 1.0 + _STRETCH_MAX * min(1.0, speed / abs(v0))
    blend = ease_in_out_cubic(clamp(t / _TAKEOFF_BLEND_S, 0.0, 1.0))
    return lerp(CROUCH_SCALE_Y, stretched, blend)


def blink_amount(t: float) -> float:
    """منحنى رمشة مثلثي: 0 -> 1 -> 0 خلال 0.14 s (t بالثواني منذ بدء الرمشة)."""
    if t < 0.0 or t >= _BLINK_S:
        return 0.0
    return 1.0 - abs(2.0 * t / _BLINK_S - 1.0)


BLINK_S: Final[float] = _BLINK_S


def _walk_arms(phase: float, amplitude: float = _WALK_ARM_SWING_DEG) -> tuple[float, float]:
    """ذراعان تتأرجحان بعكس بعضهما مع الخطوات."""
    swing = amplitude * math.sin(math.pi * _STEP_HZ * phase)
    return ARM_REST_DEG + swing, ARM_REST_DEG - swing


def compute_pose(
    state: MascotState, t: float, duration: float, phase: float, rain: float, v0: float
) -> Pose:
    """الهيئة لحالة معيّنة بعد t ثانية من دخولها (دالة نقية بلا عشوائية).

    Args:
        state: الحالة. t: زمن الحالة. duration: مدتها المخططة (للمنحنيات المعتمدة على التقدم).
        phase: طور الخطوات المتراكم (للذراعين). rain: شدة المطر 0..1. v0: سرعة آخر إقلاع.
    """
    pose = Pose()
    if state in (
        MascotState.ENTERING,
        MascotState.WALKING,
        MascotState.EXITING,
        MascotState.CURIOUS,
    ):
        pose.arm_l, pose.arm_r = _walk_arms(phase)
    elif state is MascotState.CHASING:
        pose.arm_l, pose.arm_r = _walk_arms(phase, _WALK_ARM_SWING_DEG * 1.6)
        pose.expression, pose.mouth_open = Expression.HAPPY, 0.5
    elif state is MascotState.IDLE:
        pose.scale_y = 1.0 + _BREATH_AMPLITUDE * math.sin(_TWO_PI * _BREATH_HZ * t)
    elif state is MascotState.LOOK_UP and rain >= _CATCH_RAIN_MIN:
        pose.mouth_open, pose.expression, pose.effect = 0.7, Expression.HAPPY, Effect.SPARKLE
    elif state is MascotState.CROUCHING:
        pose.scale_y = crouch_scale(t, duration)
        pose.arm_l = pose.arm_r = 4.0
    elif state is MascotState.JUMPING:
        pose.scale_y = flight_scale(t, v0)
        pose.arm_l = pose.arm_r = 105.0
        pose.mouth_open, pose.expression = 0.5, Expression.HAPPY
    elif state is MascotState.LANDING:
        pose.scale_y = landing_scale(t, v0)
        pose.expression, pose.mouth_open = Expression.HAPPY, 0.25
    elif state is MascotState.STARTLED:
        pose.scale_y = flight_scale(t, v0)
        pose.arm_l = pose.arm_r = 150.0
        pose.mouth_open, pose.expression, pose.effect = 0.8, Expression.SURPRISED, Effect.ALERT
    elif state is MascotState.SHAKING:
        envelope = math.sin(math.pi * clamp(t / max(duration, 1e-6), 0.0, 1.0))
        pose.scale_y = 1.0 + _SHAKE_AMPLITUDE * envelope * math.sin(_TWO_PI * _SHAKE_HZ * t)
        pose.arm_l = pose.arm_r = 40.0
        pose.effect = Effect.SPARKLE  # رذاذ الماء المنتفض
    elif state is MascotState.DANCING:
        pose.scale_y = 1.0 - _DANCE_SQUASH * abs(math.sin(math.pi * _DANCE_HZ * t))
        swing = _DANCE_ARM_SWING_DEG * math.sin(math.pi * _DANCE_HZ * t)
        pose.arm_l, pose.arm_r = _DANCE_ARM_MID_DEG + swing, _DANCE_ARM_MID_DEG - swing
        pose.mouth_open, pose.expression = 0.4, Expression.HAPPY
    elif state is MascotState.SLEEPING:
        pose.eyes_closed, pose.expression = 1.0, Expression.SLEEPY
        if t < _YAWN_S:  # تثاؤب: يفتح الفم ويتمطّى ثم ينام
            yawn = math.sin(math.pi * t / _YAWN_S)
            pose.mouth_open = yawn
            pose.arm_l = pose.arm_r = ARM_REST_DEG + (_YAWN_ARMS_DEG - ARM_REST_DEG) * yawn
        else:
            pose.effect = Effect.ZZZ
            pose.scale_y = 1.0 + _DOZE_AMPLITUDE * math.sin(_TWO_PI * _DOZE_HZ * (t - _YAWN_S))
    elif state is MascotState.WAVING:
        pose.arm_r = _WAVE_BASE_DEG + _WAVE_SWING_DEG * math.sin(_TWO_PI * _WAVE_HZ * t)
        pose.mouth_open, pose.expression = 0.35, Expression.HAPPY
    elif state is MascotState.SPINNING:
        spin = math.cos(_TWO_PI * clamp(t / max(duration, 1e-6), 0.0, 1.0))
        pose.turn = math.copysign(max(abs(spin), _MIN_TURN), spin)  # لا يختفي أثناء الدوران
        pose.arm_l = pose.arm_r = 85.0
        pose.mouth_open, pose.expression = 0.4, Expression.HAPPY
    elif state is MascotState.SHIVERING:
        pose.scale_y = 1.0 + _SHIVER_AMPLITUDE * math.sin(_TWO_PI * _SHIVER_HZ * t)
        pose.arm_l = pose.arm_r = 20.0
        pose.mouth_open = 0.2 + 0.1 * math.sin(_TWO_PI * _SHIVER_HZ * t)
        pose.expression, pose.effect = Expression.SCARED, Effect.SWEAT
    elif state is MascotState.PETTED:
        pose.scale_y = 1.0 + _PET_WIGGLE_AMPLITUDE * math.sin(_TWO_PI * _PET_WIGGLE_HZ * t)
        pose.arm_l = pose.arm_r = 38.0
        pose.mouth_open, pose.expression, pose.effect = 0.3, Expression.LOVE, Effect.HEARTS
    return pose
