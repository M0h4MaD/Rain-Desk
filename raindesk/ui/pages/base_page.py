"""raindesk/ui/pages/base_page.py

الغرض: أساس صفحات الإعدادات: عنوان وبطاقات وربط ثنائي الاتجاه بين الأدوات والمخزن.
المسؤوليات: دوال bind_* (أداة إلى المخزن بالتفاعل، ومن المخزن إلى الأداة مع حجب الإشارات)،
    وصفوف "اسم + أداة" مترجمة، وإعادة الترجمة، وتحديث الربط بعد load/استيراد/إعادة ضبط.
الاعتماديات: PySide6 وraindesk.config.store وraindesk.i18n.translator وأدوات الواجهة.
النمط التصميمي: Template Method (كل صفحة تبني بطاقاتها) مع Observer على SettingsStore.
ملاحظات: الربط يتجنّب الحلقات: التحديث القادم من المخزن يُجرى والإشارات محجوبة. المخزن بدوره
    لا يصدر changed إلا عند تغيّر فعلي فلا تتكرر الكتابة. عُدّلت retranslate() لتكون
    مطبَّقة هنا (تنفّذ المكوّنات المسجَّلة)، وتستدعيها الصفحات الفرعية بـ super().
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.ui.widgets.color_button import ColorButton
from raindesk.ui.widgets.labeled_slider import LabeledSlider
from raindesk.ui.widgets.section_card import SectionCard
from raindesk.ui.widgets.toggle_switch import ToggleSwitch

_PAGE_MARGIN_PX = 24
_PAGE_SPACING_PX = 16
_ROW_SPACING_PX = 12
_TIP_SUFFIX = ".tip"


def _as_float(value: object) -> float:
    """يحوّل قيمة مخزن إلى float بأمان (bool ليس رقمًا هنا)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


class BasePage(QWidget):
    """صفحة إعدادات؛ الفئات الفرعية تُعرّف title_key وتبني بطاقاتها في __init__."""

    title_key: str = ""

    def __init__(
        self, store: SettingsStore, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._translator = translator
        self._updaters: dict[str, list[Callable[[object], None]]] = {}
        self._hooks: list[Callable[[], None]] = []

        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        self._root = QVBoxLayout(self)
        margin = _PAGE_MARGIN_PX
        self._root.setContentsMargins(margin, margin, margin, margin)
        self._root.setSpacing(_PAGE_SPACING_PX)
        self._root.addWidget(self._title)
        self._root.addStretch(1)  # تُدرَج البطاقات قبل هذا الفراغ المرن

        store.changed.connect(self._on_store_changed)
        store.reloaded.connect(self.refresh_bindings)

    # ------------------------------------------------------------------ البناء
    def add_card(self, card: SectionCard) -> None:
        """يضيف بطاقة قبل الفراغ المرن ويسجّل إعادة ترجمتها."""
        self._root.insertWidget(self._root.count() - 1, card)
        self.add_retranslate_hook(card.retranslate)

    def add_retranslate_hook(self, hook: Callable[[], None]) -> None:
        """يسجّل دالة تُستدعى عند تغيّر اللغة."""
        self._hooks.append(hook)

    def make_row(self, label_key: str, control: QWidget, tip_key: str | None = None) -> QWidget:
        """صف: اسم مترجم على جهة البداية والأداة على جهة النهاية (يتبدلان تلقائيًا في RTL)."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_ROW_SPACING_PX)
        label = QLabel()
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        resolved_tip = tip_key or label_key.removesuffix(".label") + _TIP_SUFFIX

        def retranslate() -> None:
            text = self._translator.tr(label_key)
            tip = self._translator.tr(resolved_tip)
            label.setText(text)
            control.setAccessibleName(text)
            control.setToolTip("" if tip == resolved_tip else tip)

        self.add_retranslate_hook(retranslate)
        retranslate()
        return row

    @staticmethod
    def fill_combo(combo: QComboBox, items: list[tuple[str, str]]) -> None:
        """يملأ القائمة بأزواج (الرمز، النص) مع الحفاظ على الاختيار الحالي وحجب الإشارات."""
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for code, text in items:
            combo.addItem(text, code)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    # ------------------------------------------------------------------ الربط ثنائي الاتجاه
    def _register(self, key: str, updater: Callable[[object], None]) -> None:
        self._updaters.setdefault(key, []).append(updater)

    def _write(self, key: str, value: object) -> None:
        self._store.set(key, value)

    def watch_key(self, key: str, callback: Callable[[object], None]) -> None:
        """يستدعي callback(القيمة) الآن وعند كل تغيّر في المفتاح (لمنطق إضافي مثل التعطيل)."""
        self._register(key, callback)
        callback(self._store.get(key))

    def bind_slider(self, key: str, slider: LabeledSlider) -> None:
        slider.set_value(_as_float(self._store.get(key)), emit=False)
        slider.value_changed.connect(partial(self._write, key))
        self._register(key, lambda value: slider.set_value(_as_float(value), emit=False))

    def bind_switch(self, key: str, switch: ToggleSwitch) -> None:
        switch.setChecked(bool(self._store.get(key)))
        switch.toggled.connect(partial(self._write, key))

        def update(value: object) -> None:
            switch.blockSignals(True)
            switch.setChecked(bool(value))
            switch.blockSignals(False)

        self._register(key, update)

    def bind_combo(
        self,
        key: str,
        combo: QComboBox,
        apply: Callable[[object], None] | None = None,
    ) -> None:
        """يربط قائمة منسدلة بمفتاح؛ apply يستبدل الكتابة المباشرة (مثل اختيار preset)."""
        handler = apply if apply is not None else partial(self._write, key)

        def select(value: object) -> None:
            index = combo.findData(value)
            if index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)

        select(self._store.get(key))
        combo.currentIndexChanged.connect(lambda index: handler(combo.itemData(index)))
        self._register(key, select)

    def bind_color(self, key: str, button: ColorButton) -> None:
        button.set_color(str(self._store.get(key)))
        button.color_changed.connect(partial(self._write, key))
        self._register(key, lambda value: button.set_color(str(value)))

    def _on_store_changed(self, key: str) -> None:
        for updater in self._updaters.get(key, ()):
            updater(self._store.get(key))

    def refresh_bindings(self) -> None:
        """يعيد مزامنة كل الأدوات من المخزن (بعد load أو استيراد أو إعادة ضبط)."""
        for key, updaters in self._updaters.items():
            value = self._store.get(key)
            for updater in updaters:
                updater(value)

    # ------------------------------------------------------------------ الترجمة
    def retranslate(self) -> None:
        """يحدّث العنوان وكل المكوّنات المسجَّلة؛ الفئات الفرعية تضيف ما يخصها بعد super()."""
        self._title.setText(self._translator.tr(self.title_key))
        for hook in self._hooks:
            hook()