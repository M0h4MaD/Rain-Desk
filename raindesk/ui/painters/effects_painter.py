"""raindesk/ui/painters/effects_painter.py

الغرض: رسم المؤثرات: تظليل الأجواء، وجداول الحواف، والرذاذ، ووميض البرق.
المسؤوليات: تحويل مصفوفات المحرك إلى أوامر QPainter بدفعات: تجميع الشفافية في عدد قليل
    من الدلاء (buckets) فيُستعمل قلم واحد وأمر رسم واحد لكل دلو بدل قلم لكل جسيم.
الاعتماديات: PySide6 وNumPy وraindesk.engine.
النمط التصميمي: Batching بالتكميم (quantization) كما في DD-05؛ المرسِم بلا حالة.
ملاحظات: ترتيب الرسم الذي يضبطه OverlayWindow: التظليل ثم ماء الحواف ثم المطر ثم الرذاذ ثم
    البرق. شفافية الرذاذ تُضرب بـ drop_opacity كي تتبع إعداد المستخدم.
مثال: paint_splashes(painter, splashes, params)
"""

from __future__ import annotations

from typing import Final

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from raindesk.engine.edge_streams import EdgeStreams
from raindesk.engine.math_utils import clamp, lerp
from raindesk.engine.params import EngineParams
from raindesk.engine.splash_system import SplashSystem
from raindesk.engine.weather_fsm import LIGHTNING_PEAK_MAX

_ALPHA_BUCKETS: Final[int] = 5  # عدد دلاء الشفافية (5 مستويات تكفي لتلاشٍ ناعم لعين المشاهد)
_RIPPLE_PEN_PX: Final[float] = 1.2  # px: سُمك خط التموّج
_MIN_TRAIL_POINTS: Final[int] = 2  # أقل عدد نقاط لرسم أثر
_MIN_TRAIL_SPAN_PX: Final[float] = 2.0  # px: أقل امتداد رأسي للأثر
_TRAIL_STOPS: Final[tuple[float, ...]] = (0.0, 0.35, 0.7, 1.0)  # مواضع تدرّج شفافية الأثر
_RESIDUE_BODY_ALPHA: Final[float] = 0.45  # شفافية جسم الحبيبة نسبةً للدلو
_RESIDUE_SAG: Final[float] = 1.15  # استطالة الحبيبة رأسيًا
_GLINT_ALPHA: Final[float] = 0.85
_GLINT_PEN_PX: Final[float] = 1.0  # px: نقطة اللمعان على الحبيبة
_GLINT_OFFSET: Final[float] = 0.3
_FOCUS_OFFSET: Final[float] = 0.35  # إزاحة بؤرة التدرّج نحو الأعلى واليسار (اتجاه الضوء)
_CORE_ALPHA: Final[float] = 0.45  # أوزان شفافية طبقات جسم القطرة نسبةً لشفافية القطرة
_BODY_LIGHT_ALPHA: Final[float] = 0.30
_BODY_ALPHA: Final[float] = 0.26
_RIM_ALPHA: Final[float] = 0.62
_RIM_RGB: Final[tuple[int, int, int]] = (14, 22, 40)  # حافة داكنة: انكسار الضوء عند طرف القطرة
_HIGHLIGHT_ALPHA: Final[float] = 0.95
_HIGHLIGHT_DX: Final[float] = 0.32  # موضع اللمعان العلوي نسبةً لنصف القطر
_HIGHLIGHT_DY: Final[float] = 0.38
_HIGHLIGHT_SIZE_X: Final[float] = 0.30
_HIGHLIGHT_SIZE_Y: Final[float] = 0.22
_CAUSTIC_ALPHA: Final[float] = 0.40  # بقعة الضوء المنكسر عند أسفل القطرة
_CAUSTIC_DX: Final[float] = 0.22
_CAUSTIC_DY: Final[float] = 0.50
_CAUSTIC_SIZE: Final[float] = 0.20
_LIGHTEN_MIX: Final[float] = 0.45  # مزج لون الحبّات مع الأبيض لتبدو لامعة
_FLASH_COLOR: Final[str] = "#DDE8FF"  # لون وميض البرق
_MIN_VISIBLE_ALPHA: Final[float] = 0.002  # أدنى شفافية تستحق الرسم
_WHITE: Final[int] = 255

def _bucket_ids(alpha: np.ndarray) -> np.ndarray:
    """فهرس الدلو (0 إلى 4) لكل قيمة شفافية في [0, 1]."""
    return np.minimum((alpha * _ALPHA_BUCKETS).astype(np.int32), _ALPHA_BUCKETS - 1)

def _bucket_alpha(bucket: int, opacity: float) -> float:
    """شفافية الدلو: منتصف مجاله مضروبًا في عتامة القطرات (إعداد المستخدم)."""
    return clamp((bucket + 0.5) / _ALPHA_BUCKETS * opacity, 0.0, 1.0)

def _lighten(color: QColor) -> QColor:
    return QColor(
        round(lerp(color.red(), _WHITE, _LIGHTEN_MIX)),
        round(lerp(color.green(), _WHITE, _LIGHTEN_MIX)),
        round(lerp(color.blue(), _WHITE, _LIGHTEN_MIX)),
    )

def paint_mood(
    painter: QPainter, width: float, height: float, color_hex: str, opacity: float
) -> None:
    """تظليل ملوّن فوق الشاشة كلها؛ يُرسم قبل المطر. لا شيء إن كانت العتامة صفرًا."""
    alpha = clamp(opacity, 0.0, 1.0)
    if alpha <= _MIN_VISIBLE_ALPHA:
        return
    color = QColor(color_hex)
    color.setAlphaF(alpha)
    painter.fillRect(QRectF(0.0, 0.0, width, height), color)

def _add_smooth_edge(path: QPainterPath, points: list[tuple[float, float]]) -> None:
    """يضيف حافة ناعمة: منحنيات تربيعية بنقاط التحكم عند العيّنات والنهايات عند منتصفاتها.

    عند كثرة المسارات تقلّ عيّنات الأثر (سقف 600 نقطة) فتظهر زوايا حادة لو وُصلت بخطوط مستقيمة.
    """
    path.lineTo(*points[0])
    for (cx, cy), (nx, ny) in zip(points[1:-1], points[2:], strict=True):
        path.quadTo(cx, cy, (cx + nx) / 2.0, (cy + ny) / 2.0)
    path.lineTo(*points[-1])


def _trail_path(x: np.ndarray, y: np.ndarray, half: np.ndarray) -> QPainterPath:
    """شكل أثر مبلّل: حافة يسرى من الرأس إلى الذيل ثم اليمنى راجعةً، فيدقّ الأثر نحو الذيل."""
    xs, ys, ws = x.tolist(), y.tolist(), half.tolist()
    left = [(px - w, py) for px, py, w in zip(xs, ys, ws, strict=True)]
    right = [(px + w, py) for px, py, w in zip(xs, ys, ws, strict=True)]
    path = QPainterPath()
    path.moveTo(*left[0])
    _add_smooth_edge(path, left)
    _add_smooth_edge(path, right[::-1])
    path.closeSubpath()
    return path


def _paint_trails(painter: QPainter, streams: EdgeStreams, tint: QColor) -> None:
    """آثار الماء: مضلّع لكل قطرة بتدرّج شفافية رأسي من الذيل (خافت) إلى الرأس (أوضح)."""
    trails = streams.trails()
    painter.setPen(Qt.PenStyle.NoPen)
    for i in np.flatnonzero(trails.count >= _MIN_TRAIL_POINTS).tolist():
        n = int(trails.count[i])
        xs, ys = trails.x[i, :n], trails.y[i, :n]
        alpha = trails.alpha[i, :n]
        top, bottom = float(ys[-1]), float(ys[0])  # الذيل أعلى (y أصغر) والرأس أسفل
        if bottom - top < _MIN_TRAIL_SPAN_PX:
            continue
        gradient = QLinearGradient(0.0, top, 0.0, bottom)
        for stop in _TRAIL_STOPS:
            # alpha مرتّبة من الرأس (0) إلى الذيل، فنقطة الذيل في التدرّج = 1 - stop.
            a = float(np.interp(stop * (n - 1), np.arange(n), alpha))
            color = QColor(tint)
            color.setAlphaF(clamp(a, 0.0, 1.0))
            gradient.setColorAt(1.0 - stop, color)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(_trail_path(xs, ys, trails.half_width[i, :n]))


def _paint_residue(painter: QPainter, streams: EdgeStreams, tint: QColor) -> None:
    """الحبيبات المتخلّفة: دوائر صغيرة مجمّعة بدلاء الشفافية مع نقطة لمعان لكل دلو."""
    beads = streams.residue()
    if beads.shape[0] == 0:
        return
    ids = _bucket_ids(beads[:, 3])
    for bucket in range(_ALPHA_BUCKETS):
        selected = beads[ids == bucket]
        if selected.shape[0] == 0:
            continue
        alpha = (bucket + 0.5) / _ALPHA_BUCKETS
        fill = QColor(tint)
        fill.setAlphaF(alpha * _RESIDUE_BODY_ALPHA)
        path = QPainterPath()
        for x, y, r, _a in selected.tolist():
            path.addEllipse(QPointF(x, y), r, r * _RESIDUE_SAG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPath(path)
        glint = QColor(_WHITE, _WHITE, _WHITE)
        glint.setAlphaF(alpha * _GLINT_ALPHA)
        painter.setPen(QPen(glint, _GLINT_PEN_PX, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPoints(
            [QPointF(x - r * _GLINT_OFFSET, y - r * _GLINT_OFFSET) for x, y, r, _a in selected.tolist()]
        )


def _paint_drop(painter: QPainter, x: float, y: float, rx: float, ry: float, alpha: float,
                tint: QColor) -> None:
    """قطرة واحدة تُرسم بثلاث طبقات: جسم بتدرّج دائري (حافة داكنة)، لمعان علوي، وانكسار سفلي."""
    focus = QPointF(x - _FOCUS_OFFSET * rx, y - _FOCUS_OFFSET * ry)
    gradient = QRadialGradient(QPointF(x, y), max(rx, ry), focus)
    stops = (
        (0.0, QColor(_WHITE, _WHITE, _WHITE), _CORE_ALPHA),
        (0.30, _lighten(tint), _BODY_LIGHT_ALPHA),
        (0.78, tint, _BODY_ALPHA),
        (1.0, QColor(*_RIM_RGB), _RIM_ALPHA),
    )
    for position, color, weight in stops:
        shaded = QColor(color)
        shaded.setAlphaF(clamp(alpha * weight, 0.0, 1.0))
        gradient.setColorAt(position, shaded)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    centre = QPointF(x, y)
    painter.drawEllipse(centre, rx, ry)

    highlight = QColor(_WHITE, _WHITE, _WHITE)
    highlight.setAlphaF(clamp(alpha * _HIGHLIGHT_ALPHA, 0.0, 1.0))
    painter.setBrush(highlight)
    painter.drawEllipse(
        QPointF(x - _HIGHLIGHT_DX * rx, y - _HIGHLIGHT_DY * ry),
        _HIGHLIGHT_SIZE_X * rx, _HIGHLIGHT_SIZE_Y * ry,
    )
    caustic = QColor(_WHITE, _WHITE, _WHITE)
    caustic.setAlphaF(clamp(alpha * _CAUSTIC_ALPHA, 0.0, 1.0))
    painter.setBrush(caustic)
    painter.drawEllipse(
        QPointF(x + _CAUSTIC_DX * rx, y + _CAUSTIC_DY * ry),
        _CAUSTIC_SIZE * rx, _CAUSTIC_SIZE * ry,
    )


def paint_edge_streams(
    painter: QPainter, streams: EdgeStreams, params: EngineParams, height: float
) -> None:
    """ماء الحواف: آثار مبلّلة، فحبيبات متخلّفة، فقطرات بتظليل زجاجي (يُرسم بعد التظليل وقبل المطر).

    height يُبقى في التوقيع للتوافق؛ التلاشي العلوي صار محسوبًا في المحرك لكل عيّنة.
    """
    del height
    red, green, blue = params.color_rgb
    tint = QColor(red, green, blue)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _paint_trails(painter, streams, tint)
    _paint_residue(painter, streams, tint)
    for x, y, rx, ry, alpha, _sliding in streams.drops().tolist():
        _paint_drop(painter, x, y, rx, ry, alpha, tint)


def paint_splashes(painter: QPainter, splashes: SplashSystem, params: EngineParams) -> None:
    """التموّجات (إهليلجات بدون تعبئة) ثم جسيمات الرذاذ (نقاط مستديرة)، مجمّعة بدلاء الشفافية."""
    red, green, blue = params.color_rgb
    color = QColor(red, green, blue)

    ripples = splashes.ripples()
    if ripples.shape[0]:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        ids = _bucket_ids(ripples[:, 4])
        for bucket in range(_ALPHA_BUCKETS):
            selected = ripples[ids == bucket]
            if selected.shape[0] == 0:
                continue
            color.setAlphaF(_bucket_alpha(bucket, params.drop_opacity))
            painter.setPen(QPen(color, _RIPPLE_PEN_PX))
            path = QPainterPath()
            for x, y, rx, ry, _a in selected.tolist():
                path.addEllipse(QPointF(x, y), rx, ry)
            painter.drawPath(path)

    sprays = splashes.sprays()
    if sprays.shape[0]:
        ids = _bucket_ids(sprays[:, 3])
        for bucket in range(_ALPHA_BUCKETS):
            selected = sprays[ids == bucket]
            if selected.shape[0] == 0:
                continue
            color.setAlphaF(_bucket_alpha(bucket, params.drop_opacity))
            # سُمك القلم = متوسط أحجام جسيمات الدلو (1 إلى 2 px) بدل قلم لكل جسيم.
            size = float(selected[:, 2].mean())
            painter.setPen(QPen(color, size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPoints([QPointF(x, y) for x, y, _s, _a in selected.tolist()])

def paint_lightning(painter: QPainter, width: float, height: float, alpha: float) -> None:
    """وميض البرق: تعبئة شاملة بلون #DDE8FF؛ الشدة مقيَّدة بسقف الأمان مهما كانت القيمة الواردة."""
    level = clamp(alpha, 0.0, LIGHTNING_PEAK_MAX)
    if level <= _MIN_VISIBLE_ALPHA:
        return
    color = QColor(_FLASH_COLOR)
    color.setAlphaF(level)
    painter.fillRect(QRectF(0.0, 0.0, width, height), color)
