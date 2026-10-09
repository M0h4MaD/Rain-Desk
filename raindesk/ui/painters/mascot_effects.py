"""raindesk/ui/painters/mascot_effects.py

الغرض: رسم المؤثرات الصغيرة التي تطفو فوق رأس Drip وتعبّر عن شعوره: قلوب (تمسيح)، وقطرة
    عرق (خوف)، وعلامة تعجب (فزع)، وحروف Z (نوم)، وبريق (فرح أو التقاط مطر).
المسؤوليات: paint_effect فقط، بإحداثيات موحَّدة المقياس (لا تتشوه مع ضغط الجسم وتمدده)؛
    الحركة دالة نقية في mascot.effect_t (عمر المؤثر بالثواني) فلا حالة في المرسِم.
الاعتماديات: PySide6.QtCore وPySide6.QtGui وraindesk.engine.mascot.
النمط التصميمي: Painter Function (بلا حالة).
ملاحظات: الأصل (0, 0) فوق قمة الرأس مباشرة، والوحدة = ارتفاع الجسم الأساسي.
مثال: paint_effect(painter, mascot)
"""

from __future__ import annotations

import math
from typing import Final

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from raindesk.engine.mascot import Effect, Mascot

_HEART: Final[QColor] = QColor("#FF5C8A")
_SWEAT: Final[QColor] = QColor("#BFE9FF")
_ALERT: Final[QColor] = QColor("#FF5A3C")
_ZZZ: Final[QColor] = QColor("#8FB8FF")
_STAR: Final[QColor] = QColor("#FFF3B0")
_HEART_COUNT: Final[int] = 3
_HEART_RISE: Final[float] = 0.55  # ارتفاع صعود القلب بوحدة الجسم
_HEART_PERIOD_S: Final[float] = 1.4  # s: عمر القلب الواحد
_ALERT_POP_S: Final[float] = 0.12  # s: زمن تكبير علامة التعجب عند ظهورها
_ZZZ_COUNT: Final[int] = 3
_ZZZ_PERIOD_S: Final[float] = 2.4  # s: عمر الحرف الواحد
_STAR_COUNT: Final[int] = 4
_STAR_RADIUS: Final[float] = 0.62  # نصف قطر دائرة البريق حول الرأس
_STAR_TWINKLE_HZ: Final[float] = 2.5
_LINE_WIDTH: Final[float] = 0.03
_TWO_PI: Final[float] = 2.0 * math.pi


def _heart_path(size: float) -> QPainterPath:
    """قلب بمنحنيين مكعبين، بعرض نحو size."""
    path = QPainterPath()
    path.moveTo(0.0, 0.30 * size)
    path.cubicTo(-0.55 * size, -0.12 * size, -0.22 * size, -0.52 * size, 0.0, -0.20 * size)
    path.cubicTo(0.22 * size, -0.52 * size, 0.55 * size, -0.12 * size, 0.0, 0.30 * size)
    return path


def _paint_hearts(painter: QPainter, t: float) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    for index in range(_HEART_COUNT):
        life = (t / _HEART_PERIOD_S + index / _HEART_COUNT) % 1.0
        color = QColor(_HEART)
        color.setAlphaF(math.sin(math.pi * life))  # يظهر ثم يتلاشى
        painter.setBrush(color)
        painter.save()
        painter.translate(
            (index - 1) * 0.16 + 0.05 * math.sin(_TWO_PI * (life + index)), -life * _HEART_RISE
        )
        painter.drawPath(_heart_path(0.16 + 0.04 * (index % 2)))
        painter.restore()


def _paint_sweat(painter: QPainter, t: float) -> None:
    """قطرة عرق تنزلق على جانب الرأس."""
    slide = (t * 0.9) % 1.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_SWEAT)
    painter.save()
    painter.translate(0.30, 0.18 + 0.2 * slide)
    path = QPainterPath()
    path.moveTo(0.0, -0.06)
    path.cubicTo(0.0, -0.02, 0.045, 0.0, 0.045, 0.03)
    path.cubicTo(0.045, 0.065, -0.045, 0.065, -0.045, 0.03)
    path.cubicTo(-0.045, 0.0, 0.0, -0.02, 0.0, -0.06)
    painter.drawPath(path)
    painter.restore()


def _paint_alert(painter: QPainter, t: float) -> None:
    """علامة تعجب تكبر بتجاوز بسيط (overshoot) عند ظهورها."""
    pop = min(1.0, t / _ALERT_POP_S)
    scale = pop * (1.0 + 0.25 * math.sin(math.pi * pop))
    painter.save()
    painter.translate(0.0, -0.14)
    painter.scale(scale, scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_ALERT)
    painter.drawRoundedRect(QRectF(-0.028, -0.13, 0.056, 0.15), 0.028, 0.028)
    painter.drawEllipse(QPointF(0.0, 0.06), 0.032, 0.032)
    painter.restore()


def _paint_zzz(painter: QPainter, t: float) -> None:
    """حروف Z صاعدة تكبر وتتلاشى (نوم)."""
    for index in range(_ZZZ_COUNT):
        life = (t / _ZZZ_PERIOD_S + index / _ZZZ_COUNT) % 1.0
        color = QColor(_ZZZ)
        color.setAlphaF(math.sin(math.pi * life))
        size = 0.05 + 0.05 * life
        path = QPainterPath()
        path.moveTo(-size, -size)
        path.lineTo(size, -size)
        path.lineTo(-size, size)
        path.lineTo(size, size)
        pen = QPen(QBrush(color), _LINE_WIDTH)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.save()
        painter.translate(0.18 + life * 0.22, -life * 0.5)
        painter.drawPath(path)
        painter.restore()


def _paint_sparkles(painter: QPainter, t: float) -> None:
    """نجوم رباعية تومض حول الرأس."""
    painter.setPen(Qt.PenStyle.NoPen)
    for index in range(_STAR_COUNT):
        angle = _TWO_PI * index / _STAR_COUNT + 0.7
        twinkle = 0.5 + 0.5 * math.sin(_TWO_PI * _STAR_TWINKLE_HZ * t + index * 1.7)
        size = 0.035 + 0.05 * twinkle
        color = QColor(_STAR)
        color.setAlphaF(0.35 + 0.65 * twinkle)
        painter.setBrush(color)
        painter.save()
        painter.translate(
            _STAR_RADIUS * math.cos(angle), 0.45 - _STAR_RADIUS * 0.85 * math.sin(angle)
        )
        path = QPainterPath()
        path.moveTo(0.0, -size)
        path.quadTo(0.0, 0.0, size, 0.0)
        path.quadTo(0.0, 0.0, 0.0, size)
        path.quadTo(0.0, 0.0, -size, 0.0)
        path.quadTo(0.0, 0.0, 0.0, -size)
        painter.drawPath(path)
        painter.restore()


def paint_effect(painter: QPainter, mascot: Mascot) -> None:
    """يرسم مؤثر الحالة الحالية (إن وُجد) في فضاء موحَّد المقياس فوق الرأس."""
    effect, t = mascot.effect, mascot.effect_t
    if effect is Effect.HEARTS:
        _paint_hearts(painter, t)
    elif effect is Effect.SWEAT:
        _paint_sweat(painter, t)
    elif effect is Effect.ALERT:
        _paint_alert(painter, t)
    elif effect is Effect.ZZZ:
        _paint_zzz(painter, t)
    elif effect is Effect.SPARKLE:
        _paint_sparkles(painter, t)
