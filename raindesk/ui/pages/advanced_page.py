"""raindesk/ui/pages/advanced_page.py

الغرض: صفحة المتقدم: خيارات المحرك، والاستيراد والتصدير، ومجلد السجلات.
المسؤوليات: أدوات مربوطة بالمخزن، وحوارات اختيار الملفات للاستيراد والتصدير مع رسالة نتيجة
    ظاهرة، وفتح مجلد السجلات في مستكشف Windows.
الاعتماديات: raindesk.ui.pages.base_page وraindesk.core.paths وأدوات الواجهة.
ملاحظة: خيار "لوحة التشخيص" يُحفظ الآن وتظهر اللوحة في مرحلة لاحقة (M8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from raindesk.config.schema import FIELD_SPECS
from raindesk.config.store import SettingsStore
from raindesk.core.paths import log_dir
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.section_card import SectionCard

_LOG_LEVELS: Final[tuple[str, ...]] = ("DEBUG", "INFO", "WARNING", "ERROR")
_DEFAULT_EXPORT_NAME: Final[str] = "raindesk-settings.json"
_SPIN_MIN_WIDTH_PX: Final[int] = 160
_BUTTON_SPACING_PX: Final[int] = 8
_JSON_SUFFIX: Final[str] = ".json"


class AdvancedPage(BasePage):
    """صفحة المتقدم."""

    title_key = "nav.advanced"

    def __init__(
        self, store: SettingsStore, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(store, translator, parent)
        self._import_button = QPushButton()
        self._export_button = QPushButton()
        self._logs_button = QPushButton()
        self._feedback = QLabel()
        self._feedback.setObjectName("Caption")
        self._feedback.setWordWrap(True)
        self._add_engine_card()
        self._add_data_card()
        self.retranslate()

    # ------------------------------------------------------------------ البطاقات
    def _add_engine_card(self) -> None:
        card = SectionCard("card.engine.title", "card.engine.desc", self._translator)
        card.add_row(self.make_row("setting.adaptive_quality.label",
                                   self.make_switch("adaptive_quality")))
        card.add_row(self.make_slider("depth_layers", "", 0))
        card.add_row(self.make_row("setting.topmost_watchdog.label",
                                   self.make_switch("topmost_watchdog")))
        card.add_row(self.make_row("setting.debug_hud.label", self.make_switch("debug_hud")))
        level = self.make_combo("log_level", lambda: [(name, name) for name in _LOG_LEVELS])
        card.add_row(self.make_row("setting.log_level.label", level))

        spec = FIELD_SPECS["rng_seed"]
        seed = QSpinBox()
        seed.setRange(
            int(spec.minimum) if spec.minimum is not None else -1,
            int(spec.maximum) if spec.maximum is not None else 2147483647,
        )
        seed.setKeyboardTracking(False)  # القيمة تُكتب عند Enter أو فقدان التركيز لا مع كل رقم
        seed.setMinimumWidth(_SPIN_MIN_WIDTH_PX)
        self.bind_spin("rng_seed", seed)
        card.add_row(self.make_row("setting.rng_seed.label", seed))
        self.add_card(card)

    def _add_data_card(self) -> None:
        card = SectionCard("card.data.title", "card.data.desc", self._translator)
        buttons = QWidget()
        layout = QHBoxLayout(buttons)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_BUTTON_SPACING_PX)
        for button in (self._import_button, self._export_button, self._logs_button):
            layout.addWidget(button)
        layout.addStretch(1)
        self._import_button.clicked.connect(self._import_settings)
        self._export_button.clicked.connect(self._export_settings)
        self._logs_button.clicked.connect(self._open_logs)
        card.add_row(buttons)
        card.add_row(self._feedback)
        self.add_card(card)

    # ------------------------------------------------------------------ الإجراءات
    def _import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self._translator.tr("dialog.import_title"), "",
            self._translator.tr("dialog.json_filter"),
        )
        if not path:
            return  # أُلغي الحوار
        ok = self._store.import_from(Path(path))
        self._feedback.setText(self._translator.tr("msg.import_ok" if ok else "msg.import_failed"))

    def _export_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self._translator.tr("dialog.export_title"), _DEFAULT_EXPORT_NAME,
            self._translator.tr("dialog.json_filter"),
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(_JSON_SUFFIX)
        ok = self._store.export_to(target)
        self._feedback.setText(self._translator.tr("msg.export_ok" if ok else "msg.export_failed"))

    def _open_logs(self) -> None:
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))
        self._feedback.setText("" if opened else self._translator.tr("msg.open_logs_failed"))

    # ------------------------------------------------------------------ الترجمة
    def retranslate(self) -> None:
        super().retranslate()
        tr = self._translator.tr
        self._import_button.setText(tr("button.import"))
        self._export_button.setText(tr("button.export"))
        self._logs_button.setText(tr("button.open_logs"))
        self._feedback.setText("")  # رسالة النتيجة السابقة بلغة قديمة