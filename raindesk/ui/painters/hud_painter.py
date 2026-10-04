"""raindesk/ui/painters/hud_painter.py

الغرض: رسم لوحة التشخيص (debug HUD): أسطر نصية بخط ثابت العرض فوق خلفية معتمة جزئيًا.
المسؤوليات: قياس النص بـ QFontMetricsF ورسم مستطيل مستدير ثم الأسطر في الزاوية العليا اليسرى.
الاعتماديات: PySide6 فقط.
النمط التصميمي: دالة رسم بلا حالة.
ملاحظات: اللوحة أداة تشخيص بالإنجليزية عمدًا (أرقام ومصطلحات تقنية) ولا تُترجم.
مثال: paint_hud(painter, ['FPS 30', 'Drops 650'])
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter

_MARGIN_PX: Final[float] = 12.0  # px: بعد اللوحة عن حافة الشاشة
_PADDING_PX: Final[float] = 8.0  # px: الحشوة داخل اللوحة
_RADIUS_PX: Final[float] = 6.0
_POINT_SIZE: Final[int] = 10
_BACKGROUND: Final[QColor] = QColor(0, 0, 0, 170)
_TEXT_COLOR: Final[QColor] = QColor(235, 245, 255)
_FONT_FAMILY: Final[str] = "Consolas"  # ثابت العرض ومتوفر في Windows؛ يُستبدل بأقرب بديل ثابت


def paint_hud(painter: QPainter, lines: Sequence[str]) -> None:
    """يرسم أسطر التشخيص في الزاوية العليا اليسرى؛ لا شيء إن كانت القائمة فارغة."""
    if not lines:
        return
    font = QFont(_FONT_FAMILY)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(_POINT_SIZE)
    metrics = QFontMetricsF(font)
    line_height = metrics.height()
    text_width = max(metrics.horizontalAdvance(line) for line in lines)
    box = QRectF(
        _MARGIN_PX, _MARGIN_PX,
        text_width + 2.0 * _PADDING_PX, line_height * len(lines) + 2.0 * _PADDING_PX,
    )
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_BACKGROUND)
    painter.drawRoundedRect(box, _RADIUS_PX, _RADIUS_PX)
    painter.setFont(font)
    painter.setPen(_TEXT_COLOR)
    for index, line in enumerate(lines):
        baseline = box.top() + _PADDING_PX + metrics.ascent() + index * line_height
        painter.drawText(box.left() + _PADDING_PX, baseline, line)
    painter.restore()