"""raindesk/ui/pages/rain_page.py

الغرض: صفحة المطر والرياح: الإعدادات المسبقة وخصائص القطرات والرياح.
المسؤوليات: منزلقات مربوطة بالمخزن (الحدود من FIELD_SPECS فلا تكرار)، وقائمة الإعدادات
    المسبقة، وتعطيل العناصر التي يديرها الطقس التلقائي مع ملاحظة توضيحية.
الاعتماديات: raindesk.ui.pages.base_page وraindesk.config.schema وأدوات الواجهة.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel, QWidget

from raindesk.config.schema import FIELD_SPECS, PRESETS
from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.color_button import ColorButton
from raindesk.ui.widgets.labeled_slider import LabeledSlider
from raindesk.ui.widgets.section_card import SectionCard

_COMBO_MIN_WIDTH_PX = 200
_DEGREE = "°"
_SECONDS = " s"


class RainPage(BasePage):
    """صفحة المطر والرياح."""

    title_key = "nav.rain"

    def __init__(
        self, store: SettingsStore, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(store, translator, parent)
        self._managed: list[QWidget] = []  # عناصر يتحكم بها الطقس التلقائي

        # --- بطاقة الإعدادات المسبقة ---
        preset_card = SectionCard("card.preset.title", "card.preset.desc", translator)
        self._preset = QComboBox()
        self._preset.setMinimumWidth(_COMBO_MIN_WIDTH_PX)
        self._fill_presets()
        self.bind_combo("preset", self._preset, apply=self._on_preset_chosen)
        preset_card.add_row(self.make_row("setting.preset.label", self._preset))
        self._note = QLabel()
        self._note.setObjectName("Note")
        self._note.setWordWrap(True)
        preset_card.add_row(self._note)
        self._managed.append(self._preset)
        self.add_card(preset_card)

        # --- بطاقة القطرات ---
        drops = SectionCard("card.drops.title", "card.drops.desc", translator)
        for key in ("intensity", "speed", "drop_length", "drop_thickness", "drop_opacity"):
            slider = self._make_slider(key, "", 2)
            drops.add_row(slider)
            self._managed.append(slider)
        self._color = ColorButton(translator)
        self.bind_color("drop_color", self._color)
        self.add_retranslate_hook(self._color.retranslate)
        drops.add_row(self.make_row("setting.drop_color.label", self._color))
        drops.add_row(self._make_slider("parallax_strength", "", 2))
        self.add_card(drops)

        # --- بطاقة الرياح ---
        wind = SectionCard("card.wind.title", "card.wind.desc", translator)
        angle = self._make_slider("wind_angle_deg", _DEGREE, 1)
        gusts = self._make_slider("wind_gusts", "", 2)
        wind.add_row(angle)
        wind.add_row(gusts)
        wind.add_row(self._make_slider("gust_period_s", _SECONDS, 1))
        self._managed.extend((angle, gusts))
        self.add_card(wind)

        self.watch_key("auto_weather", self._on_auto_weather)
        self.retranslate()

    # ------------------------------------------------------------------ البناء
    def _make_slider(self, key: str, unit: str, decimals: int) -> LabeledSlider:
        """منزلق لمفتاح رقمي: الحدود والخطوة والافتراضي من FIELD_SPECS."""
        spec = FIELD_SPECS[key]
        assert spec.minimum is not None and spec.maximum is not None and spec.step is not None
        slider = LabeledSlider(
            key, f"setting.{key}.label", spec.minimum, spec.maximum, spec.step,
            float(spec.default), unit, decimals, self._translator,  # type: ignore[arg-type]
        )
        self.bind_slider(key, slider)
        self.add_retranslate_hook(slider.retranslate)
        return slider

    def _fill_presets(self) -> None:
        codes = ["custom", *PRESETS]
        self.fill_combo(self._preset, [(c, self._translator.tr(f"preset.{c}")) for c in codes])

    def _on_preset_chosen(self, data: object) -> None:
        self._store.apply_preset(str(data))

    def _on_auto_weather(self, value: object) -> None:
        """الطقس التلقائي يدير هذه القيم، فنعطّل عناصرها ونُظهر الملاحظة."""
        automatic = bool(value)
        for widget in self._managed:
            widget.setEnabled(not automatic)
        self._note.setVisible(automatic)

    def retranslate(self) -> None:
        super().retranslate()
        self._fill_presets()
        self._note.setText(self._translator.tr("note.auto_weather"))