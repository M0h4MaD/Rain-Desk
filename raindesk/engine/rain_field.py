"""raindesk/engine/rain_field.py

الغرض: محاكاة قطرات المطر لشاشة واحدة (موضع وسرعة وعمق) بتخطيط SoA ومتجهة بالكامل بـ NumPy.
المسؤوليات: عدد القطرات الفعّال، والحركة بسرعة نهائية ثابتة مع الرياح والعصف، وإعادة التدوير
    (respawn) ضمن شريط تعويض الرياح، ونموذج التعريض لأطوال الخطوط، وتقسيم الخطوط إلى طبقات عمق،
    وتسجيل نقاط الهبوط للرذاذ.
الاعتماديات: NumPy وraindesk.core.constants وraindesk.engine.math_utils وraindesk.engine.params.
النمط التصميمي: Structure of Arrays (SoA) مع Object Pool (قطرات ثابتة العدد تُعاد تدويرها).
ملاحظات: الإحداثيات بالبكسل المنطقي، الأصل أعلى يسار الشاشة، y للأسفل. لا يوجد PySide6 هنا.
    انظر قرارات التصميم DD-04 (SoA) وDD-05 (طبقات العمق) وDD-06 (نموذج التعريض).
مثال: field.set_active_count(n); field.step(dt, params, gust); lines = field.layer_lines(5)
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from raindesk.core.constants import (
    BASE_FALL_SPEED_PX_S,
    DEPTH_BIAS_EXPONENT,
    DEPTH_SPEED_ATTENUATION,
    DROP_JITTER,
    DROPS_PER_MEGAPIXEL_MAX,
    DROPS_PER_MEGAPIXEL_MIN,
    EXPOSURE_TIME_S,
    GUST_MAX_DEG,
    INTENSITY_CURVE_EXPONENT,
    MAX_DROPS_PER_SCREEN,
    MAX_WIND_ANGLE_DEG,
    SPAWN_MARGIN_TOP_FRACTION,
)
from raindesk.engine.math_utils import clamp
from raindesk.engine.params import EngineParams

_PAD_PX: Final[float] = 40.0  # px: هامش أمان خارج الشاشة قبل إعادة تدوير القطرة
_MIN_SIZE_PX: Final[float] = 1.0  # px: أصغر أبعاد مقبولة (يمنع القسمة على صفر)
_PIXELS_PER_MEGAPIXEL: Final[float] = 1e6
_DEPTH_PLANE_MIN_FRACTION: Final[float] = 0.60  # أبعد مستوى أرض = 60% من الارتفاع (depth_plane)
_MAX_LAYERS: Final[int] = 255  # حد dtype الفهرس uint8
_LINE_COLUMNS: Final[int] = 4  # x_tail, y_tail, x_head, y_head
_LANDING_COLUMNS: Final[int] = 3  # x, y, z
GROUND_BOTTOM_EDGE: Final[str] = "bottom_edge"
GROUND_DEPTH_PLANE: Final[str] = "depth_plane"


class RainField:
    """مجموعة قطرات ثابتة السعة؛ يُفعَّل منها بادئة [0, active) فقط.

    الثوابت (invariants): 0 <= active <= capacity؛ لكل قطرة z وjitter ثابتان طوال العمر، لذلك
    تبقى فهارس الطبقات صالحة دون إعادة حساب؛ كل العشوائية تمر عبر rng الممرَّر (حتمية بالبذرة).
    التعقيد: step وlayer_lines بزمن O(N) وذاكرة O(capacity). سلامة الخيوط: غير آمن.
    المصفوفات الكبيرة تُحجز مرة واحدة؛ لا يُحجز لكل إطار إلا أقنعة منطقية وفهارس صغيرة.
    """

    def __init__(
        self,
        width: float,
        height: float,
        rng: np.random.Generator,
        capacity: int = MAX_DROPS_PER_SCREEN,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rng = rng
        self._capacity = int(capacity)
        self._width = max(float(width), _MIN_SIZE_PX)
        self._height = max(float(height), _MIN_SIZE_PX)
        cap = self._capacity
        f32 = np.float32

        # مصفوفات الحالة (SoA): float32 تكفي لمدى الشاشة وتنصّف عرض الذاكرة مقابل float64.
        self._x = np.zeros(cap, f32)
        self._y = np.zeros(cap, f32)
        # العمق z في [0, 1): u ** 1.6 يُحيّز القطرات نحو البعيد (كثير صغير وقليل كبير).
        self._z = (rng.random(cap, dtype=f32) ** f32(DEPTH_BIAS_EXPONENT)).astype(f32)
        # معامل سرعة ثابت لكل قطرة في [1 - J, 1 + J] لكسر التزامن بين القطرات المتقاربة.
        self._jitter = (1.0 + DROP_JITTER * (2.0 * rng.random(cap, dtype=f32) - 1.0)).astype(f32)
        # مصفوفات مؤقتة مسبقة الحجز (scratch) كي لا نحجز ذاكرة كبيرة كل إطار.
        self._vx = np.zeros(cap, f32)
        self._vy = np.zeros(cap, f32)
        self._x_tail = np.zeros(cap, f32)
        self._y_tail = np.zeros(cap, f32)
        self._tmp = np.zeros(cap, f32)
        self._ground = np.zeros(cap, f32)
        self._lines = np.zeros((cap, _LINE_COLUMNS), f32)
        self._sorted = np.zeros((cap, _LINE_COLUMNS), f32)
        self._layer_idx = np.zeros(cap, np.uint8)
        self._layer_count = 0  # عدد الطبقات الذي حُسبت له _layer_idx (0 = لم يُحسب بعد)
        self._landing_buf = np.zeros((cap, _LANDING_COLUMNS), f32)
        self._landing_count = 0

        self._active = 0
        self._tan_eff = 0.0  # tan لآخر زاوية رياح فعلية؛ يُستعمل عند تفعيل قطرات خارج step()
        self._ground_bottom = self._height
        self._ground_mode = GROUND_BOTTOM_EDGE

    # ------------------------------------------------------------------ الحجم والعدد
    @property
    def active_count(self) -> int:
        """عدد القطرات الفعّالة حاليًا."""
        return self._active

    @property
    def _margin(self) -> float:
        """m = SPAWN_MARGIN_TOP_FRACTION * H: ارتفاع منطقة الولادة فوق الشاشة (px)."""
        return SPAWN_MARGIN_TOP_FRACTION * self._height

    def resize(self, width: float, height: float) -> None:
        """يغيّر أبعاد الشاشة ويعيد توزيع القطرات الفعّالة فورًا؛ لا شيء إن لم يتغيّر الحجم."""
        new_w = max(float(width), _MIN_SIZE_PX)
        new_h = max(float(height), _MIN_SIZE_PX)
        if new_w == self._width and new_h == self._height:
            return
        self._width, self._height = new_w, new_h
        self._ground_bottom = new_h  # set_ground يُستدعى بعدها إن احتاج المستدعي قيمة مختلفة
        self._place(slice(0, self._active), initial=True)

    @staticmethod
    def target_count(
        width: float,
        height: float,
        intensity: float,
        multiplier: float,
        wind_angle_deg: float,
        capacity: int = MAX_DROPS_PER_SCREEN,
    ) -> int:
        """عدد القطرات المطلوب لكثافة مرئية مستقلة عن الدقة.

        الصيغة: n = min(capacity, round(multiplier * area_MP * density(i) * band_factor))
            density(i) = D_MIN + (D_MAX - D_MIN) * i ** 1.5   (قطرات لكل ميغابكسل)
            band_factor = (W + (H + m) * |tan(theta)| + 2 * pad) / W
        اشتقاق band_factor: تولد القطرات في شريط أعرض من الشاشة (تعويضًا عن ميلان المسار) عرضه
        B = W + (H + m)|tan(theta)| + 2 pad، فلا يظهر إلا جزء W / B من المجموعة. ضرب العدد
        بـ B / W يستعيد الكثافة المرئية المقصودة. theta هنا هي الزاوية الأساسية المنعّمة،
        دون العصف اللحظي.
        """
        if width <= 0.0 or height <= 0.0 or capacity <= 0:
            return 0
        area_mp = width * height / _PIXELS_PER_MEGAPIXEL
        level = clamp(intensity, 0.0, 1.0)
        density = DROPS_PER_MEGAPIXEL_MIN + (
            DROPS_PER_MEGAPIXEL_MAX - DROPS_PER_MEGAPIXEL_MIN
        ) * level**INTENSITY_CURVE_EXPONENT
        margin = SPAWN_MARGIN_TOP_FRACTION * height
        angle = clamp(wind_angle_deg, -MAX_WIND_ANGLE_DEG, MAX_WIND_ANGLE_DEG)
        slant = (height + margin) * abs(math.tan(math.radians(angle)))  # الإزاحة الأفقية للمسار
        band = (width + slant + 2.0 * _PAD_PX) / width
        count = round(max(multiplier, 0.0) * area_mp * density * band)
        return max(0, min(capacity, count))

    def set_active_count(self, n: int) -> None:
        """يضبط عدد القطرات الفعّالة (مقيَّدًا بالسعة)؛ الزيادة تُملأ فورًا على كامل الشاشة."""
        target = min(max(int(n), 0), self._capacity)
        if target > self._active:
            start = self._active
            self._active = target
            self._place(slice(start, target), initial=True)
        else:
            self._active = target

    def set_ground(self, bottom_y: float, mode: str) -> None:
        """يحدد خط الهبوط: 'bottom_edge' عند bottom_y، أو 'depth_plane' بين 60% منه وbottom_y."""
        self._ground_bottom = max(float(bottom_y), _MIN_SIZE_PX)
        self._ground_mode = mode if mode in (GROUND_BOTTOM_EDGE, GROUND_DEPTH_PLANE) else (
            GROUND_BOTTOM_EDGE
        )

    # ------------------------------------------------------------------ الوضع الابتدائي والولادة
    def _ground_y(self, z: np.ndarray) -> np.ndarray | float:
        """خط الأرض لكل قطرة: ثابت في bottom_edge، وlerp(0.6 B, B, z) في depth_plane."""
        if self._ground_mode == GROUND_DEPTH_PLANE:
            base = self._ground_bottom
            return _DEPTH_PLANE_MIN_FRACTION * base + (1.0 - _DEPTH_PLANE_MIN_FRACTION) * base * z
        return self._ground_bottom

    def _place(self, idx: slice | np.ndarray, *, initial: bool) -> None:
        """يضع قطرات في شريط الولادة المعوَّض بالرياح.

        الشريط عند ارتفاع الولادة: x0 ~ U(lo, hi) حيث t = tan(theta_eff) وm هامش الولادة:
            lo = -(H + m) * max(t, 0) - pad      hi = W - (H + m) * min(t, 0) + pad
        البرهان المختصر على تجانس الكثافة عند كل ارتفاع: قطرة وُلدت عند y0 في [-m, 0] بموضع x0
        تصل إلى الارتفاع y (بين 0 وH) بعد قطع مسافة رأسية d = y - y0 في [0, H + m]، فيكون
        x = x0 + t * d (إزاحة ثابتة لكل d). لكل نقطة مرئية x في [0, W] يقع الأصل x0 = x - t * d
        داخل [-t * (H + m), W] الذي يغطيه الشريط، والإزاحة لا تغيّر الكثافة المنتظمة
        (التحويل انسحاب). فالكثافة عند أي نقطة مرئية هي نفسها، وخليط الإزاحات يبقيها منتظمة.
        في الملء الابتدائي: y ~ U(-m, الأرض) (وهي U(-m, H) في bottom_edge)، ويُستخرج x بنفس
        المسار x = x0 + t * (y - y0) كي يتطابق التوزيع الابتدائي مع المستقر.
        """
        if isinstance(idx, slice):
            count = len(range(*idx.indices(self._capacity)))
        else:
            count = int(idx.size)
        if count == 0:
            return
        rng, f32 = self._rng, np.float32
        width, height, margin, tan_eff = self._width, self._height, self._margin, self._tan_eff
        y0 = -rng.random(count, dtype=f32) * f32(margin)
        lo = -(height + margin) * max(tan_eff, 0.0) - _PAD_PX
        hi = width - (height + margin) * min(tan_eff, 0.0) + _PAD_PX
        x0 = f32(lo) + f32(hi - lo) * rng.random(count, dtype=f32)
        if initial:
            ground = self._ground_y(self._z[idx])
            span_y = np.asarray(ground, f32) + f32(margin)  # ارتفاع مجال الملء (من -m إلى الأرض)
            y = -f32(margin) + rng.random(count, dtype=f32) * span_y
            x = x0 + f32(tan_eff) * (y - y0)
            span = (height + margin) * abs(tan_eff) + _PAD_PX
            x = np.clip(x, f32(-span), f32(width + span))  # لا نولّد قطرات ستُعاد تدويرها فورًا
            self._y[idx] = y
            self._x[idx] = x
        else:
            self._y[idx] = y0
            self._x[idx] = x0

    # ------------------------------------------------------------------ الحركة
    def step(self, dt: float, params: EngineParams, gust: float) -> None:
        """يتقدم بزمن dt.

        الصيغ (سرعة نهائية ثابتة بلا تسارع، x += v * dt):
            f_speed(z) = lerp(1 - p * 0.55, 1, z)           p = parallax
            vy = BASE * speed * f_speed(z) * jitter          px/s
            theta_eff = clamp(theta + gusts * 25 * G, -75, +75)  (درجات)
            vx = vy * tan(theta_eff)
        نموذج التعريض: tail = head - v * EXPOSURE * drop_length، فالأسرع يترك خطًا أطول تلقائيًا
        (كزمن غالق الكاميرا). Args: gust في [-1, 1]. التعقيد O(N) متجهًا.
        """
        n = self._active
        if n <= 0 or dt <= 0.0:
            return
        width, height, margin = self._width, self._height, self._margin
        theta = clamp(
            params.wind_angle_deg + params.wind_gusts * GUST_MAX_DEG * gust,
            -MAX_WIND_ANGLE_DEG,
            MAX_WIND_ANGLE_DEG,
        )
        tan_eff = math.tan(math.radians(theta))
        self._tan_eff = tan_eff

        x, y, z = self._x[:n], self._y[:n], self._z[:n]
        vx, vy, tmp = self._vx[:n], self._vy[:n], self._tmp[:n]

        # vy = BASE * speed * ((1 - a) + a * z) * jitter حيث a = p * DEPTH_SPEED_ATTENUATION.
        attenuation = params.parallax * DEPTH_SPEED_ATTENUATION
        np.multiply(z, attenuation, out=vy)
        vy += 1.0 - attenuation
        vy *= self._jitter[:n]
        vy *= BASE_FALL_SPEED_PX_S * params.speed
        np.multiply(vy, tan_eff, out=vx)

        np.multiply(vx, dt, out=tmp)
        x += tmp
        np.multiply(vy, dt, out=tmp)
        y += tmp

        exposure = EXPOSURE_TIME_S * params.drop_length
        x_tail, y_tail = self._x_tail[:n], self._y_tail[:n]
        np.multiply(vx, exposure, out=tmp)
        np.subtract(x, tmp, out=x_tail)
        np.multiply(vy, exposure, out=tmp)
        np.subtract(y, tmp, out=y_tail)

        # هبوط القطرة: رأسها يبلغ خط الأرض. نخزّن خط الأرض لكل قطرة لاستعماله في تسجيل الهبوط.
        ground = self._ground[:n]
        ground[:] = self._ground_y(z)
        landed = y >= ground
        x_limit = (height + margin) * abs(tan_eff) + _PAD_PX
        recycle = landed | (y_tail > height + _PAD_PX) | (x < -x_limit) | (x > width + x_limit)
        recycle_idx = np.flatnonzero(recycle)
        if recycle_idx.size == 0:
            return
        self._record_landings(np.flatnonzero(landed), x, ground, z)
        self._place(recycle_idx, initial=False)
        # الذيل يتبع الرأس الجديد بنفس السرعة، فلا يبقى خط يمتد من موضع القطرة القديم.
        self._x_tail[recycle_idx] = self._x[recycle_idx] - self._vx[recycle_idx] * exposure
        self._y_tail[recycle_idx] = self._y[recycle_idx] - self._vy[recycle_idx] * exposure

    def _record_landings(
        self, landed_idx: np.ndarray, x: np.ndarray, ground: np.ndarray, z: np.ndarray
    ) -> None:
        """يسجّل (x, y, z) لكل هبوط؛ إذا امتلأ المخزن (لا أحد يستهلكه) تُهمل الزيادة."""
        room = self._capacity - self._landing_count
        if landed_idx.size == 0 or room <= 0:
            return
        take = landed_idx[:room]
        out = self._landing_buf[self._landing_count : self._landing_count + take.size]
        out[:, 0] = x[take]
        out[:, 1] = ground[take]
        out[:, 2] = z[take]
        self._landing_count += int(take.size)

    def drain_landings(self) -> np.ndarray:
        """يعيد نسخة (m, 3) من الهبوطات (x, y, z) منذ آخر استدعاء ويفرّغ المخزن الداخلي."""
        out = self._landing_buf[: self._landing_count].copy()
        self._landing_count = 0
        return out

    # ------------------------------------------------------------------ الخطوط للرسم
    def _refresh_layer_index(self, layer_count: int) -> None:
        """يحسب فهرس الطبقة min(L - 1, int(z * L)) لكل القطرات؛ z ثابت فلا يُعاد إلا عند تغيّر L."""
        scaled = (self._z * np.float32(layer_count)).astype(np.int32)
        np.minimum(scaled, layer_count - 1, out=scaled)
        self._layer_idx[:] = scaled.astype(np.uint8)
        self._layer_count = layer_count

    def layer_lines(self, layer_count: int) -> list[np.ndarray]:
        """خطوط كل طبقة من البعيد إلى القريب: مصفوفة (k, 4) float32 لكل طبقة.

        الأعمدة: x_tail, y_tail, x_head, y_head. القيم عروض (views) على مخزن داخلي صالحة حتى
        الاستدعاء التالي. الفرز: argsort مستقر على uint8؛ تستعمل NumPy فرز الجذر (radix sort)
        للأعداد الصحيحة حتى 16 بت فيكون الفرز O(N). تقارنه tools/bench_engine.py بنهج الأقنعة
        (مرور لكل طبقة) لتبرير الاختيار (DD-05).
        """
        layers = min(max(int(layer_count), 1), _MAX_LAYERS)
        if layers != self._layer_count:
            self._refresh_layer_index(layers)
        n = self._active
        lines = self._lines[:n]
        lines[:, 0] = self._x_tail[:n]
        lines[:, 1] = self._y_tail[:n]
        lines[:, 2] = self._x[:n]
        lines[:, 3] = self._y[:n]
        idx = self._layer_idx[:n]
        order = np.argsort(idx, kind="stable")
        np.take(lines, order, axis=0, out=self._sorted[:n], mode="clip")  # mode=clip أسرع من raise
        counts = np.bincount(idx, minlength=layers)
        bounds = np.concatenate(([0], np.cumsum(counts)))
        return [self._sorted[bounds[k] : bounds[k + 1]] for k in range(layers)]