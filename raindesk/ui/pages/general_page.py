"""raindesk/ui/pages/general_page.py

الغرض: الصفحة العامة: السلوك (تشغيل، بدء مع ويندوز، بدء مخفيًا) والمظهر (اللغة والسمة).
الاعتماديات: raindesk.ui.pages.base_page وأدوات الواجهة.
ملاحظة: مفتاح "التشغيل مع ويندوز" يُحفظ الآن ويبدأ مفعوله في مرحلة تكامل النظام (M8).
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QWidget

from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.section_card import SectionCard
from raindesk.ui.widgets.toggle_switch import ToggleSwitch

_COMBO_MIN_WIDTH_PX = 200
_THEME_CODES = ("system", "light", "dark")


class GeneralPage(BasePage):
    """الصفحة العامة."""

    title_key = "nav.general"

    def __init__(
        self, store: SettingsStore, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(store, translator, parent)

        behavior = SectionCard("card.behavior.title", "card.behavior.desc", translator)
        for key in ("enabled", "launch_at_login", "start_hidden_in_tray"):
            switch = ToggleSwitch()
            self.bind_switch(key, switch)
            behavior.add_row(self.make_row(f"setting.{key}.label", switch))
        self.add_card(behavior)

        appearance = SectionCard("card.appearance.title", "card.appearance.desc", translator)
        self._language = QComboBox()
        self._theme = QComboBox()
        for combo in (self._language, self._theme):
            combo.setMinimumWidth(_COMBO_MIN_WIDTH_PX)
        self._fill_language()
        self._fill_theme()
        self.bind_combo("language", self._language)
        self.bind_combo("theme", self._theme)
        appearance.add_row(self.make_row("setting.language.label", self._language))
        appearance.add_row(self.make_row("setting.theme.label", self._theme))
        self.add_card(appearance)

        self.retranslate()

    def _fill_language(self) -> None:
        self.fill_combo(self._language, self._translator.available_languages())

    def _fill_theme(self) -> None:
        items = [(code, self._translator.tr(f"theme.{code}")) for code in _THEME_CODES]
        self.fill_combo(self._theme, items)

    def retranslate(self) -> None:
        super().retranslate()
        self._fill_language()  # اسم خيار "تلقائي" يتغير مع اللغة
        self._fill_theme()