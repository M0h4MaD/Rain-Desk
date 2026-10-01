"""raindesk/ui/widgets/color_button.py

الغرض: زر يعرض عينة اللون وقيمته النصية ويفتح QColorDialog عند الضغط.
المسؤوليات: تخزين اللون بصيغة '#RRGGBB' بأحرف كبيرة، ورفض القيم غير الصالحة، وإصدار color_changed
    عند اختيار المستخدم فقط.
الاعتماديات: PySide6 وraindesk.core.color_utils وraindesk.i18n.translator.
النمط التصميمي: Custom Widget (زر مع أيقونة مولَّدة).
مثال: button = ColorButton(translator); button.set_color('#A9C7E8')
"""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QColorDialog, QPushButton, QWidget

from raindesk.core.color_utils import hex_to_rgb, is_valid_hex, rgb_to_hex
from raindesk.i18n.translator import Translator

_LOG = logging.getLogger(__name__)

_SWATCH_PX: Final[int] = 20
_SWATCH_RADIUS_PX: Final[float] = 4.0
_SWATCH_OUTLINE_PX: Final[float] = 1.0
_DEFAULT_COLOR: Final[str] = "#FFFFFF"


class ColorButton(QPushButton):
    """زر اختيار لون؛ color_changed(str) يصدر عند اختيار المستخدم لونًا جديدًا فقط."""

    color_changed = Signal(str)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._color = _DEFAULT_COLOR
        self.setIconSize(QSize(_SWATCH_PX, _SWATCH_PX))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._choose_color)
        self._refresh()
        self.retranslate()

    def color(self) -> str:
        """اللون الحالي بصيغة '#RRGGBB' (أحرف كبيرة)."""
        return self._color

    def set_color(self, hex_color: str) -> None:
        """يضبط اللون دون إصدار إشارة؛ القيمة غير الصالحة تُرفض مع تحذير ويبقى اللون كما هو."""
        if not is_valid_hex(hex_color):
            _LOG.warning("ColorButton rejected invalid color: %.20r", hex_color)
            return
        self._color = rgb_to_hex(hex_to_rgb(hex_color))
        self._refresh()

    def retranslate(self) -> None:
        self.setToolTip(self._translator.tr("color.tip"))

    def _refresh(self) -> None:
        """يرسم عينة اللون (بدقة الشاشة) ويكتب القيمة نصًا ملاصقًا لها."""
        ratio = self.devicePixelRatioF()
        side = round(_SWATCH_PX * ratio)
        pixmap = QPixmap(side, side)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self.palette().mid().color(), _SWATCH_OUTLINE_PX))
        painter.setBrush(QColor(self._color))
        painter.drawRoundedRect(
            QRectF(0.5, 0.5, _SWATCH_PX - 1.0, _SWATCH_PX - 1.0),
            _SWATCH_RADIUS_PX, _SWATCH_RADIUS_PX,
        )
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setText(self._color)
        self.setAccessibleDescription(self._color)

    def _choose_color(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self._color), self, self._translator.tr("color.pick_title")
        )
        if not chosen.isValid():
            return  # أُلغي الحوار
        new_color = rgb_to_hex((chosen.red(), chosen.green(), chosen.blue()))
        if new_color != self._color:
            self.set_color(new_color)
            self.color_changed.emit(new_color)