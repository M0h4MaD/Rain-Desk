"""raindesk/ui/pages/effects_page.py

الغرض: صفحة المؤثرات: الرذاذ، وجداول الحواف، وتظليل الأجواء، والبرق، والطقس التلقائي.
المسؤوليات: أدوات مربوطة بالمخزن، وتعطيل التوابع عند إيقاف مفتاحها الرئيسي، وتحذير حساسية
    الضوء للبرق، وتعطيل البرق إذا أوقف المستخدم رسوم Windows المتحركة.
الاعتماديات: raindesk.ui.pages.base_page وraindesk.platform_win.win32_api وأدوات الواجهة.
ملاحظة: بطاقة الصوت تُضاف إلى هذه الصفحة في مرحلة الصوت (M8A).
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.platform_win import win32_api
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.color_button import ColorButton
from raindesk.ui.widgets.section_card import SectionCard

_SPLASH_ZONES = ("bottom_edge", "depth_plane")


class EffectsPage(BasePage):
    """صفحة المؤثرات."""

    title_key = "nav.effects"

    def __init__(
        self, store: SettingsStore, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(store, translator, parent)
        self._animations_ok = win32_api.client_animations_enabled()
        self._lightning_note = QLabel()
        self._lightning_note.setObjectName("Note")
        self._lightning_note.setWordWrap(True)
        self._add_splashes()
        self._add_streams()
        self._add_mood()
        self._add_lightning()
        self._add_weather()
        self.retranslate()

    # ------------------------------------------------------------------ البطاقات
    def _add_splashes(self) -> None:
        card = SectionCard("card.splashes.title", "card.splashes.desc", self._translator)
        card.add_row(self.make_row("setting.splashes_enabled.label",
                                   self.make_switch("splashes_enabled")))
        amount = self.make_slider("splash_amount")
        zone = self.make_combo("splash_zone", self.choice_items("splash_zone", _SPLASH_ZONES))
        zone_row = self.make_row("setting.splash_zone.label", zone)
        card.add_row(amount)
        card.add_row(zone_row)
        self.link_enabled("splashes_enabled", amount, zone_row)
        self.add_card(card)

    def _add_streams(self) -> None:
        card = SectionCard("card.streams.title", "card.streams.desc", self._translator)
        card.add_row(self.make_row("setting.edge_streams_enabled.label",
                                   self.make_switch("edge_streams_enabled")))
        count = self.make_slider("edge_streams_count", "", 0)
        opacity = self.make_slider("edge_streams_opacity")
        card.add_row(count)
        card.add_row(opacity)
        self.link_enabled("edge_streams_enabled", count, opacity)
        self.add_card(card)

    def _add_mood(self) -> None:
        card = SectionCard("card.mood.title", "card.mood.desc", self._translator)
        card.add_row(self.make_row("setting.mood_enabled.label",
                                   self.make_switch("mood_enabled")))
        color = ColorButton(self._translator)
        self.bind_color("mood_color", color)
        self.add_retranslate_hook(color.retranslate)
        color_row = self.make_row("setting.mood_color.label", color)
        opacity = self.make_slider("mood_opacity")
        card.add_row(color_row)
        card.add_row(opacity)
        self.link_enabled("mood_enabled", color_row, opacity)
        self.add_card(card)

    def _add_lightning(self) -> None:
        card = SectionCard("card.lightning.title", "card.lightning.desc", self._translator)
        switch = self.make_switch("lightning_enabled")
        switch.setEnabled(self._animations_ok)  # بلا رسوم متحركة لا برق (حساسية الضوء)
        card.add_row(self.make_row("setting.lightning_enabled.label", switch))
        frequency = self.make_slider("lightning_frequency")
        card.add_row(frequency)
        card.add_row(self._lightning_note)
        self.watch_key(
            "lightning_enabled",
            lambda value: frequency.setEnabled(bool(value) and self._animations_ok),
        )
        self.add_card(card)

    def _add_weather(self) -> None:
        card = SectionCard("card.weather.title", "card.weather.desc", self._translator)
        card.add_row(self.make_row("setting.auto_weather.label",
                                   self.make_switch("auto_weather")))
        variability = self.make_slider("auto_weather_variability")
        card.add_row(variability)
        self.link_enabled("auto_weather", variability)
        self.add_card(card)

    # ------------------------------------------------------------------ الترجمة
    def retranslate(self) -> None:
        super().retranslate()
        text = self._translator.tr("note.lightning_warning")
        if not self._animations_ok:
            text += "\n" + self._translator.tr("note.lightning_animations_off")
        self._lightning_note.setText(text)