"""raindesk/ui/widgets/toggle_switch.py

الغرض: مفتاح تبديل (toggle) مرسوم يدويًا بحجم 44x24 px مع حركة انزلاق للمقبض.
المسؤوليات: الرسم من ألوان اللوحة، وحركة 120 ms بمنحنى ease-out، وحلقة تركيز ظاهرة للوحة
    المفاتيح، وعكس الاتجاه في RTL، وتعطيل الحركة إن عطّلها المستخدم في Windows.
الاعتماديات: PySide6 وraindesk.platform_win.win32_api وraindesk.engine.math_utils.
النمط التصميمي: Custom Widget مع Property Animation.
ملاحظات: Space يبدّل الحالة تلقائيًا (سلوك QAbstractButton). يستدعي Qt الدالة checkStateSet
    عند كل تغيّر في الحالة، حتى مع حجب الإشارات، فتبقى الحركة متزامنة مع الربط ثنائي الاتجاه.
    المستدعي يضبط setAccessibleName لأن المفتاح بلا نص.
مثال: switch = ToggleSwitch(); switch.setAccessibleName('Show rain'); switch.toggled.connect(f)
"""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import QAbstractButton, QWidget

from raindesk.engine.math_utils import lerp
from raindesk.platform_win import win32_api

_WIDTH_PX: Final[int] = 44
_HEIGHT_PX: Final[int] = 24
_KNOB_MARGIN_PX: Final[int] = 4  # px: الفراغ بين المقبض وحافة المسار
_ANIMATION_MS: Final[int] = 120
_TRACK_OUTLINE_PX: Final[float] = 1.0
_FOCUS_RING_PX: Final[float] = 2.0
_FOCUS_GAP_PX: Final[float] = 2.0  # px: الفراغ بين المسار وحلقة التركيز
_DISABLED_OPACITY: Final[float] = 0.5


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    """مزج خطي بين لونين (t=0 يعطي a وt=1 يعطي b) قناة بقناة."""
    return QColor(
        round(lerp(a.red(), b.red(), t)),
        round(lerp(a.green(), b.green(), t)),
        round(lerp(a.blue(), b.blue(), t)),
    )


class ToggleSwitch(QAbstractButton):
    """مفتاح تبديل؛ الإشارة toggled(bool) موروثة من QAbstractButton."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Tab ونقر
        self.setFixedSize(_WIDTH_PX, _HEIGHT_PX)
        self._progress = 0.0  # موضع المقبض: 0 إيقاف، 1 تشغيل
        self._animation = QPropertyAnimation(self, b"progress", self)
        self._animation.setDuration(_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(_WIDTH_PX, _HEIGHT_PX)

    # ------------------------------------------------------------------ خاصية الحركة
    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, value: float) -> None:
        self._progress = value
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def _animate_to(self, target: float) -> None:
        """ينتقل إلى الهدف بحركة، أو فورًا إن كانت النافذة مخفية أو الحركة معطّلة في Windows."""
        self._animation.stop()
        if not self.isVisible() or not win32_api.client_animations_enabled():
            self._set_progress(target)
            return
        self._animation.setStartValue(self._progress)
        self._animation.setEndValue(target)
        self._animation.start()

    def checkStateSet(self) -> None:  # noqa: N802
        super().checkStateSet()
        self._animate_to(1.0 if self.isChecked() else 0.0)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._animation.stop()
        self._set_progress(1.0 if self.isChecked() else 0.0)  # مزامنة الحالة عند الظهور

    # ------------------------------------------------------------------ الرسم
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            painter.setOpacity(_DISABLED_OPACITY)
        palette = self.palette()
        progress = self._progress
        width, height = float(self.width()), float(self.height())

        inset = _TRACK_OUTLINE_PX / 2.0
        track = QRectF(inset, inset, width - 2 * inset, height - 2 * inset)
        radius = track.height() / 2.0
        track_color = _blend(palette.button().color(), palette.highlight().color(), progress)
        painter.setPen(QPen(palette.mid().color(), _TRACK_OUTLINE_PX))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, radius, radius)

        diameter = height - 2.0 * _KNOB_MARGIN_PX
        travel = width - 2.0 * _KNOB_MARGIN_PX - diameter
        offset = travel * (1.0 - progress if self.isRightToLeft() else progress)  # عكس في RTL
        knob_color = _blend(
            palette.placeholderText().color(), palette.highlightedText().color(), progress
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(_KNOB_MARGIN_PX + offset, _KNOB_MARGIN_PX, diameter, diameter))

        if self.hasFocus():  # حلقة تركيز لمستخدمي لوحة المفاتيح (لون focus_ring في دور Link)
            ring = track.adjusted(-_FOCUS_GAP_PX, -_FOCUS_GAP_PX, _FOCUS_GAP_PX, _FOCUS_GAP_PX)
            painter.setPen(QPen(palette.link().color(), _FOCUS_RING_PX))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(ring, ring.height() / 2.0, ring.height() / 2.0)
        painter.end()