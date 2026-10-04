"""raindesk/ui/pages/display_page.py

الغرض: صفحة العرض والأداء: الشاشات، وشريط المهام، والجودة، ومعدل الإطارات، والإيقاف المؤقت.
المسؤوليات: منتقي الشاشات (يُفعَّل عند وضع "شاشات أختارها" فقط)، وقائمة الجودة التي تكتب
    fps_cap وantialiasing معًا عبر apply_quality، وبقية الخيارات الحية.
الاعتماديات: raindesk.ui.pages.base_page وأدوات الواجهة.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from raindesk.config.store import SettingsStore
from raindesk.i18n.translator import Translator
from raindesk.platform_win import win32_api
from raindesk.ui.pages.base_page import BasePage
from raindesk.ui.widgets.screen_picker import ScreenPicker
from raindesk.ui.widgets.section_card import SectionCard

_SCREEN_MODES = ("all", "primary", "selected")
_QUALITY_CODES = ("low", "balanced", "high")
_FPS_UNIT = " fps"
_MIN_BUILD_CAPTURE_EXCLUSION = 19041  # Windows 10 الإصدار 2004


class DisplayPage(BasePage):
    """صفحة العرض والأداء."""

    title_key = "nav.display"

    def __init__(
        self,
        store: SettingsStore,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(store, translator, parent)

        screens = SectionCard("card.screens.title", "card.screens.desc", translator)
        mode = self.make_combo(
            "screens_mode", self.choice_items("screens_mode", _SCREEN_MODES)
        )
        screens.add_row(self.make_row("setting.screens_mode.label", mode))
        picker = ScreenPicker(translator)
        self.bind_screens("selected_screens", picker)
        self.add_retranslate_hook(picker.retranslate)
        screens.add_row(picker)
        self.link_enabled("screens_mode", picker, when_equals="selected")
        screens.add_row(
            self.make_row(
                "setting.cover_taskbar.label", self.make_switch("cover_taskbar")
            )
        )
        self.add_card(screens)

        performance = SectionCard(
            "card.performance.title", "card.performance.desc", translator
        )
        quality = self.make_combo(
            "quality",
            self.choice_items("quality", _QUALITY_CODES),
            self._on_quality_chosen,
        )
        performance.add_row(self.make_row("setting.quality.label", quality))
        performance.add_row(self.make_slider("fps_cap", _FPS_UNIT, 0))
        performance.add_row(
            self.make_row(
                "setting.antialiasing.label", self.make_switch("antialiasing")
            )
        )
        self.add_card(performance)

        pause = SectionCard("card.pause.title", "card.pause.desc", translator)
        for key in (
            "pause_on_fullscreen",
            "pause_on_battery_saver",
            "exclude_from_capture",
        ):
            switch = self.make_switch(key)
            if key == "exclude_from_capture":
                # يتطلب Windows 10 بناء 19041+؛ نعطّله هنا وتلميحه يشرح السبب (الخيار تجريبي).
                switch.setEnabled(
                    win32_api.windows_build() >= _MIN_BUILD_CAPTURE_EXCLUSION
                )
            pause.add_row(self.make_row(f"setting.{key}.label", switch))
        self.add_card(pause)
        self.retranslate()

    def _on_quality_chosen(self, data: object) -> None:
        """اختيار ملف جودة يكتب quality وfps_cap وantialiasing دفعة واحدة."""
        self._store.apply_quality(str(data))
