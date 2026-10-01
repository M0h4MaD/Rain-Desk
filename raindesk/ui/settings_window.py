"""raindesk/ui/settings_window.py

الغرض: نافذة الإعدادات: شريط جانبي للصفحات ومنطقة محتوى وشريط أزرار سفلي.
المسؤوليات: بناء الصفحات داخل QScrollArea، والتنقل، وزرّي "عشوائي" و"استعادة الافتراضي"
    (مع تأكيد)، وحالة "تم الحفظ"، وحفظ هندسة النافذة، وإعادة الترجمة، وإخفاء النافذة عند الإغلاق.
الاعتماديات: PySide6 وraindesk.config.store وraindesk.i18n.translator وraindesk.ui.theme
    وصفحات الواجهة.
النمط التصميمي: Composite (نافذة تحوي صفحات) مع Observer على المخزن والمترجم.
ملاحظات: التطبيق الحي: لا زر "موافق" ولا "تطبيق"؛ كل تغيير يُكتب فورًا في المخزن.
    الإغلاق يخفي النافذة فيبقى التطبيق في شريط النظام، إلا إذا كان الشريط غير متاح فيُغلق التطبيق.
مثال: window = SettingsWindow(store, translator, theme); window.show_and_raise()
"""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.pages.general_page import GeneralPage
from raindesk.ui.pages.rain_page import RainPage
from raindesk.ui.theme import ThemeManager

_DEFAULT_SIZE: Final[tuple[int, int]] = (900, 640)
_MIN_SIZE: Final[tuple[int, int]] = (760, 540)
_SIDEBAR_WIDTH_PX: Final[int] = 210
_BAR_MARGIN_PX: Final[int] = 16
_BAR_SPACING_PX: Final[int] = 8
_SAVED_FLASH_MS: Final[int] = 1500  # ms: مدة ظهور "تم الحفظ"
_NOTICE_MS: Final[int] = 10000  # ms: مدة ظهور رسالة تنبيه
_GEOMETRY_KEY: Final[str] = "window_geometry"


class SettingsWindow(QMainWindow):
    """نافذة الإعدادات؛ تُنشأ كسولًا من AppController وتبقى حيّة مخفيةً بين الاستعمالات."""

    randomize_requested = Signal()
    reset_requested = Signal()

    def __init__(
        self,
        store: SettingsStore,
        translator: Translator,
        theme: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._translator = translator
        self._theme = theme
        self._quit_on_close = False

        self.setMinimumSize(*_MIN_SIZE)
        self._pages: list[BasePage] = [
            GeneralPage(store, translator),
            RainPage(store, translator),
        ]

        self._sidebar = QListWidget()
        self._sidebar.setObjectName("Sidebar")
        self._sidebar.setFixedWidth(_SIDEBAR_WIDTH_PX)
        self._sidebar.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._stack = QStackedWidget()
        for page in self._pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self._stack.addWidget(scroll)
            self._sidebar.addItem(QListWidgetItem())
        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)

        self._randomize_button = QPushButton()
        self._randomize_button.setObjectName("primary")
        self._reset_button = QPushButton()
        self._status = QLabel()
        self._status.setObjectName("StatusLabel")
        self._randomize_button.clicked.connect(self.randomize_requested)
        self._reset_button.clicked.connect(self._confirm_reset)

        bar = QHBoxLayout()
        bar.setContentsMargins(_BAR_MARGIN_PX, _BAR_MARGIN_PX, _BAR_MARGIN_PX, _BAR_MARGIN_PX)
        bar.setSpacing(_BAR_SPACING_PX)
        bar.addWidget(self._randomize_button)
        bar.addWidget(self._reset_button)
        bar.addStretch(1)
        bar.addWidget(self._status)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._sidebar)
        body.addWidget(self._stack, 1)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(body, 1)
        outer.addLayout(bar)
        self.setCentralWidget(central)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self._status.setText(""))

        self._restore_geometry()
        self._sidebar.setCurrentRow(0)
        store.changed.connect(self._on_store_changed)
        translator.language_changed.connect(self._on_language_changed)
        self.retranslate()

    # ------------------------------------------------------------------ الهندسة
    def _restore_geometry(self) -> None:
        """يستعيد الهندسة المحفوظة؛ وإلا الحجم الافتراضي (Qt يعيد النافذة داخل الشاشات المتاحة)."""
        saved = self._store.get(_GEOMETRY_KEY)
        if isinstance(saved, str) and saved:
            if self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii"))):
                return
        self.resize(*_DEFAULT_SIZE)

    def save_geometry(self) -> None:
        """يحفظ هندسة النافذة في الإعدادات (base64)."""
        encoded = bytes(self.saveGeometry().toBase64().data()).decode("ascii")
        self._store.set(_GEOMETRY_KEY, encoded)

    # ------------------------------------------------------------------ واجهة عامة
    def show_and_raise(self) -> None:
        """يُظهر النافذة ويرفعها للأمام حتى لو كانت مصغّرة أو خلف نوافذ أخرى."""
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def set_quit_on_close(self, quit_on_close: bool) -> None:
        """عند غياب شريط النظام يجب أن يُنهي إغلاق النافذة التطبيق، وإلا ضاع الوصول إليه."""
        self._quit_on_close = quit_on_close

    def show_notice(self, text: str) -> None:
        """يعرض رسالة قصيرة في شريط الحالة."""
        self._status.setText(text)
        self._status_timer.start(_NOTICE_MS)

    def retranslate(self) -> None:
        tr = self._translator.tr
        self.setWindowTitle(tr("window.title"))
        self._randomize_button.setText(tr("ui.randomize"))
        self._reset_button.setText(tr("ui.reset"))
        for index, page in enumerate(self._pages):
            item = self._sidebar.item(index)
            if item is not None:
                item.setText(tr(page.title_key))
            page.retranslate()

    def _on_language_changed(self, _code: str) -> None:
        self.retranslate()

    # ------------------------------------------------------------------ الأحداث
    def _on_store_changed(self, key: str) -> None:
        if key == _GEOMETRY_KEY:
            return  # حفظ الهندسة ليس "تغييرًا" يهم المستخدم
        self._status.setText(self._translator.tr("ui.saved"))
        self._status_timer.start(_SAVED_FLASH_MS)

    def _confirm_reset(self) -> None:
        """حوار تأكيد قبل إعادة الضبط (إجراء مدمّر)."""
        tr = self._translator.tr
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("ui.reset_confirm.title"))
        box.setText(tr("ui.reset_confirm.body"))
        confirm = box.addButton(tr("ui.confirm"), QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(tr("ui.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)  # الافتراضي الأمان: الإلغاء
        box.exec()
        if box.clickedButton() is confirm:
            self.reset_requested.emit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """الإغلاق يخفي النافذة ويبقي التطبيق في الشريط (إلا عند غياب الشريط)."""
        self.save_geometry()
        if self._quit_on_close:
            event.accept()
            QApplication.quit()
            return
        event.ignore()
        self.hide()