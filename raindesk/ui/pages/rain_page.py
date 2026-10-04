"""raindesk/ui/pages/rain_page.py

الغرض: صفحة المطر والرياح: الإعدادات المسبقة وخصائص القطرات والرياح.
المسؤوليات: منزلقات مربوطة بالمخزن (الحدود من FIELD_SPECS عبر BasePage)، وقائمة الإعدادات
    المسبقة، وتعطيل العناصر التي يديرها الطقس التلقائي مع ملاحظة توضيحية.
الاعتماديات: raindesk.ui.pages.base_page وraindesk.config.schema وأدوات الواجهة.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from raindesk.config.schema import PRESETS
from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.color_button import ColorButton
from raindesk.ui.widgets.section_card import SectionCard

_DEGREE = "°"
_SECONDS = " s"


class RainPage(BasePage):
    """صفحة المطر والرياح."""

    title_key = "nav.rain"

    def __init__(
        self,
        store: SettingsStore,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(store, translator, parent)
        managed: list[QWidget] = []  # عناصر يتحكم بها الطقس التلقائي

        # --- بطاقة الإعدادات المسبقة ---
        preset_card = SectionCard("card.preset.title", "card.preset.desc", translator)
        preset = self.make_combo(
            "preset",
            self.choice_items("preset", ["custom", *PRESETS]),
            self._on_preset_chosen,
        )
        preset_card.add_row(self.make_row("setting.preset.label", preset))
        self._note = QLabel()
        self._note.setObjectName("Note")
        self._note.setWordWrap(True)
        preset_card.add_row(self._note)
        managed.append(preset)
        self.add_card(preset_card)

        # --- بطاقة القطرات ---
        drops = SectionCard("card.drops.title", "card.drops.desc", translator)
        for key in (
            "intensity",
            "speed",
            "drop_length",
            "drop_thickness",
            "drop_opacity",
        ):
            slider = self.make_slider(key)
            drops.add_row(slider)
            managed.append(slider)
        color = ColorButton(translator)
        self.bind_color("drop_color", color)
        self.add_retranslate_hook(color.retranslate)
        drops.add_row(self.make_row("setting.drop_color.label", color))
        drops.add_row(self.make_slider("parallax_strength"))
        self.add_card(drops)

        # --- بطاقة الرياح ---
        wind = SectionCard("card.wind.title", "card.wind.desc", translator)
        angle = self.make_slider("wind_angle_deg", _DEGREE, 1)
        gusts = self.make_slider("wind_gusts")
        wind.add_row(angle)
        wind.add_row(gusts)
        wind.add_row(self.make_slider("gust_period_s", _SECONDS, 1))
        managed.extend((angle, gusts))
        self.add_card(wind)

        self._managed = managed
        self.watch_key("auto_weather", self._on_auto_weather)
        self.retranslate()

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
        self._note.setText(self._translator.tr("note.auto_weather"))
