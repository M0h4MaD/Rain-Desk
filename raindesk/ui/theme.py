"""raindesk/ui/theme.py

الغرض: السمة البصرية (فاتحة/داكنة/النظام): رموز الألوان (tokens) وورقة الأنماط QSS واللوحة.
المسؤوليات: تحديد السمة الفعلية، وتطبيق الخط واللوحة (QPalette) وورقة الأنماط على التطبيق،
    ومتابعة تغيّر سمة النظام، وإصدار theme_changed.
الاعتماديات: PySide6 فقط (QtCore وQtGui وQtWidgets) والمكتبة القياسية.
النمط التصميمي: Strategy (مجموعة رموز لكل سمة) مع Observer (theme_changed).
ملاحظات: الرموز تجتاز تباين WCAG 2.1 (AA، 4.5:1 للنص)، ويتحقق منه tests/test_theme_contrast.py.
    نستعمل النمط Fusion لأن الأنماط الأصلية في Windows تتجاهل أجزاء من اللوحة وQSS.
    الأدوات المرسومة يدويًا (ToggleSwitch) تقرأ ألوانها من اللوحة: Button وMid وHighlight
    وHighlightedText وPlaceholderText، ويحمل الدور Link لون حلقة التركيز (focus_ring).
مثال: theme = ThemeManager(app); theme.apply('dark')
"""

from __future__ import annotations

import logging
from string import Template
from typing import Final

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

_LOG = logging.getLogger(__name__)

MODE_SYSTEM: Final[str] = "system"
MODE_LIGHT: Final[str] = "light"
MODE_DARK: Final[str] = "dark"
_MODES: Final[tuple[str, ...]] = (MODE_SYSTEM, MODE_LIGHT, MODE_DARK)
_FONT_FAMILIES: Final[tuple[str, ...]] = ("Segoe UI", "Tahoma", "Arial")  # Segoe UI تدعم العربية
_BASE_POINT_SIZE: Final[int] = 10
_STYLE_NAME: Final[str] = "Fusion"

TOKENS_DARK: Final[dict[str, str]] = {
    "bg": "#0F141A",
    "surface": "#171E26",
    "surface_alt": "#1E2731",
    "border": "#2A3644",
    "text": "#E6EDF3",
    "text_muted": "#9FB0C0",
    "accent": "#4FA3FF",
    "accent_hover": "#74B8FF",
    "accent_text": "#0B0F14",
    "danger": "#FF6B6B",
    "success": "#3DDC97",
    "focus_ring": "#74B8FF",
}

TOKENS_LIGHT: Final[dict[str, str]] = {
    "bg": "#F4F7FA",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF3F8",
    "border": "#D5DEE8",
    "text": "#16202A",
    "text_muted": "#5B6B7B",
    "accent": "#1F6FEB",
    "accent_hover": "#1A5FCC",
    "accent_text": "#FFFFFF",
    "danger": "#C62828",
    "success": "#1B7F4B",
    "focus_ring": "#1F6FEB",
}

# ورقة الأنماط: قالب string.Template كي لا نضاعف الأقواس المعقوصة الخاصة بـ QSS.
# الخلفيات الأساسية تأتي من اللوحة (Window وBase)، فلا نحدد خلفية لكل QWidget (وإلا صارت
# كل QLabel مستطيلًا معتمًا داخل البطاقات). القياسات على شبكة 8px: الزوايا 10 و8، الارتفاع 32.
_QSS_TEMPLATE: Final[Template] = Template(
    """
QToolTip { background: ${surface_alt}; color: ${text}; border: 1px solid ${border};
           padding: 4px 6px; }
QMenu { background: ${surface}; color: ${text}; border: 1px solid ${border}; padding: 4px; }
QMenu::item { padding: 6px 24px; border-radius: 6px; }
QMenu::item:selected { background: ${accent}; color: ${accent_text}; }
QMenu::separator { height: 1px; background: ${border}; margin: 4px 8px; }

QFrame#SectionCard { background: ${surface}; border: 1px solid ${border}; border-radius: 10px; }
QLabel#PageTitle { font-size: 16pt; font-weight: 600; }
QLabel#CardTitle { font-size: 12pt; font-weight: 600; }
QLabel#Caption { font-size: 9pt; color: ${text_muted}; }
QLabel#Note { background: ${surface_alt}; color: ${text_muted}; border-radius: 8px; padding: 8px; }
QLabel#StatusLabel { color: ${success}; }

QListWidget#Sidebar { background: ${surface}; border: none; outline: 0; padding: 8px; }
QListWidget#Sidebar::item { height: 40px; padding: 0 12px; border-radius: 8px; color: ${text}; }
QListWidget#Sidebar::item:hover { background: ${surface_alt}; }
QListWidget#Sidebar::item:selected { background: ${accent}; color: ${accent_text}; }
QListWidget#Sidebar:focus { border: 2px solid ${focus_ring}; }

QPushButton { background: ${surface_alt}; color: ${text}; border: 1px solid ${border};
              border-radius: 8px; padding: 0 16px; min-height: 32px; }
QPushButton:hover { border-color: ${accent}; }
QPushButton:pressed { background: ${border}; }
QPushButton:focus { border: 2px solid ${focus_ring}; padding: 0 15px; }
QPushButton:disabled { color: ${text_muted}; }
QPushButton#primary { background: ${accent}; color: ${accent_text}; border: 1px solid ${accent};
                      font-weight: 600; }
QPushButton#primary:hover { background: ${accent_hover}; border-color: ${accent_hover}; }
QPushButton#primary:focus { border: 2px solid ${focus_ring}; padding: 0 15px; }

QComboBox { background: ${surface_alt}; color: ${text}; border: 1px solid ${border};
            border-radius: 8px; padding: 0 12px; min-height: 32px; }
QComboBox:hover { border-color: ${accent}; }
QComboBox:focus { border: 2px solid ${focus_ring}; }
QComboBox:disabled { color: ${text_muted}; }
QComboBox QAbstractItemView { background: ${surface}; color: ${text}; border: 1px solid ${border};
                              selection-background-color: ${accent};
                              selection-color: ${accent_text}; outline: 0; }

QSlider::groove:horizontal { height: 4px; background: ${border}; border-radius: 2px; }
QSlider::sub-page:horizontal { background: ${accent}; border-radius: 2px; }
QSlider::handle:horizontal { background: ${accent}; width: 16px; height: 16px; margin: -6px 0;
                             border-radius: 8px; border: 2px solid ${accent}; }
QSlider::handle:horizontal:hover { background: ${accent_hover}; border-color: ${accent_hover}; }
QSlider::handle:horizontal:focus { border: 2px solid ${text}; }
QSlider::handle:horizontal:disabled { background: ${text_muted}; border-color: ${text_muted}; }
QSlider::sub-page:horizontal:disabled { background: ${text_muted}; }

QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: ${border}; border-radius: 6px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: ${text_muted}; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
)


class ThemeManager(QObject):
    """يطبّق السمة على التطبيق كله ويبلّغ عند تغيّر السمة الفعلية (light أو dark)."""

    theme_changed = Signal(str)  # السمة الفعلية الجديدة: 'light' أو 'dark'

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode: str = MODE_SYSTEM
        self._effective: str = self._system_mode()
        self._initialized = False  # الخط والنمط يُضبطان مرة واحدة فقط
        signal = getattr(QGuiApplication.styleHints(), "colorSchemeChanged", None)
        if signal is not None:  # متاحة من Qt 6.5
            signal.connect(self._on_system_scheme_changed)

    @staticmethod
    def _system_mode() -> str:
        """سمة النظام الحالية؛ تُعدّ فاتحة إن تعذّر الاستعلام (Qt أقدم من 6.5 أو قيمة Unknown)."""
        getter = getattr(QGuiApplication.styleHints(), "colorScheme", None)
        if getter is not None and getter() == Qt.ColorScheme.Dark:
            return MODE_DARK
        return MODE_LIGHT

    @property
    def effective_mode(self) -> str:
        """'light' أو 'dark' (لا تكون 'system' أبدًا)."""
        return self._effective

    @property
    def tokens(self) -> dict[str, str]:
        """نسخة من رموز السمة الفعلية."""
        return dict(TOKENS_DARK if self._effective == MODE_DARK else TOKENS_LIGHT)

    def stylesheet(self) -> str:
        """ورقة QSS للسمة الفعلية."""
        return _QSS_TEMPLATE.substitute(self.tokens)

    def _palette(self) -> QPalette:
        """لوحة ألوان من الرموز: تعتمد عليها الأدوات القياسية والمرسومة يدويًا معًا."""
        tokens = self.tokens
        palette = QPalette()
        roles = {
            QPalette.ColorRole.Window: "bg",
            QPalette.ColorRole.WindowText: "text",
            QPalette.ColorRole.Base: "surface",
            QPalette.ColorRole.AlternateBase: "surface_alt",
            QPalette.ColorRole.Text: "text",
            QPalette.ColorRole.Button: "surface_alt",
            QPalette.ColorRole.ButtonText: "text",
            QPalette.ColorRole.Highlight: "accent",
            QPalette.ColorRole.HighlightedText: "accent_text",
            QPalette.ColorRole.ToolTipBase: "surface_alt",
            QPalette.ColorRole.ToolTipText: "text",
            QPalette.ColorRole.PlaceholderText: "text_muted",
            QPalette.ColorRole.Mid: "border",
            QPalette.ColorRole.Link: "focus_ring",
        }
        for role, key in roles.items():
            palette.setColor(role, QColor(tokens[key]))
        muted = QColor(tokens["text_muted"])
        for role in (
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
            QPalette.ColorRole.WindowText,
        ):
            palette.setColor(QPalette.ColorGroup.Disabled, role, muted)
        return palette

    def apply(self, mode: str) -> None:
        """يطبّق السمة ('system' أو 'light' أو 'dark')؛ القيمة المجهولة تُعامل كـ 'system'."""
        if mode not in _MODES:
            _LOG.warning("unknown theme mode %r; using system", mode)
            mode = MODE_SYSTEM
        self._mode = mode
        effective = self._system_mode() if mode == MODE_SYSTEM else mode
        changed = effective != self._effective
        self._effective = effective
        self._apply_to_application()
        if changed:
            self.theme_changed.emit(effective)

    def _apply_to_application(self) -> None:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        if not self._initialized:
            app.setStyle(_STYLE_NAME)
            font = QFont()
            font.setFamilies(list(_FONT_FAMILIES))
            font.setPointSize(_BASE_POINT_SIZE)
            app.setFont(font)
            self._initialized = True
        app.setPalette(self._palette())
        app.setStyleSheet(self.stylesheet())

    def _on_system_scheme_changed(self, *_args: object) -> None:
        """عند تغيّر سمة Windows نعيد التطبيق فقط إذا كان الوضع المختار 'system'."""
        if self._mode == MODE_SYSTEM:
            self.apply(MODE_SYSTEM)