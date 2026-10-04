"""raindesk/engine/splash_system.py

الغرض: رذاذ الهبوط: تموّجات إهليلجية (ripples) وجسيمات رذاذ (sprays) عند ارتطام القطرات.
المسؤوليات: توليد الرذاذ احتماليًا من نقاط الهبوط، وتقدّم الجسيمات بالفيزياء البسيطة، وتصدير
    مصفوفات جاهزة للرسم، ضمن حوض ثابت السعة بلا حجز ذاكرة كبير لكل إطار.
الاعتماديات: NumPy وraindesk.core.constants وraindesk.engine.math_utils.
النمط التصميمي: Object Pool على شكل ring buffer بتخطيط SoA (انظر DD-04).
ملاحظات: حوضان منفصلان (ripples وsprays) لكل منهما سعة 'capacity'؛ عند الامتلاء يُستبدل الأقدم.
    الإحداثيات بالبكسل المنطقي، y للأسفل. كل العشوائية من الـ Generator الممرَّر.
مثال: splashes.spawn(field.drain_landings(), 0.5); splashes.step(dt); data = splashes.ripples()
"""

from __future__ import annotations

from typing import Final

import numpy as np

from raindesk.core.constants import GRAVITY_PX_S2, SPLASH_POOL_CAPACITY
from raindesk.engine.math_utils import clamp

# --- التموّج (ripple) ---
_RIPPLE_R0_PX: Final[float] = 2.0  # px: نصف القطر الأفقي الابتدائي
_RIPPLE_R1_BASE_PX: Final[float] = 10.0  # px: نصف القطر النهائي عند z = 0
_RIPPLE_R1_DEPTH_PX: Final[float] = 26.0  # px: زيادة نصف القطر النهائي مع العمق (z = 1)
_RIPPLE_ASPECT: Final[float] = 3.0  # rx / ry (إهليلج مسطّح يوحي بمنظور سطح الماء)
_RIPPLE_T_MIN_S: Final[float] = 0.35  # ثانية: أقصر عمر
_RIPPLE_T_MAX_S: Final[float] = 0.55  # ثانية: أطول عمر
# --- احتمال التوليد: p = amount * (0.35 + 0.65 z)، فالقطرات القريبة (z كبير) أكثر رذاذًا ---
_PROB_BASE: Final[float] = 0.35
_PROB_DEPTH: Final[float] = 0.65
# --- جسيمات الرذاذ ---
_SPRAY_MIN: Final[int] = 2
_SPRAY_MAX_EXCLUSIVE: Final[int] = 5  # integers(2, 5) تعطي 2 أو 3 أو 4
_SPRAY_ANGLE_MIN_DEG: Final[float] = -150.0  # مقيسة من +x ومحور y للأسفل: مخروط للأعلى
_SPRAY_ANGLE_MAX_DEG: Final[float] = -30.0
_SPRAY_SPEED_MIN: Final[float] = 90.0  # px/s
_SPRAY_SPEED_MAX: Final[float] = 240.0
_SPRAY_LIFE_MIN_S: Final[float] = 0.22
_SPRAY_LIFE_MAX_S: Final[float] = 0.42
_SPRAY_SIZE_MIN_PX: Final[float] = 1.0
_SPRAY_SIZE_MAX_PX: Final[float] = 2.0
_SPRAY_DEPTH_MIN: Final[float] = 0.45  # معامل سرعة الرذاذ البعيد (z = 0) عند أقصى تأثير عمق
# --- الشفافية الابتدائية: تتراوح من 0.5 (بعيد) إلى 1.0 (قريب) ---
_ALPHA_BASE: Final[float] = 0.5
_ALPHA_DEPTH: Final[float] = 0.5
_LANDING_COLUMNS: Final[int] = 3  # x, y, z
_RIPPLE_COLUMNS: Final[int] = 5  # x, y, rx, ry, alpha
_SPRAY_COLUMNS: Final[int] = 4  # x, y, size, alpha


class SplashSystem:
    """رذاذ بحوض ثابت السعة.

    الثوابت (invariants): عدد الحيّ <= capacity في كل حوض؛ كل جسيم يموت عند بلوغ عمره الأقصى؛
    الشفافية لا تزيد أبدًا مع عمر الجسيم. التعقيد O(capacity) لكل step.
    """

    def __init__(self, rng: np.random.Generator, capacity: int = SPLASH_POOL_CAPACITY) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rng = rng
        self._capacity = int(capacity)
        cap, f32 = self._capacity, np.float32
        # حوض التموّجات
        self._r_x = np.zeros(cap, f32)
        self._r_y = np.zeros(cap, f32)
        self._r_age = np.zeros(cap, f32)
        self._r_dur = np.ones(cap, f32)
        self._r_end = np.zeros(cap, f32)  # نصف القطر النهائي r1
        self._r_alpha0 = np.zeros(cap, f32)
        self._r_alive = np.zeros(cap, np.bool_)
        self._r_head = 0
        # حوض جسيمات الرذاذ
        self._s_x = np.zeros(cap, f32)
        self._s_y = np.zeros(cap, f32)
        self._s_vx = np.zeros(cap, f32)
        self._s_vy = np.zeros(cap, f32)
        self._s_age = np.zeros(cap, f32)
        self._s_life = np.ones(cap, f32)
        self._s_size = np.zeros(cap, f32)
        self._s_alpha0 = np.zeros(cap, f32)
        self._s_alive = np.zeros(cap, np.bool_)
        self._s_head = 0
        # مخازن الإخراج مسبقة الحجز (تُعاد كعروض views)
        self._ripple_out = np.zeros((cap, _RIPPLE_COLUMNS), f32)
        self._spray_out = np.zeros((cap, _SPRAY_COLUMNS), f32)

    # ------------------------------------------------------------------ التوليد
    def spawn(self, landings: np.ndarray, amount: float) -> None:
        """يولّد رذاذًا من الهبوطات (m, 3) = (x, y, z) باحتمال p = amount * (0.35 + 0.65 z).

        Raises:
            ValueError: إذا لم يكن شكل landings (m, 3).
        """
        if landings.size == 0:
            return
        if landings.ndim != 2 or landings.shape[1] != _LANDING_COLUMNS:
            raise ValueError("landings must have shape (m, 3)")
        level = clamp(amount, 0.0, 1.0)
        if level <= 0.0:
            return
        z = landings[:, 2]
        probability = level * (_PROB_BASE + _PROB_DEPTH * z)
        chosen = landings[self._rng.random(landings.shape[0]) < probability]
        if chosen.shape[0] == 0:
            return
        self._spawn_ripples(chosen)
        self._spawn_sprays(chosen)

    def _ring_indices(self, head: int, count: int) -> np.ndarray:
        """فهارس الكتابة في الحوض الدائري بدءًا من head (تلتف عند الامتلاء فتستبدل الأقدم)."""
        return (head + np.arange(count)) % self._capacity

    def _spawn_ripples(self, chosen: np.ndarray) -> None:
        count = chosen.shape[0]
        idx = self._ring_indices(self._r_head, count)
        z = chosen[:, 2]
        self._r_x[idx] = chosen[:, 0]
        self._r_y[idx] = chosen[:, 1]
        self._r_age[idx] = 0.0
        self._r_dur[idx] = self._rng.uniform(_RIPPLE_T_MIN_S, _RIPPLE_T_MAX_S, count)
        self._r_end[idx] = _RIPPLE_R1_BASE_PX + _RIPPLE_R1_DEPTH_PX * z
        self._r_alpha0[idx] = _ALPHA_BASE + _ALPHA_DEPTH * z
        self._r_alive[idx] = True
        self._r_head = (self._r_head + count) % self._capacity

    def _spawn_sprays(self, chosen: np.ndarray) -> None:
        per_splash = self._rng.integers(_SPRAY_MIN, _SPRAY_MAX_EXCLUSIVE, size=chosen.shape[0])
        origins = np.repeat(chosen, per_splash, axis=0)
        total = origins.shape[0]
        z = origins[:, 2]
        angle = np.radians(self._rng.uniform(_SPRAY_ANGLE_MIN_DEG, _SPRAY_ANGLE_MAX_DEG, total))
        depth_factor = _SPRAY_DEPTH_MIN + (1.0 - _SPRAY_DEPTH_MIN) * z  # f_speed(z) عند parallax=1
        speed = self._rng.uniform(_SPRAY_SPEED_MIN, _SPRAY_SPEED_MAX, total) * depth_factor
        idx = self._ring_indices(self._s_head, total)
        self._s_x[idx] = origins[:, 0]
        self._s_y[idx] = origins[:, 1]
        self._s_vx[idx] = speed * np.cos(angle)
        self._s_vy[idx] = speed * np.sin(angle)  # سالبة: للأعلى
        self._s_age[idx] = 0.0
        self._s_life[idx] = self._rng.uniform(_SPRAY_LIFE_MIN_S, _SPRAY_LIFE_MAX_S, total)
        self._s_size[idx] = self._rng.uniform(_SPRAY_SIZE_MIN_PX, _SPRAY_SIZE_MAX_PX, total)
        self._s_alpha0[idx] = _ALPHA_BASE + _ALPHA_DEPTH * z
        self._s_alive[idx] = True
        self._s_head = (self._s_head + total) % self._capacity

    # ------------------------------------------------------------------ التقدّم
    def step(self, dt: float) -> None:
        """يقدّم الجسيمات الحيّة فقط (فلا تنجرف قيم الميتة)، ويقتل ما بلغ عمره الأقصى."""
        if dt <= 0.0:
            return
        alive = np.flatnonzero(self._r_alive)
        if alive.size:
            self._r_age[alive] += dt
            expired = alive[self._r_age[alive] >= self._r_dur[alive]]
            self._r_alive[expired] = False
        alive = np.flatnonzero(self._s_alive)
        if alive.size:
            self._s_vy[alive] += GRAVITY_PX_S2 * dt  # الجاذبية تسحب الرذاذ للأسفل
            self._s_x[alive] += self._s_vx[alive] * dt
            self._s_y[alive] += self._s_vy[alive] * dt
            self._s_age[alive] += dt
            expired = alive[self._s_age[alive] >= self._s_life[alive]]
            self._s_alive[expired] = False

    # ------------------------------------------------------------------ الإخراج
    def ripples(self) -> np.ndarray:
        """(k, 5) float32: x, y, rx, ry, alpha. عرض (view) صالح حتى الاستدعاء التالي.

        rx(t) = lerp(r0, r1, ease_out_quad(t / T))، وry = rx / 3، وalpha = alpha0 * (1 - t / T)^2.
        ease_out_quad(u) = 1 - (1 - u)^2 مكتوبة متجهة هنا (النسخة العددية في math_utils).
        """
        idx = np.flatnonzero(self._r_alive)
        out = self._ripple_out[: idx.size]
        if idx.size == 0:
            return out
        u = np.clip(self._r_age[idx] / self._r_dur[idx], 0.0, 1.0)
        eased = 1.0 - (1.0 - u) * (1.0 - u)
        radius = _RIPPLE_R0_PX + (self._r_end[idx] - _RIPPLE_R0_PX) * eased
        out[:, 0] = self._r_x[idx]
        out[:, 1] = self._r_y[idx]
        out[:, 2] = radius
        out[:, 3] = radius / _RIPPLE_ASPECT
        out[:, 4] = self._r_alpha0[idx] * (1.0 - u) ** 2
        return out

    def sprays(self) -> np.ndarray:
        """(k, 4) float32: x, y, size, alpha (تتلاشى خطيًا). عرض صالح حتى الاستدعاء التالي."""
        idx = np.flatnonzero(self._s_alive)
        out = self._spray_out[: idx.size]
        if idx.size == 0:
            return out
        u = np.clip(self._s_age[idx] / self._s_life[idx], 0.0, 1.0)
        out[:, 0] = self._s_x[idx]
        out[:, 1] = self._s_y[idx]
        out[:, 2] = self._s_size[idx]
        out[:, 3] = self._s_alpha0[idx] * (1.0 - u)
        return out

    def clear(self) -> None:
        """يقتل كل الجسيمات (عند الإيقاف المؤقت أو تغيير الإعدادات الجذري)."""
        self._r_alive[:] = False
        self._s_alive[:] = False