"""raindesk/ui/pages/mascot_page.py

الغرض: صفحة الشخصية Drip: تشغيلها وتكرار ظهورها وحجمها.
الاعتماديات: raindesk.ui.pages.base_page وأدوات الواجهة.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.section_card import SectionCard


class MascotPage(BasePage):
    """صفحة الشخصية."""

    title_key = "nav.mascot"

    def __init__(
        self, store: SettingsStore, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(store, translator, parent)
        card = SectionCard("card.mascot.title", "card.mascot.desc", translator)
        card.add_row(self.make_row("setting.mascot_enabled.label",
                                   self.make_switch("mascot_enabled")))
        frequency = self.make_slider("mascot_frequency")
        scale = self.make_slider("mascot_scale")
        card.add_row(frequency)
        card.add_row(scale)
        self.link_enabled("mascot_enabled", frequency, scale)
        self.add_card(card)
        self.retranslate()