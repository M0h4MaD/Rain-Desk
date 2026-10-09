"""raindesk/ui/painters/mascot_painter.py

الغرض: رسم الشخصية Drip بشكل لطيف بدل التلوين المسطّح: جسم قطرة ممتلئ بتظليل متعدد الطبقات
    (ضوء حافة وظل داخلي سفلي وضوء منعكس ولمعة)، وذراعان وقدمان، وظل على الأرض، ثم الوجه
    (mascot_face) والمؤثرات (mascot_effects).
المسؤوليات: دالة paint_mascot فقط؛ لا تغيّر حالة الشخصية ولا تحتفظ بحالة بين الاستدعاءات.
الاعتماديات: PySide6.QtCore وPySide6.QtGui وraindesk.engine.mascot وmascot_face وmascot_effects.
النمط التصميمي: Painter Function (منطق في engine ورسم هنا).
ملاحظات: الرسم في فضاء وحدة: ارتفاع الجسم 1 وعرضه 0.92 وقدمه عند y = 0 وقمته عند y = -1،
    ثم يُكبَّر بـ (base_height * scale_x، base_height * scale_y)، فيعمل الضغط والتمدد على
    الجسم والوجه معًا ويبقى القدمان على الأرض. الطبقات تُقصّ بمسار الجسم (clip) كي لا تتسرب.
    المؤثرات تُرسم بعد استعادة التحويل بمقياس موحَّد حتى لا تتشوه مع الضغط.
مثال: paint_mascot(painter, mascot, mascot.height_px)
"""

from __future__ import annotations

import math
from typing import Final

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

from raindesk.engine.mascot import Mascot
from raindesk.ui.painters.mascot_effects import paint_effect
from raindesk.ui.painters.mascot_face import paint_face

_RADIUS: Final[float] = 0.46  # نصف عرض الجسم (فضاء الوحدة) = BODY_WIDTH_RATIO / 2
_KAPPA: Final[float] = 0.5523  # 4/3 * (sqrt(2) - 1): تقريب بيزيه لربع دائرة
_SHADOW_ALPHA: Final[int] = 70
_SHADOW_FADE_PX: Final[float] = 140.0  # px: الارتفاع الذي يخف عنده الظل إلى أدناه
_SHADOW_MIN_FACTOR: Final[float] = 0.35
_SHADOW_RX: Final[float] = 0.40  # نصف عرض الظل نسبة إلى ارتفاع الجسم
_SHADOW_RY: Final[float] = 0.075
_FOOT_X: Final[float] = 0.17
_FOOT_RX: Final[float] = 0.115
_FOOT_RY: Final[float] = 0.07
_FOOT_LIFT: Final[float] = 0.075  # أقصى رفع للقدم أثناء الخطوة
_SHOULDER_X: Final[float] = 0.41
_SHOULDER_Y: Final[float] = -0.34
_ARM_LENGTH: Final[float] = 0.22
_ARM_WIDTH: Final[float] = 0.105
_RIM_WIDTH: Final[float] = 0.034

_BODY_STOPS: Final[tuple[tuple[float, str], ...]] = (
    (0.0, "#E2F6FF"),
    (0.30, "#9ADAFB"),
    (0.70, "#52AAEC"),
    (1.0, "#2C74C6"),
)
_LIMB_LIGHT: Final[QColor] = QColor("#6FBFF4")
_LIMB_DARK: Final[QColor] = QColor("#2F7FCF")
_SHADE_BOTTOM: Final[QColor] = QColor(22, 72, 156, 105)
_BOUNCE_LIGHT: Final[QColor] = QColor(170, 236, 255, 120)


def _build_body_path() -> QPainterPath:
    """جسم قطرة ممتلئ بأربعة منحنيات مكعبة، متماثل حول المحور الرأسي.

    أعرض نقطة عند y = -0.46 (نصف القطر 0.46) والنصف السفلي ربع دائرتين بالثابت kappa؛
    المماسات رأسية عند أعرض نقطة فيمر المنحنيان بسلاسة (استمرارية G1). الرأس مدوَّر قليلًا.
    """
    r = _RADIUS
    path = QPainterPath()
    path.moveTo(0.0, -1.0)
    path.cubicTo(0.045, -0.88, r, -0.76, r, -r)
    path.cubicTo(r, -r + r * _KAPPA, r * _KAPPA, 0.0, 0.0, 0.0)
    path.cubicTo(-r * _KAPPA, 0.0, -r, -r + r * _KAPPA, -r, -r)
    path.cubicTo(-r, -0.76, -0.045, -0.88, 0.0, -1.0)
    path.closeSubpath()
    return path


_BODY_PATH: Final[QPainterPath] = _build_body_path()


def _limb_brush(center: QPointF, radius: float) -> QRadialGradient:
    gradient = QRadialGradient(center, radius)
    gradient.setColorAt(0.0, _LIMB_LIGHT)
    gradient.setColorAt(1.0, _LIMB_DARK)
    return gradient


def _paint_shadow(painter: QPainter, mascot: Mascot, height_px: float) -> None:
    """ظل بيضاوي على الأرض يتقلص ويخفت كلما ارتفعت الشخصية (إيحاء بالعمق)."""
    lift = max(0.0, mascot.ground_y - mascot.y)
    fade = 1.0 - (1.0 - _SHADOW_MIN_FACTOR) * min(1.0, lift / _SHADOW_FADE_PX)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, round(_SHADOW_ALPHA * fade)))
    radius_x = _SHADOW_RX * height_px * abs(mascot.scale_x) * (0.6 + 0.4 * fade)
    painter.drawEllipse(QPointF(mascot.x, mascot.ground_y), radius_x, _SHADOW_RY * height_px)


def _paint_feet(painter: QPainter, mascot: Mascot) -> None:
    """قدمان صغيرتان تتناوبان الارتفاع أثناء المشي والجري (خلف الجسم فتبرزان من أسفله)."""
    painter.setPen(Qt.PenStyle.NoPen)
    for index, side in enumerate((-1.0, 1.0)):
        lift = mascot.gait * max(0.0, math.sin(mascot.foot_phase + index * math.pi)) * _FOOT_LIFT
        center = QPointF(side * _FOOT_X, -_FOOT_RY * 0.55 - lift)
        painter.setBrush(_limb_brush(QPointF(center.x(), center.y() - 0.02), _FOOT_RX * 1.3))
        painter.drawEllipse(center, _FOOT_RX, _FOOT_RY)


def _paint_arms(painter: QPainter, mascot: Mascot) -> None:
    """ذراعان قصيرتان تدوران حول الكتف؛ الزاوية 0 تتدلى و90 أفقية و180 مرفوعة للأعلى."""
    painter.setPen(Qt.PenStyle.NoPen)
    for side, angle in ((-1.0, mascot.arm_l), (1.0, mascot.arm_r)):
        painter.save()
        painter.translate(side * _SHOULDER_X, _SHOULDER_Y)
        painter.rotate(-side * angle)  # +y (للأسفل) تدور إلى اتجاه الذراع
        center = QPointF(0.0, _ARM_LENGTH / 2.0)
        painter.setBrush(_limb_brush(QPointF(0.0, center.y() - 0.03), _ARM_LENGTH * 0.75))
        painter.drawEllipse(center, _ARM_WIDTH / 2.0, _ARM_LENGTH / 2.0)
        painter.restore()


def _paint_body(painter: QPainter) -> None:
    """الجسم: تدرج شعاعي ثم ظل داخلي سفلي وضوء منعكس ولمعة وضوء حافة، كلها داخل المسار."""
    base = QRadialGradient(QPointF(-0.14, -0.64), 0.95)
    for position, color in _BODY_STOPS:
        base.setColorAt(position, QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(base)
    painter.drawPath(_BODY_PATH)

    painter.save()
    painter.setClipPath(_BODY_PATH)
    transparent = QColor(_SHADE_BOTTOM)
    transparent.setAlpha(0)
    shade = QLinearGradient(QPointF(0.0, -0.50), QPointF(0.0, 0.0))  # ظل داخلي أسفل الجسم
    shade.setColorAt(0.0, transparent)
    shade.setColorAt(1.0, _SHADE_BOTTOM)
    painter.setBrush(shade)
    painter.drawRect(QRectF(-_RADIUS, -0.5, 2 * _RADIUS, 0.5))
    bounce = QRadialGradient(QPointF(0.24, -0.07), 0.30)  # ضوء منعكس من الأرض
    bounce.setColorAt(0.0, _BOUNCE_LIGHT)
    bounce.setColorAt(1.0, QColor(170, 236, 255, 0))
    painter.setBrush(bounce)
    painter.drawRect(QRectF(-0.1, -0.4, _RADIUS + 0.2, 0.45))
    rim = QLinearGradient(QPointF(-_RADIUS, -0.9), QPointF(_RADIUS, 0.0))  # ضوء الحافة
    rim.setColorAt(0.0, QColor(255, 255, 255, 215))
    rim.setColorAt(0.55, QColor(255, 255, 255, 40))
    rim.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QBrush(rim), _RIM_WIDTH))
    painter.drawPath(_BODY_PATH)
    painter.setPen(Qt.PenStyle.NoPen)  # لمعة كبيرة ناعمة ونقطة صغيرة أعلى اليسار (داخل الجسم)
    gloss = QRadialGradient(QPointF(0.0, 0.0), 0.16)
    gloss.setColorAt(0.0, QColor(255, 255, 255, 215))
    gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.save()
    painter.translate(-0.19, -0.62)
    painter.rotate(-24.0)
    painter.scale(0.55, 1.0)
    painter.setBrush(gloss)
    painter.drawEllipse(QPointF(0.0, 0.0), 0.16, 0.16)
    painter.restore()
    painter.setBrush(QColor(255, 255, 255, 200))
    painter.drawEllipse(QPointF(-0.115, -0.76), 0.024, 0.024)
    painter.restore()


def paint_mascot(painter: QPainter, mascot: Mascot, base_height_px: float) -> None:
    """يرسم Drip إن كانت ظاهرة؛ لا يغيّر الشخصية ويستعيد حالة الرسام عند الانتهاء.

    Args:
        painter: رسام نشط على نافذة المضيف. mascot: الحالة الحالية.
        base_height_px: ارتفاع الجسم بالبكسل المنطقي قبل الضغط والتمدد.
    التعقيد: O(1)؛ بضع عشرات من العمليات الرسومية فقط (وتُستدعى فقط عند ظهورها).
    """
    if not mascot.visible or base_height_px <= 0.0:
        return
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _paint_shadow(painter, mascot, base_height_px)
        painter.save()
        painter.translate(mascot.x, mascot.y)  # أصل الإحداثيات عند القدم
        painter.scale(base_height_px * mascot.scale_x, base_height_px * mascot.scale_y)
        _paint_feet(painter, mascot)
        _paint_arms(painter, mascot)
        _paint_body(painter)
        paint_face(painter, mascot)
        painter.restore()
        painter.translate(mascot.x, mascot.y - base_height_px * mascot.scale_y)  # فوق الرأس
        painter.scale(base_height_px, base_height_px)
        paint_effect(painter, mascot)
    finally:
        painter.restore()
