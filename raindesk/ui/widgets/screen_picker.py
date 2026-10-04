"""raindesk/ui/widgets/screen_picker.py

الغرض: قائمة مربعات اختيار بعدد الشاشات المتصلة (الاسم والدقة وشارة "أساسية").
المسؤوليات: عرض الشاشات المكتشفة، وتتبّع اختيار المستخدم، وتحديث القائمة عند توصيل/فصل
    الشاشات أو تغيّر الأساسية، مع الاحتفاظ باختيارات شاشات غير متصلة حاليًا.
الاعتماديات: PySide6 وraindesk.ui.overlay_window (compute_screen_key) وraindesk.i18n.translator.
النمط التصميمي: Composite (قائمة مربعات) مع Observer على إشارات QGuiApplication.
ملاحظات: المفتاح هو نفسه الذي تستعمله OverlayManager، فيطابق اختيار المستخدم النوافذ تمامًا.
    الاختيار الداخلي مجموعة (set) تحتفظ بمفاتيح الشاشات الغائبة، فيعود اختيارها عند إعادة توصيلها.
مثال: picker = ScreenPicker(translator); picker.selection_changed.connect(save)
"""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from raindesk.i18n.translator import Translator
from raindesk.ui.overlay_window import compute_screen_key

_SPACING_PX = 8
_MULTIPLY_SIGN = "\u00d7"  # علامة الضرب بين العرض والارتفاع
_BULLET = "\u2022"


class ScreenPicker(QWidget):
    """منتقي الشاشات؛ selection_changed(list) يصدر من نقر المستخدم فقط."""

    selection_changed = Signal(list)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._selection: set[str] = set()
        self._boxes: dict[str, QCheckBox] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(_SPACING_PX)

        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)
            app.primaryScreenChanged.connect(self._on_screens_changed)
        self.refresh()

    # ------------------------------------------------------------------ الواجهة العامة
    def set_selection(self, keys: list[str]) -> None:
        """يضبط الاختيار دون إصدار إشارة (يُستعمل لمزامنة الأداة من المخزن)."""
        self._selection = set(keys)
        for key, box in self._boxes.items():
            box.blockSignals(True)
            box.setChecked(key in self._selection)
            box.blockSignals(False)

    def refresh(self) -> None:
        """يعيد بناء القائمة من الشاشات المتصلة حاليًا مع الحفاظ على الاختيار."""
        for box in self._boxes.values():
            self._layout.removeWidget(box)
            box.deleteLater()
        self._boxes.clear()
        primary = QGuiApplication.primaryScreen()
        for index, screen in enumerate(QGuiApplication.screens(), start=1):
            key = compute_screen_key(screen)
            text = self._describe(index, screen, is_primary=screen is primary)
            box = QCheckBox(text)
            box.setAccessibleName(text)
            box.setChecked(key in self._selection)
            box.toggled.connect(partial(self._on_toggled, key))
            self._layout.addWidget(box)
            self._boxes[key] = box

    def retranslate(self) -> None:
        self.refresh()  # شارة "أساسية" نص مترجم

    # ------------------------------------------------------------------ داخلي
    def _describe(self, index: int, screen: QScreen, *, is_primary: bool) -> str:
        """وصف الشاشة: رقمها واسمها (والطراز إن وُجد) والدقة الأصلية وشارة الأساسية."""
        size = screen.geometry().size()
        ratio = screen.devicePixelRatio()  # الدقة الأصلية = الحجم المنطقي * معامل DPI
        width, height = round(size.width() * ratio), round(size.height() * ratio)
        model = screen.model().strip()
        name = f"{model} {screen.name()}".strip() if model else screen.name()
        text = f"{index}. {name}  ({width}{_MULTIPLY_SIGN}{height})"
        if is_primary:
            text += f"  {_BULLET}  {self._translator.tr('display.primary_badge')}"
        return text

    def _on_toggled(self, key: str, checked: bool) -> None:
        if checked:
            self._selection.add(key)
        else:
            self._selection.discard(key)
        self.selection_changed.emit(sorted(self._selection))

    def _on_screens_changed(self, *_args: object) -> None:
        """يؤجّل التحديث إلى الدورة التالية كي تكون قائمة الشاشات قد استقرت."""
        QTimer.singleShot(0, self.refresh)