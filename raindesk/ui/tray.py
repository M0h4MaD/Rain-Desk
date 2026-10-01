"""raindesk/ui/tray.py

الغرض: أيقونة شريط النظام وقائمتها (فتح الإعدادات، تشغيل/إيقاف، عشوائي، إعدادات مسبقة، خروج).
المسؤوليات: رسم الأيقونة برمجيًا (بلا ملفات صور)، وبناء القائمة، وإصدار إشارات الطلبات
    إلى AppController، وتحديث النصوص عند تغيّر اللغة، وإظهار إشعارات النظام.
الاعتماديات: PySide6 وraindesk.config.schema (أسماء الإعدادات المسبقة) وraindesk.i18n.translator.
النمط التصميمي: Adapter فوق QSystemTrayIcon، وObserver عبر الإشارات (لا يعرف المتحكم).
ملاحظات: النقر الأيسر يفتح الإعدادات. تُضاف عناصر الصوت في مرحلة الصوت.
مثال: tray = TrayController(translator); tray.show(); tray.notify('RainDesk', 'Hello')
"""

from __future__ import annotations

from functools import partial
from typing import Final

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from raindesk.config.schema import PRESETS
from raindesk.i18n.translator import Translator

_ICON_PX: Final[int] = 64  # px: الدقة التي نرسم بها (تُصغَّر تلقائيًا لحجم الأيقونة)
_ICON_COLOR_ON: Final[str] = "#4FA3FF"  # يطابق accent في السمة الداكنة
_ICON_COLOR_OFF: Final[str] = "#8A97A6"  # رمادي محايد للحالة الموقوفة
_HIGHLIGHT_ALPHA: Final[int] = 90  # شفافية اللمعة البيضاء على القطرة
_NOTIFY_MS: Final[int] = 6000  # ms: مدة بقاء الإشعار


def _make_icon(fill: str) -> QIcon:
    """قطرة ماء ملوّنة بلمعة؛ تتكوّن من قوسين بيزيه وقوس سفلي نصف دائري."""
    pixmap = QPixmap(_ICON_PX, _ICON_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.moveTo(32.0, 5.0)  # رأس القطرة
    path.cubicTo(32.0, 5.0, 52.0, 29.0, 52.0, 42.0)  # الجانب الأيمن نحو نقطة القوس
    path.arcTo(QRectF(12.0, 22.0, 40.0, 40.0), 0.0, -180.0)  # النصف السفلي (مع عقارب الساعة)
    path.cubicTo(12.0, 29.0, 32.0, 5.0, 32.0, 5.0)  # الجانب الأيسر عودة إلى الرأس
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(fill))
    painter.drawPath(path)
    painter.setBrush(QColor(255, 255, 255, _HIGHLIGHT_ALPHA))
    painter.drawEllipse(QRectF(21.0, 38.0, 7.0, 12.0))  # لمعة صغيرة توحي بالحجم
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    """أيقونة شريط النظام؛ كل الإجراءات تخرج كإشارات ولا ينفّذ منها شيئًا بنفسه."""

    open_settings_requested = Signal()
    toggle_enabled_requested = Signal()
    randomize_requested = Signal()
    preset_requested = Signal(str)
    quit_requested = Signal()

    def __init__(self, translator: Translator, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._enabled = True
        self._icon_on = _make_icon(_ICON_COLOR_ON)
        self._icon_off = _make_icon(_ICON_COLOR_OFF)
        self._tray = QSystemTrayIcon(self._icon_on, self)

        # القائمة بلا أب Qt (تُحذف مع المتحكم)؛ نحتفظ بمرجعها كي لا تُجمَّع قبل الأوان.
        self._menu = QMenu()
        self._action_open = QAction(self._menu)
        bold = QFont(self._action_open.font())
        bold.setBold(True)
        self._action_open.setFont(bold)  # الإجراء الافتراضي بخط عريض كأغلب تطبيقات الشريط
        self._action_enable = QAction(self._menu)
        self._action_enable.setCheckable(True)
        self._action_enable.setChecked(True)
        self._action_randomize = QAction(self._menu)
        self._presets_menu = QMenu(self._menu)
        self._preset_actions: dict[str, QAction] = {}
        for code in PRESETS:
            action = QAction(self._presets_menu)
            action.triggered.connect(partial(self._emit_preset, code))
            self._presets_menu.addAction(action)
            self._preset_actions[code] = action
        self._action_quit = QAction(self._menu)

        self._menu.addAction(self._action_open)
        self._menu.addAction(self._action_enable)
        self._menu.addAction(self._action_randomize)
        self._menu.addMenu(self._presets_menu)
        self._menu.addSeparator()
        self._menu.addAction(self._action_quit)

        self._action_open.triggered.connect(self.open_settings_requested)
        self._action_enable.triggered.connect(self.toggle_enabled_requested)
        self._action_randomize.triggered.connect(self.randomize_requested)
        self._action_quit.triggered.connect(self.quit_requested)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self.retranslate()

    @staticmethod
    def is_available() -> bool:
        """True إذا كان شريط النظام متاحًا في هذه الجلسة."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    @property
    def app_icon(self) -> QIcon:
        """أيقونة التطبيق (لنافذة الإعدادات وغيرها)."""
        return self._icon_on

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()  # يُخفى صراحةً عند الخروج كي لا تبقى أيقونة شبحية في الشريط

    def set_enabled_state(self, enabled: bool) -> None:
        """يزامن علامة "إظهار المطر" والأيقونة والتلميح مع حالة التشغيل."""
        self._enabled = enabled
        self._action_enable.setChecked(enabled)  # setChecked لا يصدر triggered
        self._tray.setIcon(self._icon_on if enabled else self._icon_off)
        self._update_tooltip()

    def notify(self, title: str, message: str) -> None:
        """إشعار من شريط النظام إن كان مدعومًا."""
        if QSystemTrayIcon.supportsMessages():
            self._tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, _NOTIFY_MS
            )

    def retranslate(self) -> None:
        tr = self._translator.tr
        self._action_open.setText(tr("tray.open_settings"))
        self._action_enable.setText(tr("tray.enable"))
        self._action_randomize.setText(tr("tray.randomize"))
        self._presets_menu.setTitle(tr("tray.presets"))
        for code, action in self._preset_actions.items():
            action.setText(tr(f"preset.{code}"))
        self._action_quit.setText(tr("tray.quit"))
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        key = "app.name" if self._enabled else "tray.tooltip_off"
        self._tray.setToolTip(self._translator.tr(key))

    def _emit_preset(self, code: str, _checked: bool = False) -> None:
        self.preset_requested.emit(code)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_settings_requested.emit()