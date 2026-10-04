"""raindesk/ui/pages/about_page.py

الغرض: صفحة "حول": الإصدار وتراخيص المكتبات الحرة وبيان الخصوصية.
الاعتماديات: raindesk.ui.pages.base_page وraindesk.core.constants وأدوات الواجهة.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from raindesk.config.store import SettingsStore
from raindesk.core.constants import APP_VERSION
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.section_card import SectionCard

_LICENSE_KEYS = ("license.pyside6", "license.numpy", "license.pyinstaller", "license.python")
_PRIVACY_KEYS = ("privacy.body", "privacy.registry")


def _text_label() -> QLabel:
    """تسمية نصية تلتف على الأسطر ويمكن تحديدها بالفأرة (لنسخ رقم الإصدار مثلًا)."""
    label = QLabel()
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class AboutPage(BasePage):
    """صفحة حول."""

    title_key = "nav.about"

    def __init__(
        self, store: SettingsStore, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(store, translator, parent)
        self._tagline = _text_label()
        self._version = _text_label()
        about = SectionCard("card.about.title", None, translator)
        about.add_row(self._tagline)
        about.add_row(self._version)
        self.add_card(about)

        self._licenses = {key: _text_label() for key in _LICENSE_KEYS}
        licenses = SectionCard("card.licenses.title", "card.licenses.desc", translator)
        for label in self._licenses.values():
            licenses.add_row(label)
        self.add_card(licenses)

        self._privacy = {key: _text_label() for key in _PRIVACY_KEYS}
        privacy = SectionCard("card.privacy.title", None, translator)
        for label in self._privacy.values():
            privacy.add_row(label)
        self.add_card(privacy)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        tr = self._translator.tr
        self._tagline.setText(tr("about.tagline"))
        self._version.setText(tr("about.version", version=APP_VERSION))
        for key, label in (*self._licenses.items(), *self._privacy.items()):
            label.setText(tr(key))