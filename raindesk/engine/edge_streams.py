"""raindesk/engine/edge_streams.py

الغرض: جداول ماء تنساب على حافتي الشاشة اليسرى واليمنى توحي بماء يلتف حول إطار الشاشة.
المسؤوليات: توليد مسارات جيبية متمايلة لكل جدول، وتقدّمها بالزمن مع إزاحة العصف، وحبّات
    لامعة تنزلق على المسارات بذيل خافت، وتصدير المسارات والحبّات للرسم.
الاعتماديات: NumPy والمكتبة القياسية.
النمط التصميمي: Structure of Arrays مع حساب متجه للمسارات (نقاط لكل جدول في صف).
ملاحظات: سقف نقاط المسارات 600 لكل شاشة (يُزاد الفاصل بين العينات عند كثرة الجداول).
    كل جدول يُرسم كـ QPainterPath واحد في المرسِم، والتلاشي العلوي يطبَّق هناك بتدرّج لوني.
مثال: streams.configure(3, 0.35); streams.step(dt, gust); paths = streams.paths()
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np

from raindesk.engine.math_utils import clamp

_MARGIN_PX: Final[float] = 6.0  # px: أول جدول يبعد عن حافة الشاشة
_BAND_FRACTION: Final[float] = 0.06  # عرض شريط الحافة: 6% من عرض الشاشة
_BAND_MAX_PX: Final[float] = 120.0  # px: سقف عرض الشريط
_MIN_SPACING_PX: Final[float] = 1.0  # px: أقل مسافة بين جدولين متجاورين
_SAMPLE_STEP_PX: Final[float] = 24.0  # px: فاصل أخذ العينات على المسار
_MAX_PATH_POINTS: Final[int] = 600  # سقف نقاط كل المسارات في الشاشة
_MAX_COUNT_PER_EDGE: Final[int] = 8
_AMPLITUDE_MIN_PX: Final[float] = 2.0
_AMPLITUDE_MAX_PX: Final[float] = 7.0
_WAVE_K_MIN: Final[float] = 0.008  # rad/px
_WAVE_K_MAX: Final[float] = 0.02
_WAVE_W_MIN: Final[float] = 0.4  # rad/s
_WAVE_W_MAX: Final[float] = 1.2
_WIDTH_MIN_PX: Final[float] = 1.5
_WIDTH_MAX_PX: Final[float] = 3.0
_ALPHA_MIN: Final[float] = 0.4
_ALPHA_MAX: Final[float] = 1.0
_GUST_SHIFT_PX: Final[float] = 6.0  # px: إزاحة المسار لكل وحدة عصف
_BEADS_PER_STREAM: Final[int] = 2
_BEAD_SPEED_MIN: Final[float] = 90.0  # px/s
_BEAD_SPEED_MAX: Final[float] = 260.0
_BEAD_RESPAWN_MAX_PX: Final[float] = 120.0  # px: أقصى ارتفاع فوق الشاشة لإعادة بعث الحبة
_BEAD_RECYCLE_MARGIN_PX: Final[float] = 20.0  # px: الحبة تُعاد بعد تجاوز أسفل الشاشة بهذا القدر
_BEAD_BRIGHTNESS: Final[float] = 1.8  # معامل سطوع الحبة نسبةً لشفافية الجدول
_TRAIL_STEPS: Final[int] = 3  # عدد نقاط الذيل خلف كل حبة
_TRAIL_SPACING_PX: Final[float] = 9.0
_TOP_FADE_FRACTION: Final[float] = 0.10  # التلاشي على أعلى 10% من الارتفاع
_VISIBLE_ALPHA: Final[float] = 0.01
_TWO_PI: Final[float] = 2.0 * math.pi
_MIN_SIZE_PX: Final[float] = 1.0


@dataclass(slots=True)
class StreamPath:
    """مسار جدول واحد: points (n, 2) float32 (عرض على مخزن داخلي)، وأقصى شفافية، وسُمك القلم."""

    points: np.ndarray
    alpha: float
    width: float


class EdgeStreams:
    """جداول الحواف. الثوابت: عدد النقاط الكلي <= 600؛ كل العشوائية من rng الممرَّر."""

    def __init__(self, width: float, height: float, rng: np.random.Generator) -> None:
        self._rng = rng
        self._width = max(float(width), _MIN_SIZE_PX)
        self._height = max(float(height), _MIN_SIZE_PX)
        self._count = 0  # عدد الجداول لكل حافة (0 = لا جداول)
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
        """عدد الجداول لكل حافة (0 إلى 8) وشفافيتها (0 إلى 1)؛ تغيير العدد يعيد توليد الجداول."""
        count = min(max(int(count_per_edge), 0), _MAX_COUNT_PER_EDGE)
        self._opacity = clamp(opacity, 0.0, 1.0)
        if count != self._count:
            self._count = count
            self._build()

    def _build(self) -> None:
        """يولّد معاملات كل جدول (سعة وتردد وطور) ومصفوفات العينات والحبّات."""
        streams = 2 * self._count
        rng = self._rng
        self._streams = streams
        if streams == 0:
            self._points = np.zeros((0, 0, 2), np.float32)
            self._beads_out = np.zeros((0, 3), np.float32)
            return
        count, width, height = self._count, self._width, self._height
        band = min(_BAND_FRACTION * width, _BAND_MAX_PX)
        spacing = max((band - _MARGIN_PX) / count, _MIN_SPACING_PX)
        index = np.tile(np.arange(count), 2)  # فهرس الجدول داخل حافته
        right = np.repeat([False, True], count)
        offset = _MARGIN_PX + index * spacing
        self._base_x = np.where(right, width - offset, offset)  # اليمين مرآة اليسار
        self._amp = rng.uniform(_AMPLITUDE_MIN_PX, _AMPLITUDE_MAX_PX, streams)
        self._wave_k = rng.uniform(_WAVE_K_MIN, _WAVE_K_MAX, streams)
        self._wave_w = rng.uniform(_WAVE_W_MIN, _WAVE_W_MAX, streams)
        self._phase = rng.uniform(0.0, _TWO_PI, streams)
        self._line_width = rng.uniform(_WIDTH_MIN_PX, _WIDTH_MAX_PX, streams)
        self._alpha_mult = rng.uniform(_ALPHA_MIN, _ALPHA_MAX, streams)

        # سقف النقاط: نقلّل نقاط الجدول الواحد عند كثرة الجداول فيكبر فاصل العينات.
        wanted = math.ceil(height / _SAMPLE_STEP_PX) + 1
        per_stream = max(2, min(wanted, _MAX_PATH_POINTS // streams))
        self._ys = np.linspace(0.0, height, per_stream).astype(np.float32)
        self._points = np.zeros((streams, per_stream, 2), np.float32)
        self._points[:, :, 1] = self._ys

        self._bead_y = rng.uniform(-0.2 * height, height, (streams, _BEADS_PER_STREAM))
        self._bead_v = rng.uniform(_BEAD_SPEED_MIN, _BEAD_SPEED_MAX, (streams, _BEADS_PER_STREAM))
        max_beads = streams * _BEADS_PER_STREAM * (1 + _TRAIL_STEPS)  # الحبة ونقاط ذيلها
        self._beads_out = np.zeros((max_beads, 3), np.float32)

    # ------------------------------------------------------------------ التقدّم
    def _x_at(self, y: np.ndarray) -> np.ndarray:
        """x(y, t) = x_i + A_i sin(k_i y + w_i t + phi_i) + 6 G، لكل جدول (الصف) ولكل y في صفه."""
        phase = self._wave_k[:, None] * y + (self._wave_w * self._time + self._phase)[:, None]
        result: np.ndarray = (
            self._base_x[:, None] + self._amp[:, None] * np.sin(phase) + self._shift
        )
        return result

    def step(self, dt: float, gust: float) -> None:
        """يقدّم الزمن والموجات والحبّات؛ gust في [-1, 1] يزيح المسارات بـ 6 px * gust."""
        if self._streams == 0 or dt <= 0.0:
            return
        self._time += dt
        self._shift = _GUST_SHIFT_PX * clamp(gust, -1.0, 1.0)
        self._points[:, :, 0] = self._x_at(np.broadcast_to(self._ys, self._points.shape[:2]))
        self._bead_y += self._bead_v * dt
        done = self._bead_y > self._height + _BEAD_RECYCLE_MARGIN_PX
        if done.any():  # تعاد الحبّة فوق الشاشة بسرعة جديدة
            fresh = int(done.sum())
            self._bead_y[done] = -self._rng.uniform(0.0, _BEAD_RESPAWN_MAX_PX, fresh)
            self._bead_v[done] = self._rng.uniform(_BEAD_SPEED_MIN, _BEAD_SPEED_MAX, fresh)

    # ------------------------------------------------------------------ الإخراج
    def paths(self) -> list[StreamPath]:
        """مسار كل جدول: نقاط (n, 2) وأقصى شفافية وسُمك. القائمة فارغة إن كان العدد صفرًا."""
        if self._streams == 0 or self._opacity <= 0.0:
            return []
        return [
            StreamPath(
                points=self._points[i],
                alpha=float(self._opacity * self._alpha_mult[i]),
                width=float(self._line_width[i]),
            )
            for i in range(self._streams)
        ]

    def beads(self) -> np.ndarray:
        """(k, 3) float32: x, y, alpha لكل حبة وذيلها الخافت؛ عرض صالح حتى الاستدعاء التالي."""
        if self._streams == 0 or self._opacity <= 0.0:
            return self._beads_out[:0]
        offsets = np.arange(1 + _TRAIL_STEPS) * _TRAIL_SPACING_PX  # الرأس ثم الذيل
        y = self._bead_y[:, :, None] - offsets[None, None, :]  # (streams, beads, 1 + trail)
        flat_y = y.reshape(self._streams, -1)
        x = self._x_at(flat_y).reshape(y.shape)
        head_alpha = np.minimum(1.0, self._opacity * self._alpha_mult * _BEAD_BRIGHTNESS)
        trail_fade = 1.0 - np.arange(1 + _TRAIL_STEPS) / (1.0 + _TRAIL_STEPS)
        alpha = head_alpha[:, None, None] * trail_fade[None, None, :]
        alpha = alpha * np.clip(y / (_TOP_FADE_FRACTION * self._height), 0.0, 1.0)
        visible = (alpha > _VISIBLE_ALPHA) & (y <= self._height)
        count = int(visible.sum())
        out = self._beads_out[:count]
        out[:, 0] = x[visible]
        out[:, 1] = y[visible]
        out[:, 2] = alpha[visible]
        return out
