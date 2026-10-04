"""raindesk/ui/pages/base_page.py

الغرض: أساس صفحات الإعدادات: عنوان وبطاقات وربط ثنائي الاتجاه بين الأدوات والمخزن.
المسؤوليات: دوال bind_* وmake_* (أداة مربوطة بالمخزن بخطوة واحدة)، وصفوف "اسم + أداة" مترجمة،
    وربط التفعيل بقيمة مفتاح (link_enabled)، وإعادة الترجمة، وتحديث الربط بعد load/استيراد/ضبط.
الاعتماديات: PySide6 وraindesk.config وraindesk.i18n.translator وأدوات الواجهة.
النمط التصميمي: Template Method (كل صفحة تبني بطاقاتها) مع Observer على SettingsStore.
ملاحظات: الربط يتجنّب الحلقات: التحديث القادم من المخزن يُجرى والإشارات محجوبة. المخزن بدوره
    لا يصدر changed إلا عند تغيّر فعلي فلا تتكرر الكتابة. حدود المنزلقات تُقرأ من FIELD_SPECS
    فلا تتكرر في الصفحات. retranslate() مطبَّقة هنا وتستدعيها الصفحات الفرعية بـ super().
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from raindesk.config.schema import FIELD_SPECS
from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.ui.widgets.color_button import ColorButton
from raindesk.ui.widgets.labeled_slider import LabeledSlider
from raindesk.ui.widgets.screen_picker import ScreenPicker
from raindesk.ui.widgets.section_card import SectionCard
from raindesk.ui.widgets.toggle_switch import ToggleSwitch

_PAGE_MARGIN_PX = 24
_PAGE_SPACING_PX = 16
_ROW_SPACING_PX = 12
_COMBO_MIN_WIDTH_PX = 200
_TIP_SUFFIX = ".tip"


def _as_float(value: object) -> float:
    """يحوّل قيمة مخزن إلى float بأمان (bool ليس رقمًا هنا)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _as_str_list(value: object) -> list[str]:
    """قائمة النصوص من قيمة مخزن (أي نوع آخر يعطي قائمة فارغة)."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


class BasePage(QWidget):
    """صفحة إعدادات؛ الفئات الفرعية تُعرّف title_key وتبني بطاقاتها في __init__."""

    title_key: str = ""

    def __init__(
        self,
        store: SettingsStore,
        translator: Translator,
        parent: QWidget | None = None,
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

    def make_row(
        self, label_key: str, control: QWidget, tip_key: str | None = None
    ) -> QWidget:
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

    def choice_items(
        self, prefix: str, codes: Sequence[str]
    ) -> Callable[[], list[tuple[str, str]]]:
        """دالة تنتج عناصر قائمة منسدلة بنصوص مترجمة بالمفاتيح 'prefix.code'."""

        def items() -> list[tuple[str, str]]:
            return [(code, self._translator.tr(f"{prefix}.{code}")) for code in codes]

        return items

    # ------------------------------------------------------------------ أدوات جاهزة مربوطة
    def make_slider(self, key: str, unit: str = "", decimals: int = 2) -> LabeledSlider:
        """منزلق لمفتاح رقمي: الحدود والخطوة والافتراضي من FIELD_SPECS، مربوط ومسجَّل للترجمة."""
        spec = FIELD_SPECS[key]
        if spec.minimum is None or spec.maximum is None or spec.step is None:
            raise ValueError(f"{key} is not a numeric setting")
        slider = LabeledSlider(
            key,
            f"setting.{key}.label",
            spec.minimum,
            spec.maximum,
            spec.step,
            _as_float(spec.default),
            unit,
            decimals,
            self._translator,
        )
        self.bind_slider(key, slider)
        self.add_retranslate_hook(slider.retranslate)
        return slider

    def make_switch(self, key: str) -> ToggleSwitch:
        """مفتاح تبديل مربوط بمفتاح منطقي (لا يُضاف إلى تخطيط؛ استعمل make_row)."""
        switch = ToggleSwitch()
        self.bind_switch(key, switch)
        return switch

    def make_combo(
        self,
        key: str,
        items: Callable[[], list[tuple[str, str]]],
        apply: Callable[[object], None] | None = None,
    ) -> QComboBox:
        """قائمة منسدلة مربوطة تُعاد تعبئتها بنصوص مترجمة عند تغيّر اللغة."""
        combo = QComboBox()
        combo.setMinimumWidth(_COMBO_MIN_WIDTH_PX)
        self.fill_combo(combo, items())
        self.bind_combo(key, combo, apply)
        self.add_retranslate_hook(lambda: self.fill_combo(combo, items()))
        return combo

    def link_enabled(
        self, key: str, *widgets: QWidget, when_equals: object = True
    ) -> None:
        """يفعّل الأدوات فقط عندما تساوي قيمة المفتاح when_equals (الافتراضي True)."""

        def update(value: object) -> None:
            enabled = value == when_equals
            for widget in widgets:
                widget.setEnabled(enabled)

        self.watch_key(key, update)

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
        self._register(
            key, lambda value: slider.set_value(_as_float(value), emit=False)
        )

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

    def bind_spin(self, key: str, spin: QSpinBox) -> None:
        """يربط QSpinBox صحيحًا بمفتاح؛ يستحسن setKeyboardTracking(False) لتجنّب كتابة كل رقم."""
        spin.setValue(round(_as_float(self._store.get(key))))
        spin.valueChanged.connect(partial(self._write, key))

        def update(value: object) -> None:
            spin.blockSignals(True)
            spin.setValue(round(_as_float(value)))
            spin.blockSignals(False)

        self._register(key, update)

    def bind_screens(self, key: str, picker: ScreenPicker) -> None:
        """يربط منتقي الشاشات بمفتاح قائمة نصية (مفاتيح الشاشات)."""
        picker.set_selection(_as_str_list(self._store.get(key)))
        picker.selection_changed.connect(partial(self._write, key))
        self._register(key, lambda value: picker.set_selection(_as_str_list(value)))

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
