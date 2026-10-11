"""raindesk/engine/edge_streams.py

الغرض: قطرات ماء تنزلق على حافتي الشاشة اليسرى واليمنى كما تنزلق على زجاج نافذة مبلّلة.
المسؤوليات: محاكاة قطرات تلتصق ثم تنزلق ثم تقف (stick-slip)، وتلتحم عند التقائها، وتترك أثرًا
    مبلّلًا رفيعًا يتلاشى مع الزمن وحبيبات صغيرة متخلّفة؛ وتصدير القطرات والآثار والحبيبات
    كمصفوفات جاهزة للرسم. يحلّ هذا التصميم محلّ المسارات الجيبية المتمايلة في المواصفة الأولى،
    لأن الأسلاك الموجية المتقاطعة لا تشبه الماء؛ ويبقى سقف 600 نقطة مسار لكل شاشة.
الاعتماديات: NumPy والمكتبة القياسية.
النمط التصميمي: Structure of Arrays مع حساب متجه (لا حلقات بايثون على الجسيمات)، وآلة حالات
    ثنائية (ملتصقة/منزلقة) تُحدَّث بأقنعة منطقية، وحلقة دائرية (Ring Buffer) للأثر وللحبيبات.
ملاحظات: الفيزياء مبسّطة: كتلة القطرة m تحدّد نصف قطرها r = 3.1 * m^(1/3) وسرعتها الحدّية
    v ~ sqrt(m)؛ تفقد الكتلة وهي تنزلق (الأثر والحبيبات)، فتقف عند كتلة صغيرة أو عند عائق
    عشوائي، ثم تنمو من جديد حتى تتجاوز كتلة حرجة فتنزلق ثانية. العصف يزيح هدف الانجراف الجانبي
    لا الخطوط كلها. كل العشوائية من rng الممرَّر.
مثال: streams.configure(3, 0.35); streams.step(dt, gust); drops = streams.drops()
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np

from raindesk.engine.math_utils import clamp

# ---------------------------------------------------------------- هندسة الحافة
_MARGIN_PX: Final[float] = 6.0  # px: أول مسار يبعد عن حافة الشاشة
_BAND_FRACTION: Final[float] = 0.06  # عرض شريط الحافة: 6% من عرض الشاشة
_BAND_MAX_PX: Final[float] = 120.0  # px: سقف عرض الشريط
_MIN_SPACING_PX: Final[float] = 1.0  # px: أقل مسافة بين مسارين متجاورين
_MAX_COUNT_PER_EDGE: Final[int] = 8
_MAX_PATH_POINTS: Final[int] = 600  # سقف نقاط المسارات (القطرات * نقاط الأثر) في الشاشة
_MIN_SIZE_PX: Final[float] = 1.0
_EDGE_PAD_PX: Final[float] = 1.0  # px: أقل بعد لمركز القطرة عن حافة الشاشة
_SPAWN_Y_MIN_FRACTION: Final[float] = 0.02  # أعلى موضع لولادة قطرة (نسبة من الارتفاع)
_SPAWN_Y_MAX_FRACTION: Final[float] = 0.85  # أدنى موضع لولادة قطرة
_EXIT_MARGIN_PX: Final[float] = 24.0  # px: القطرة تُعاد بعد تجاوز أسفل الشاشة بهذا القدر

# ---------------------------------------------------------------- المجموعة (pool)
_DROPS_PER_LANE: Final[int] = 4  # قطرات كل مسار (ملتصقة أو منزلقة)
_RESIDUE_PER_LANE: Final[int] = 6  # حبيبات متخلّفة لكل مسار
_WARMUP_S: Final[float] = 14.0  # s: محاكاة تسخين عند البناء كي لا تبدأ الشاشة فارغة
_WARMUP_DT_S: Final[float] = 1.0 / 20.0
_MAX_DT_S: Final[float] = 0.1  # s: سقف خطوة المحاكاة

# ---------------------------------------------------------------- الكتلة والحجم
_RADIUS_PER_CBRT_MASS_PX: Final[float] = 3.1  # px: نصف القطر عند كتلة 1
_MASS_SPAWN_MIN: Final[float] = 0.04  # كتلة القطرة المولودة (صغيرة جدًا وشفافة)
_MASS_SPAWN_MAX: Final[float] = 0.09
_MASS_MAX: Final[float] = 6.0  # سقف الكتلة بعد الالتحام
_GROWTH_MIN: Final[float] = 0.06  # كتلة/s: نمو القطرة الملتصقة (تكثّف ورذاذ)
_GROWTH_MAX: Final[float] = 0.14
_CRITICAL_MIN: Final[float] = 1.0  # الكتلة الحرجة الأولى التي تبدأ عندها الانزلاق
_CRITICAL_MAX: Final[float] = 2.0
_RESTART_GAP_MIN: Final[float] = 0.25  # فرق الكتلة الحرجة الجديد بعد التوقف
_RESTART_GAP_MAX: Final[float] = 0.90
_FADE_IN_MASS: Final[float] = 0.25  # كتلة تكتمل عندها شفافية القطرة الوليدة (تفادي الظهور المفاجئ)
_FADE_IN_START_MASS: Final[float] = 0.05

# ---------------------------------------------------------------- الانزلاق
_START_SPEED: Final[float] = 8.0  # px/s: سرعة الانطلاق من السكون
_SPEED_BASE: Final[float] = 105.0  # px/s: السرعة الحدّية عند كتلة 1
_SPEED_MAX: Final[float] = 430.0  # px/s
_SPEED_MIN_TARGET: Final[float] = 25.0  # px/s: أدنى سرعة هدف أثناء الانزلاق
_SPEED_TAU_S: Final[float] = 0.30  # s: ثابت زمن التسارع نحو السرعة الهدف
_WOBBLE_A: Final[float] = 0.35  # تذبذب السرعة الأول (نسبة) كي لا تكون السرعة ثابتة
_WOBBLE_B: Final[float] = 0.20  # التذبذب الثاني بتردد غير قابل للقسمة على الأول
_WOBBLE_W_MIN: Final[float] = 0.8  # rad/s
_WOBBLE_W_MAX: Final[float] = 2.2
_WOBBLE_RATIO: Final[float] = 2.7
_MASS_LOSS_PER_PX: Final[float] = 0.0020  # كتلة/px: ما يتركه الأثر والحبيبات
_STOP_MASS: Final[float] = 0.55  # أقل كتلة تستمر بها القطرة في الانزلاق
_STICK_HAZARD_PER_PX: Final[float] = 0.0035  # احتمال التعلّق بعائق لكل px (متوسط ~285 px)
_KINK_PX: Final[float] = 1.2  # px: انحراف جانبي صغير عند الانطلاق والتوقف

# ---------------------------------------------------------------- الانجراف الجانبي
_WANDER_PULL_PER_PX: Final[float] = 0.02  # قوة الشدّ نحو مركز المسار لكل px مقطوع
_WANDER_SIGMA_PX: Final[float] = 0.6  # px/sqrt(px): ضجيج الانحراف (الانحراف المعياري ~3 px)
_GUST_SHIFT_PX: Final[float] = 6.0  # px: إزاحة هدف الانجراف لكل وحدة عصف
_SPAWN_X_SIGMA_PX: Final[float] = 3.0  # px: بعثرة موضع الولادة حول مركز المسار

# ---------------------------------------------------------------- الالتحام
_MERGE_MIN_MASS: Final[float] = 0.12  # القطرات الأصغر لا تشارك (لم تظهر بعد)
_MERGE_REACH: Final[float] = 0.85  # نسبة مجموع نصفي القطرين التي يبدأ عندها الالتحام
_MERGE_ABSORB: Final[float] = 0.85  # نسبة كتلة المبتلَعة التي تُضاف (الباقي يتبخّر)

# ---------------------------------------------------------------- الأثر المبلّل
_TRAIL_LENGTH_PX: Final[float] = 230.0  # px: طول الأثر خلف القطرة
_TRAIL_MAX_SAMPLES: Final[int] = 20
_TRAIL_MIN_SAMPLES: Final[int] = 8
_TRAIL_TAU_S: Final[float] = 4.5  # s: ثابت تلاشي الأثر (يجفّ تدريجيًا)
_TRAIL_WIDTH_PER_R: Final[float] = 0.34  # نصف عرض الأثر نسبةً لنصف قطر القطرة وقت العيّنة
_TRAIL_HALF_MIN_PX: Final[float] = 0.35  # px
_TRAIL_HALF_MAX_PX: Final[float] = 1.6  # px
_TRAIL_TAPER: Final[float] = 0.65  # مقدار انحسار العرض عند ذيل الأثر
_TRAIL_GAIN: Final[float] = 0.9  # شفافية الأثر نسبةً لشفافية القطرة
_MAX_SAMPLES_PER_STEP: Final[int] = 4  # أقصى عيّنات تُضاف لكل قطرة في خطوة واحدة
_TRAIL_NEVER: Final[float] = -1.0e9  # زمن ميلاد عيّنة غير موجودة

# ---------------------------------------------------------------- الحبيبات المتخلّفة
_RESIDUE_PER_PX: Final[float] = 0.018  # احتمال ترك حبيبة لكل px مقطوع (~ كل 55 px)
_RESIDUE_R_MIN_PX: Final[float] = 0.7
_RESIDUE_R_MAX_PX: Final[float] = 1.5
_RESIDUE_SIDE_PX: Final[float] = 1.6  # px: أقصى بعد جانبي عن محور الأثر
_RESIDUE_LIFE_MIN_S: Final[float] = 6.0
_RESIDUE_LIFE_MAX_S: Final[float] = 16.0
_RESIDUE_FADE_IN_S: Final[float] = 0.4
_RESIDUE_FADE_OUT_FRACTION: Final[float] = 0.35  # آخر 35% من العمر تتلاشى فيها الحبيبة

# ---------------------------------------------------------------- الرسم والشفافية
_ALPHA_MULT_MIN: Final[float] = 0.6  # تفاوت ثابت لكل قطرة
_ALPHA_MULT_MAX: Final[float] = 1.0
_DROP_GAIN: Final[float] = 1.7  # معامل سطوع القطرة نسبةً لإعداد الشفافية
_STRETCH_SPEED: Final[float] = 220.0  # px/s: السرعة التي يبلغ عندها استطالة القطرة حدّها
_STRETCH_Y: Final[float] = 0.55  # أقصى استطالة رأسية إضافية للقطرة المنزلقة
_SQUEEZE_X: Final[float] = 0.10  # أقصى انكماش أفقي للقطرة المنزلقة
_SAG_Y: Final[float] = 1.08  # القطرة الساكنة أطول قليلًا من عرضها (ثقل)
_TOP_FADE_FRACTION: Final[float] = 0.10  # التلاشي على أعلى 10% من الارتفاع
_VISIBLE_ALPHA: Final[float] = 0.01


@dataclass(slots=True)
class TrailSet:
    """آثار كل القطرات مرتبة من الرأس (العمود 0) إلى الذيل. count[i] = العيّنات الصالحة للقطرة i."""

    x: np.ndarray  # (drops, samples) float32
    y: np.ndarray
    half_width: np.ndarray  # px: نصف عرض الأثر عند كل عيّنة
    alpha: np.ndarray  # [0, 1]، غير متزايدة من الرأس إلى الذيل
    count: np.ndarray  # (drops,) int32؛ 0 = لا أثر مرئي


class EdgeStreams:
    """قطرات الحواف. الثوابت: القطرات * (عيّنات الأثر + 1) <= 600؛ كل العشوائية من rng."""

    def __init__(self, width: float, height: float, rng: np.random.Generator) -> None:
        self._rng = rng
        self._width = max(float(width), _MIN_SIZE_PX)
        self._height = max(float(height), _MIN_SIZE_PX)
        self._count = 0  # عدد المسارات لكل حافة (0 = لا قطرات)
        self._opacity = 0.0
        self._time = 0.0
        self._shift = 0.0
        self._build()

    # ------------------------------------------------------------------ الإعداد
    def resize(self, width: float, height: float) -> None:
        """يغيّر أبعاد الشاشة ويعيد بناء الهندسة؛ لا شيء إن لم يتغيّر الحجم."""
        new_w, new_h = max(float(width), _MIN_SIZE_PX), max(float(height), _MIN_SIZE_PX)
        if new_w == self._width and new_h == self._height:
            return
        self._width, self._height = new_w, new_h
        self._build()

    def configure(self, count_per_edge: int, opacity: float) -> None:
        """عدد المسارات لكل حافة (0 إلى 8) وشفافيتها (0 إلى 1)؛ تغيير العدد يعيد توليد القطرات."""
        count = min(max(int(count_per_edge), 0), _MAX_COUNT_PER_EDGE)
        self._opacity = clamp(opacity, 0.0, 1.0)
        if count != self._count:
            self._count = count
            self._build()

    @property
    def drop_total(self) -> int:
        """عدد القطرات في المجموعة (ملتصقة ومنزلقة ووليدة)."""
        return self._drops

    @property
    def sliding_count(self) -> int:
        """عدد القطرات المنزلقة الآن."""
        return int(self._sliding.sum()) if self._drops else 0

    def _build(self) -> None:
        """يخصّص مصفوفات المجموعة ويولّدها ثم يسخّنها كي تبدو الشاشة حيّة من أول إطار."""
        lanes = 2 * self._count
        self._lanes = lanes
        self._drops = lanes * _DROPS_PER_LANE
        self._time = 0.0
        drops, width, height = self._drops, self._width, self._height
        if drops == 0:
            self._alloc_empty()
            return
        band = min(_BAND_FRACTION * width, _BAND_MAX_PX)
        spacing = max((band - _MARGIN_PX) / self._count, _MIN_SPACING_PX)
        index = np.tile(np.arange(self._count), 2)  # فهرس المسار داخل حافته
        right = np.repeat([False, True], self._count)
        offset = _MARGIN_PX + index * spacing
        self._lane_x = np.where(right, width - offset, offset)  # اليمين مرآة اليسار
        self._lane_of = np.repeat(np.arange(lanes), _DROPS_PER_LANE)

        # سقف النقاط: كل قطرة تحمل رأسها وعيّنات أثرها.
        samples = _MAX_PATH_POINTS // drops - 1
        self._trail_len = int(min(max(samples, _TRAIL_MIN_SAMPLES), _TRAIL_MAX_SAMPLES))
        self._trail_spacing = _TRAIL_LENGTH_PX / self._trail_len

        zeros = np.zeros(drops)
        self._x = zeros.copy()
        self._y = zeros.copy()
        self._vy = zeros.copy()
        self._mass = zeros.copy()
        self._critical = zeros.copy()
        self._grow = zeros.copy()
        self._alpha_mult = zeros.copy()
        self._wobble_w = zeros.copy()
        self._wobble_phase = zeros.copy()
        self._sliding = np.zeros(drops, dtype=bool)
        self._trail_x = np.zeros((drops, self._trail_len))
        self._trail_y = np.zeros((drops, self._trail_len))
        self._trail_r = np.zeros((drops, self._trail_len))
        self._trail_t = np.full((drops, self._trail_len), _TRAIL_NEVER)
        self._trail_head = np.zeros(drops, dtype=np.int64)
        self._trail_acc = zeros.copy()

        residue = lanes * _RESIDUE_PER_LANE
        self._res_x = np.zeros(residue)
        self._res_y = np.zeros(residue)
        self._res_r = np.zeros(residue)
        self._res_t0 = np.full(residue, _TRAIL_NEVER)
        self._res_life = np.ones(residue)
        self._res_cursor = 0
        self._drops_out = np.zeros((drops, 6), np.float32)

        self._respawn(np.ones(drops, dtype=bool))
        self._y[:] = self._rng.uniform(_SPAWN_Y_MIN_FRACTION * height, 0.95 * height, drops)
        self._mass[:] = self._rng.uniform(_FADE_IN_MASS, _CRITICAL_MAX, drops)
        self._critical[:] = self._mass + self._rng.uniform(
            _RESTART_GAP_MIN, _RESTART_GAP_MAX, drops
        )
        steps = int(_WARMUP_S / _WARMUP_DT_S)
        for _ in range(steps):
            self._advance(_WARMUP_DT_S)

    def _alloc_empty(self) -> None:
        """مصفوفات فارغة كي تعمل واجهات التصدير بلا فروع خاصة في المرسِم."""
        self._trail_len = _TRAIL_MIN_SAMPLES
        self._trail_spacing = _TRAIL_LENGTH_PX / self._trail_len
        self._sliding = np.zeros(0, dtype=bool)
        self._drops_out = np.zeros((0, 6), np.float32)
        for name in ("_x", "_y", "_vy", "_mass", "_alpha_mult", "_res_x", "_res_y", "_res_r"):
            setattr(self, name, np.zeros(0))
        self._res_t0 = np.zeros(0)
        self._res_life = np.ones(0)
        self._trail_x = self._trail_y = self._trail_r = self._trail_t = np.zeros((0, 3))
        self._trail_head = np.zeros(0, dtype=np.int64)
        self._res_cursor = 0

    # ------------------------------------------------------------------ الولادة
    def _respawn(self, mask: np.ndarray) -> None:
        """يعيد القطرات المحدَّدة بالقناع قطراتٍ وليدة ملتصقة بكتلة صغيرة وأثر ممسوح."""
        n = int(mask.sum())
        if n == 0:
            return
        rng, height = self._rng, self._height
        base = self._lane_x[self._lane_of[mask]]
        x = base + rng.normal(0.0, _SPAWN_X_SIGMA_PX, n)
        self._x[mask] = np.clip(x, _EDGE_PAD_PX, self._width - _EDGE_PAD_PX)
        self._y[mask] = rng.uniform(
            _SPAWN_Y_MIN_FRACTION * height, _SPAWN_Y_MAX_FRACTION * height, n
        )
        self._vy[mask] = 0.0
        self._mass[mask] = rng.uniform(_MASS_SPAWN_MIN, _MASS_SPAWN_MAX, n)
        self._critical[mask] = rng.uniform(_CRITICAL_MIN, _CRITICAL_MAX, n)
        self._grow[mask] = rng.uniform(_GROWTH_MIN, _GROWTH_MAX, n)
        self._alpha_mult[mask] = rng.uniform(_ALPHA_MULT_MIN, _ALPHA_MULT_MAX, n)
        self._wobble_w[mask] = rng.uniform(_WOBBLE_W_MIN, _WOBBLE_W_MAX, n)
        self._wobble_phase[mask] = rng.uniform(0.0, 2.0 * math.pi, n)
        self._sliding[mask] = False
        self._trail_t[mask] = _TRAIL_NEVER
        self._trail_head[mask] = 0
        self._trail_acc[mask] = 0.0

    # ------------------------------------------------------------------ التقدّم
    def step(self, dt: float, gust: float) -> None:
        """يقدّم المحاكاة؛ gust في [-1, 1] يزيح هدف الانجراف الجانبي للمنزلقات بـ 6 px * gust."""
        if self._drops == 0 or dt <= 0.0:
            return
        self._shift = _GUST_SHIFT_PX * clamp(gust, -1.0, 1.0)
        self._advance(min(dt, _MAX_DT_S))

    def _advance(self, dt: float) -> None:
        """خطوة واحدة: نمو، التحام، انطلاق، انزلاق وأثر وحبيبات، توقف، ثم إعادة تدوير الخارجين."""
        rng = self._rng
        self._time += dt
        sliding = self._sliding
        self._mass += np.where(sliding, 0.0, self._grow) * dt
        self._merge()

        start = ~sliding & (self._mass >= self._critical)
        if start.any():
            sliding[start] = True
            self._vy[start] = _START_SPEED
            self._x[start] += rng.uniform(-_KINK_PX, _KINK_PX, int(start.sum()))

        wobble = (
            1.0
            + _WOBBLE_A * np.sin(self._wobble_w * self._time + self._wobble_phase)
            + _WOBBLE_B * np.sin(_WOBBLE_RATIO * self._wobble_w * self._time)
        )
        target = np.clip(
            _SPEED_BASE * np.sqrt(self._mass) * wobble, _SPEED_MIN_TARGET, _SPEED_MAX
        )
        blend = 1.0 - math.exp(-dt / _SPEED_TAU_S)
        self._vy = np.where(sliding, self._vy + (target - self._vy) * blend, 0.0)
        dy = self._vy * dt  # مقطوع هذه الخطوة (صفر للملتصقة)
        self._y += dy
        self._mass -= _MASS_LOSS_PER_PX * dy

        # انجراف جانبي: عملية Ornstein-Uhlenbeck على المسافة المقطوعة لا على الزمن.
        centre = self._lane_x[self._lane_of] + self._shift
        noise = rng.standard_normal(self._drops)
        self._x += (
            -_WANDER_PULL_PER_PX * (self._x - centre) * dy
            + _WANDER_SIGMA_PX * np.sqrt(dy) * noise
        )

        self._record_trail(dy)
        self._shed_residue(dy)

        hazard = 1.0 - np.exp(-_STICK_HAZARD_PER_PX * dy)
        stop = sliding & ((self._mass < _STOP_MASS) | (rng.random(self._drops) < hazard))
        if stop.any():
            n = int(stop.sum())
            sliding[stop] = False
            self._vy[stop] = 0.0
            self._critical[stop] = self._mass[stop] + rng.uniform(
                _RESTART_GAP_MIN, _RESTART_GAP_MAX, n
            )
            self._x[stop] += rng.uniform(-_KINK_PX, _KINK_PX, n)
        np.clip(self._x, _EDGE_PAD_PX, self._width - _EDGE_PAD_PX, out=self._x)
        gone = self._y > self._height + _EXIT_MARGIN_PX
        if gone.any():
            self._respawn(gone)

    def _merge(self) -> None:
        """الالتحام: الأكبر كتلةً يبتلع الأصغر عند التماسّ إن كان أحدهما منزلقًا (مصفوفة n*n)."""
        mass = self._mass
        radius = _RADIUS_PER_CBRT_MASS_PX * np.cbrt(mass)
        reach = _MERGE_REACH * (radius[:, None] + radius[None, :])
        dx = self._x[:, None] - self._x[None, :]
        dy = self._y[:, None] - self._y[None, :]
        touching = dx * dx + dy * dy < reach * reach
        touching &= self._sliding[:, None] | self._sliding[None, :]
        visible = mass >= _MERGE_MIN_MASS
        touching &= visible[:, None] & visible[None, :]
        index = np.arange(self._drops)
        bigger = (mass[:, None] > mass[None, :]) | (
            (mass[:, None] == mass[None, :]) & (index[:, None] < index[None, :])
        )
        hit = touching & bigger  # hit[i, j]: القطرة i تبتلع j
        if not hit.any():
            return
        victims = hit.any(axis=0)
        hit &= ~victims[:, None]  # مبتلِعة واحدة لا تكون ضحية في الخطوة نفسها
        victims = hit.any(axis=0)
        if not victims.any():
            return
        eater = np.argmax(hit, axis=0)[victims]
        np.add.at(self._mass, eater, _MERGE_ABSORB * mass[victims])
        np.minimum(self._mass, _MASS_MAX, out=self._mass)
        self._respawn(victims)

    def _record_trail(self, dy: np.ndarray) -> None:
        """يضيف عيّنات الأثر كلما قطعت القطرة مسافة العيّنة (حلقة دائرية لكل قطرة)."""
        acc = self._trail_acc + dy
        radius = _RADIUS_PER_CBRT_MASS_PX * np.cbrt(np.maximum(self._mass, 0.0))
        for _ in range(_MAX_SAMPLES_PER_STEP):
            due = acc >= self._trail_spacing
            if not due.any():
                break
            rows = np.flatnonzero(due)
            self._trail_head[rows] = (self._trail_head[rows] + 1) % self._trail_len
            cols = self._trail_head[rows]
            self._trail_x[rows, cols] = self._x[rows]
            self._trail_y[rows, cols] = self._y[rows]
            self._trail_r[rows, cols] = radius[rows]
            self._trail_t[rows, cols] = self._time
            acc[rows] -= self._trail_spacing
        self._trail_acc = np.minimum(acc, self._trail_spacing)

    def _shed_residue(self, dy: np.ndarray) -> None:
        """تترك القطرة المنزلقة حبيبات صغيرة خلفها باحتمال يتناسب مع المسافة (حلقة دائرية)."""
        rng = self._rng
        chance = np.minimum(_RESIDUE_PER_PX * dy, 1.0)
        rows = np.flatnonzero(rng.random(self._drops) < chance)
        k = rows.size
        if k == 0:
            return
        size = len(self._res_x)
        slots = (self._res_cursor + np.arange(k)) % size
        self._res_cursor = int((self._res_cursor + k) % size)
        radius = _RADIUS_PER_CBRT_MASS_PX * np.cbrt(np.maximum(self._mass[rows], 0.0))
        side = rng.uniform(-_RESIDUE_SIDE_PX, _RESIDUE_SIDE_PX, k)
        self._res_x[slots] = np.clip(
            self._x[rows] + side, _EDGE_PAD_PX, self._width - _EDGE_PAD_PX
        )
        self._res_y[slots] = self._y[rows] - radius
        self._res_r[slots] = rng.uniform(_RESIDUE_R_MIN_PX, _RESIDUE_R_MAX_PX, k)
        self._res_t0[slots] = self._time
        self._res_life[slots] = rng.uniform(_RESIDUE_LIFE_MIN_S, _RESIDUE_LIFE_MAX_S, k)

    # ------------------------------------------------------------------ الإخراج
    def _top_fade(self, y: np.ndarray) -> np.ndarray:
        """معامل التلاشي في أعلى الشاشة: 0 عند y = 0 و1 بعد 10% من الارتفاع."""
        result: np.ndarray = np.clip(y / (_TOP_FADE_FRACTION * self._height), 0.0, 1.0)
        return result

    def drops(self) -> np.ndarray:
        """(k, 6) float32: x, y, rx, ry, alpha, منزلقة؟ (0/1)؛ عرض صالح حتى الاستدعاء التالي."""
        if self._drops == 0 or self._opacity <= 0.0:
            return self._drops_out[:0]
        mass = np.maximum(self._mass, 0.0)
        radius = _RADIUS_PER_CBRT_MASS_PX * np.cbrt(mass)
        speed = np.clip(self._vy / _STRETCH_SPEED, 0.0, 1.0)
        rx = radius * (1.0 - _SQUEEZE_X * speed)
        ry = radius * (_SAG_Y + _STRETCH_Y * speed)
        born = np.clip(
            (mass - _FADE_IN_START_MASS) / (_FADE_IN_MASS - _FADE_IN_START_MASS), 0.0, 1.0
        )
        alpha = np.clip(
            self._opacity * self._alpha_mult * _DROP_GAIN * born * self._top_fade(self._y),
            0.0,
            1.0,
        )
        keep = alpha > _VISIBLE_ALPHA
        count = int(keep.sum())
        out = self._drops_out[:count]
        out[:, 0] = self._x[keep]
        out[:, 1] = self._y[keep]
        out[:, 2] = rx[keep]
        out[:, 3] = ry[keep]
        out[:, 4] = alpha[keep]
        out[:, 5] = self._sliding[keep]
        return out

    def trails(self) -> TrailSet:
        """آثار القطرات كلها مرتبة من الرأس إلى الذيل؛ count = 0 للقطرة بلا أثر مرئي."""
        length = self._trail_len
        if self._drops == 0 or self._opacity <= 0.0:
            empty = np.zeros((0, length + 1), np.float32)
            return TrailSet(empty, empty, empty, empty, np.zeros(0, np.int32))
        order = (self._trail_head[:, None] - np.arange(length)[None, :]) % length
        sample_x = np.take_along_axis(self._trail_x, order, axis=1)
        sample_y = np.take_along_axis(self._trail_y, order, axis=1)
        sample_r = np.take_along_axis(self._trail_r, order, axis=1)
        age = self._time - np.take_along_axis(self._trail_t, order, axis=1)
        alpha = (
            self._opacity
            * _TRAIL_GAIN
            * _DROP_GAIN
            * self._alpha_mult[:, None]
            * np.exp(-age / _TRAIL_TAU_S)
            * self._top_fade(sample_y)
        )
        np.clip(alpha, 0.0, 1.0, out=alpha)
        valid = alpha > _VISIBLE_ALPHA
        taper = 1.0 - _TRAIL_TAPER * np.arange(length) / length
        half = np.clip(_TRAIL_WIDTH_PER_R * sample_r, _TRAIL_HALF_MIN_PX, _TRAIL_HALF_MAX_PX)
        half = half * taper[None, :]
        count = valid.sum(axis=1).astype(np.int32)  # صالحة بشكل متصل من الرأس (الأقدم أخفت)
        # العمود 0 هو رأس القطرة نفسه، يرث عرض وشفافية أحدث عيّنة.
        full_x = np.concatenate([self._x[:, None], sample_x], axis=1).astype(np.float32)
        full_y = np.concatenate([self._y[:, None], sample_y], axis=1).astype(np.float32)
        full_half = np.concatenate([half[:, :1], half], axis=1).astype(np.float32)
        full_alpha = np.concatenate([alpha[:, :1], alpha], axis=1).astype(np.float32)
        return TrailSet(full_x, full_y, full_half, full_alpha, np.where(count > 0, count + 1, 0))

    def residue(self) -> np.ndarray:
        """(k, 4) float32: x, y, نصف القطر، alpha للحبيبات الحيّة؛ مصفوفة جديدة صغيرة كل مرة."""
        if self._drops == 0 or self._opacity <= 0.0:
            return np.zeros((0, 4), np.float32)
        age = self._time - self._res_t0
        life = self._res_life
        fade_in = np.clip(age / _RESIDUE_FADE_IN_S, 0.0, 1.0)
        fade_out = np.clip((1.0 - age / life) / _RESIDUE_FADE_OUT_FRACTION, 0.0, 1.0)
        alpha = np.clip(
            self._opacity * _DROP_GAIN * _ALPHA_MULT_MAX * fade_in * fade_out
            * self._top_fade(self._res_y),
            0.0,
            1.0,
        )
        keep = (age >= 0.0) & (age < life) & (alpha > _VISIBLE_ALPHA)
        return np.stack(
            [self._res_x[keep], self._res_y[keep], self._res_r[keep], alpha[keep]], axis=1
        ).astype(np.float32)
