"""raindesk/ui/painters/effects_painter.py

الغرض: رسم المؤثرات: تظليل الأجواء، وجداول الحواف، والرذاذ، ووميض البرق.
المسؤوليات: تحويل مصفوفات المحرك إلى أوامر QPainter بدفعات: تجميع الشفافية في عدد قليل
    من الدلاء (buckets) فيُستعمل قلم واحد وأمر رسم واحد لكل دلو بدل قلم لكل جسيم.
الاعتماديات: PySide6 وNumPy وraindesk.engine.
النمط التصميمي: Batching بالتكميم (quantization) كما في DD-05؛ المرسِم بلا حالة.
ملاحظات: ترتيب الرسم الذي يضبطه OverlayWindow: التظليل ثم الجداول ثم المطر ثم الرذاذ ثم
    البرق. شفافية الرذاذ تُضرب بـ drop_opacity كي تتبع إعداد المستخدم.
مثال: paint_splashes(painter, splashes, params)
"""

from __future__ import annotations

from typing import Final

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen

from raindesk.engine.edge_streams import EdgeStreams
from raindesk.engine.math_utils import clamp, lerp
from raindesk.engine.params import EngineParams
from raindesk.engine.splash_system import SplashSystem
from raindesk.engine.weather_fsm import LIGHTNING_PEAK_MAX

_ALPHA_BUCKETS: Final[int] = 5  # عدد دلاء الشفافية (5 مستويات تكفي لتلاشٍ ناعم لعين المشاهد)
_RIPPLE_PEN_PX: Final[float] = 1.2  # px: سُمك خط التموّج
_BEAD_PEN_PX: Final[float] = 3.0  # px: قطر الحبة اللامعة
_LIGHTEN_MIX: Final[float] = 0.45  # مزج لون الحبّات مع الأبيض لتبدو لامعة
_TOP_FADE_FRACTION: Final[float] = 0.10  # التلاشي العلوي للجداول: أعلى 10% من الارتفاع
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


def paint_edge_streams(
    painter: QPainter, streams: EdgeStreams, params: EngineParams, height: float
) -> None:
    """جداول الحواف (QPainterPath لكل جدول بتدرّج يتلاشى في أعلى الشاشة) ثم حبّاتها اللامعة."""
    paths = streams.paths()
    if not paths:
        return
    red, green, blue = params.color_rgb
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for stream in paths:
        gradient = QLinearGradient(0.0, 0.0, 0.0, height)
        solid = QColor(red, green, blue)
        solid.setAlphaF(clamp(stream.alpha, 0.0, 1.0))
        gradient.setColorAt(0.0, QColor(red, green, blue, 0))  # شفاف عند أعلى الشاشة
        gradient.setColorAt(_TOP_FADE_FRACTION, solid)
        gradient.setColorAt(1.0, solid)
        painter.setPen(
            QPen(
                QBrush(gradient), stream.width, Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
            )
        )
        points = stream.points.tolist()
        path = QPainterPath()
        path.moveTo(points[0][0], points[0][1])
        for x, y in points[1:]:
            path.lineTo(x, y)
        painter.drawPath(path)

    beads = streams.beads()
    if beads.shape[0] == 0:
        return
    bead_color = _lighten(QColor(red, green, blue))
    ids = _bucket_ids(beads[:, 2])
    for bucket in range(_ALPHA_BUCKETS):
        selected = beads[ids == bucket]
        if selected.shape[0] == 0:
            continue
        bead_color.setAlphaF((bucket + 0.5) / _ALPHA_BUCKETS)  # شفافية الحبة محسوبة في المحرك
        painter.setPen(
            QPen(bead_color, _BEAD_PEN_PX, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPoints([QPointF(x, y) for x, y, _a in selected.tolist()])


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