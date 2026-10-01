"""raindesk/ui/widgets/section_card.py

الغرض: بطاقة بزوايا مستديرة بعنوان ووصف اختياري، تحمل صفوف الإعدادات.
المسؤوليات: بناء الرأس، وإضافة الصفوف، وإعادة الترجمة.
الاعتماديات: PySide6 وraindesk.i18n.translator.
النمط التصميمي: Composite بسيط (حاوية بعنوان).
ملاحظات: المظهر (الخلفية والحد والزوايا) يأتي من QSS عبر objectName 'SectionCard'.
مثال: card = SectionCard('card.behavior.title', 'card.behavior.desc', translator)
"""

from __future__ import annotations

from typing import Final

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from raindesk.i18n.translator import Translator

_PADDING_PX: Final[int] = 20  # بين 16 و24 حسب المواصفة
_SPACING_PX: Final[int] = 12


class SectionCard(QFrame):
    """بطاقة قسم؛ add_row يضيف عنصرًا تحت الرأس."""

    def __init__(
        self,
        title_key: str,
        description_key: str | None,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self._title_key = title_key
        self._description_key = description_key
        self._translator = translator

        self._title = QLabel()
        self._title.setObjectName("CardTitle")
        self._description = QLabel()
        self._description.setObjectName("Caption")
        self._description.setWordWrap(True)
        self._description.setVisible(description_key is not None)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(_PADDING_PX, _PADDING_PX, _PADDING_PX, _PADDING_PX)
        self._layout.setSpacing(_SPACING_PX)
        self._layout.addWidget(self._title)
        self._layout.addWidget(self._description)
        self.retranslate()

    def add_row(self, widget: QWidget) -> None:
        """يضيف صفًا (أي QWidget) في أسفل البطاقة."""
        self._layout.addWidget(widget)

    def retranslate(self) -> None:
        self._title.setText(self._translator.tr(self._title_key))
        if self._description_key is not None:
            self._description.setText(self._translator.tr(self._description_key))