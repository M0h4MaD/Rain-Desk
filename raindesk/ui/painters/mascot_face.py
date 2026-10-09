"""raindesk/ui/painters/mascot_face.py

الغرض: رسم وجه Drip: عينان كبيرتان لامعتان (على طريقة الكاواي)، وخدّان محمرّان، وفم، وحواجب
    الخوف، مع تعابير: عادي وسعيد وفزع وخوف ونعاس وحب.
المسؤوليات: paint_face فقط في فضاء الوحدة (ارتفاع الجسم 1 وقدمه عند y = 0)؛ يقرأ التعبير
    ونظرة العينين والرمش وفتحة الفم من Mascot ولا يغيّر شيئًا.
الاعتماديات: PySide6.QtCore وPySide6.QtGui وraindesk.engine.mascot.
النمط التصميمي: Painter Function (بلا حالة).
ملاحظات: الإحساس بالـ "لطافة" يأتي من: عينين كبيرتين منخفضتين في الوجه، ولمعتين بيضاوين
    (كبرى وصغرى) تعطيان حياة، وخدّين ورديين، وفم صغير. اتجاه النظر يزيح العين كلها قليلًا
    واللمعات أقل (parallax) فتبدو العين كروية.
مثال: paint_face(painter, mascot)
"""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

from raindesk.engine.mascot import Expression, Mascot

_EYE_X: Final[float] = 0.175  # إزاحة العين عن محور الجسم (فضاء الوحدة)
_EYE_Y: Final[float] = -0.47
_EYE_RX: Final[float] = 0.085
_EYE_RY: Final[float] = 0.105
_LOOK_GAIN_X: Final[float] = 0.03  # إزاحة العين عند look_dir = 1
_LOOK_GAIN_Y: Final[float] = 0.024
_FACING_GAIN: Final[float] = 0.008  # ميل خفيف نحو اتجاه المشي
_SURPRISE_SCALE: Final[float] = 1.14  # تكبير العين عند الدهشة
_HAPPY_SQUINT: Final[float] = 0.92
_MIN_OPEN: Final[float] = 0.05  # أدنى انفتاح للعين عند الرمش (خط رفيع)
_HIGHLIGHT_BIG: Final[float] = 0.036
_HIGHLIGHT_SMALL: Final[float] = 0.017
_CHEEK_X: Final[float] = 0.30
_CHEEK_Y: Final[float] = -0.36
_CHEEK_RX: Final[float] = 0.075
_CHEEK_RY: Final[float] = 0.05
_MOUTH_Y: Final[float] = -0.305
_LINE_WIDTH: Final[float] = 0.022  # سمك خطوط الفم والجفون (فضاء الوحدة)

_EYE_TOP: Final[QColor] = QColor("#3A5585")
_EYE_BOTTOM: Final[QColor] = QColor("#0E1A33")
_INK: Final[QColor] = QColor("#14233F")
_WHITE: Final[QColor] = QColor(255, 255, 255)
_TONGUE: Final[QColor] = QColor("#FF8FAE")
_CHEEK: Final[QColor] = QColor("#FF8FB2")
_CHEEK_ALPHA: Final[dict[Expression, int]] = {
    Expression.NEUTRAL: 80,
    Expression.HAPPY: 135,
    Expression.SURPRISED: 60,
    Expression.SCARED: 35,
    Expression.SLEEPY: 90,
    Expression.LOVE: 175,
}


def _stroke(color: QColor) -> QPen:
    pen = QPen(QBrush(color), _LINE_WIDTH)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _paint_cheeks(painter: QPainter, expression: Expression) -> None:
    """خدّان ورديان؛ يشتدّان مع الفرح والحب ويخفتان مع الخوف."""
    color = QColor(_CHEEK)
    color.setAlpha(_CHEEK_ALPHA[expression])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    for side in (-1.0, 1.0):
        painter.drawEllipse(QPointF(side * _CHEEK_X, _CHEEK_Y), _CHEEK_RX, _CHEEK_RY)


def _paint_closed_eye(painter: QPainter, cx: float, cy: float, up: bool) -> None:
    """عين مغمضة: قوس "∩" للفرح والحب أو "∪" للنعاس."""
    path = QPainterPath()
    path.moveTo(cx - 0.075, cy + (0.02 if up else -0.01))
    path.quadTo(cx, cy + (-0.075 if up else 0.07), cx + 0.075, cy + (0.02 if up else -0.01))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_stroke(_INK))
    painter.drawPath(path)


def _paint_brows(painter: QPainter, cx: float, cy: float, side: float) -> None:
    """حاجبا الخوف: الطرف الداخلي مرفوع."""
    path = QPainterPath()
    path.moveTo(cx + side * 0.085, cy - 0.145)
    path.lineTo(cx - side * 0.07, cy - 0.20)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_stroke(_INK))
    painter.drawPath(path)


def _paint_eye(painter: QPainter, mascot: Mascot, side: float) -> None:
    expression = mascot.expression
    cx = side * _EYE_X + mascot.look_dir * _LOOK_GAIN_X + mascot.facing * _FACING_GAIN
    cy = _EYE_Y + mascot.look_y * _LOOK_GAIN_Y
    if expression is Expression.LOVE:
        _paint_closed_eye(painter, side * _EYE_X, _EYE_Y, up=True)
        return
    if expression is Expression.SLEEPY:
        _paint_closed_eye(painter, side * _EYE_X, _EYE_Y, up=False)
        return
    scale = _SURPRISE_SCALE if expression is Expression.SURPRISED else 1.0
    squint = _HAPPY_SQUINT if expression is Expression.HAPPY else 1.0
    openness = max(_MIN_OPEN, 1.0 - mascot.blink)
    rx, ry = _EYE_RX * scale, _EYE_RY * scale * squint * openness
    gradient = QRadialGradient(QPointF(cx, cy - ry * 0.35), max(_EYE_RX, ry) * 1.5)
    gradient.setColorAt(0.0, _EYE_TOP)
    gradient.setColorAt(1.0, _EYE_BOTTOM)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(QPointF(cx, cy), rx, ry)
    if openness > 0.35:  # لمعتان: كبرى أعلى اليسار وصغرى أسفل اليمين (parallax أقل من العين)
        shift_x, shift_y = mascot.look_dir * 0.01, mascot.look_y * 0.008
        painter.setBrush(_WHITE)
        painter.drawEllipse(
            QPointF(cx - rx * 0.36 - shift_x, cy - ry * 0.40 - shift_y),
            _HIGHLIGHT_BIG * scale,
            _HIGHLIGHT_BIG * scale * 1.1,
        )
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawEllipse(
            QPointF(cx + rx * 0.42 - shift_x, cy + ry * 0.46 - shift_y),
            _HIGHLIGHT_SMALL * scale,
            _HIGHLIGHT_SMALL * scale,
        )
    if expression is Expression.SCARED:
        _paint_brows(painter, side * _EYE_X, _EYE_Y, side)


def _paint_mouth(painter: QPainter, mascot: Mascot) -> None:
    expression, opened = mascot.expression, mascot.mouth_open
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if expression is Expression.SCARED:  # فم متعرّج مرتجف
        path = QPainterPath()
        path.moveTo(-0.07, _MOUTH_Y + 0.01)
        path.quadTo(-0.035, _MOUTH_Y - 0.03, 0.0, _MOUTH_Y + 0.005)
        path.quadTo(0.035, _MOUTH_Y + 0.04, 0.07, _MOUTH_Y - 0.01)
        painter.setPen(_stroke(_INK))
        painter.drawPath(path)
        return
    if expression is Expression.SURPRISED:  # "o" صغيرة
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_INK)
        painter.drawEllipse(QPointF(0.0, _MOUTH_Y + 0.01), 0.038, 0.05 + 0.02 * opened)
        return
    if opened > 0.12:  # فم مفتوح (ضحكة أو التقاط مطر أو تثاؤب) مع لسان
        width, height = 0.06 + 0.05 * opened, 0.02 + 0.095 * opened
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_INK)
        painter.drawEllipse(QPointF(0.0, _MOUTH_Y + height * 0.35), width, height)
        if opened > 0.35:
            painter.setBrush(_TONGUE)
            painter.drawEllipse(QPointF(0.0, _MOUTH_Y + height * 0.8), width * 0.6, height * 0.45)
        return
    smile = 0.075 if expression in (Expression.HAPPY, Expression.LOVE) else 0.05
    path = QPainterPath()  # ابتسامة صغيرة
    path.moveTo(-0.055, _MOUTH_Y - 0.012)
    path.quadTo(0.0, _MOUTH_Y - 0.012 + smile, 0.055, _MOUTH_Y - 0.012)
    painter.setPen(_stroke(_INK))
    painter.drawPath(path)


def paint_face(painter: QPainter, mascot: Mascot) -> None:
    """يرسم الوجه كله: الخدّان ثم العينان ثم الفم؛ يفترض فضاء الوحدة المُسقَط على الجسم."""
    _paint_cheeks(painter, mascot.expression)
    for side in (-1.0, 1.0):
        _paint_eye(painter, mascot, side)
    _paint_mouth(painter, mascot)
