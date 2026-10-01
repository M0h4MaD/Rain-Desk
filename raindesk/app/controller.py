"""raindesk/app/controller.py

الغرض: AppController: الوسيط (Mediator) الذي يوجّه أحداث الشريط والإعدادات والنسخة الواحدة.
المسؤوليات: بدء الواجهة (أول تشغيل، بدء مخفيًا)، وإنشاء نافذة الإعدادات كسولًا، وتوجيه
    تغيّر الإعدادات إلى المترجم والسمة والمدير، والعشوائي والإعدادات المسبقة والخروج.
الاعتماديات: كل طبقات الواجهة والإعدادات (الجذر app هو الوحيد المسموح له بذلك).
النمط التصميمي: Mediator. كل طرف يعرف المتحكم فقط لا بعضه بعضًا.
ملاحظات: المراقب (watcher) سيُربط في مرحلة تكامل النظام؛ الصوت وautostart في مراحلهما.
    سرعة الإطارات (fps_cap) تتولاها bootstrap لأنها تملك FrameClock.
مثال: controller = AppController(store, translator, theme, manager, None, tray, guard)
"""

from __future__ import annotations

import logging
from typing import Final

import numpy as np
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from raindesk.config.schema import RANDOMIZE_RANGES
from raindesk.config.store import SettingsStore
from raindesk.core.logging_setup import configure_logging
from raindesk.core.single_instance import SingleInstanceGuard
from raindesk.i18n.translator import Translator
from raindesk.ui.overlay_manager import OverlayManager
from raindesk.ui.settings_window import SettingsWindow
from raindesk.ui.theme import ThemeManager
from raindesk.ui.tray import TrayController

_LOG = logging.getLogger(__name__)

_RANDOM_DECIMALS: Final[int] = 2  # منزلتان عشريتان للقيم العشوائية (تتطابق مع خطوة المنزلقات)
# مفاتيح تُعيد بناء النوافذ، ومفاتيح تحدّث خيارات حية (الرسم يعالجه المدير بنفسه).
_REBUILD_KEYS: Final[frozenset[str]] = frozenset(
    {"screens_mode", "selected_screens", "cover_taskbar"}
)
_OPTION_KEYS: Final[frozenset[str]] = frozenset({"topmost_watchdog", "exclude_from_capture"})


class AppController(QObject):
    """وسيط التطبيق؛ لا يحمل منطقًا رياضيًا ولا رسمًا."""

    def __init__(
        self,
        store: SettingsStore,
        translator: Translator,
        theme: ThemeManager,
        manager: OverlayManager,
        watcher: object | None,
        tray: TrayController,
        guard: SingleInstanceGuard,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._translator = translator
        self._theme = theme
        self._manager = manager
        self._watcher = watcher  # يُربط لاحقًا (SystemWatcher)
        self._tray = tray
        self._guard = guard
        self._settings_window: SettingsWindow | None = None
        self._tray_available = True
        self._shut_down = False

    # ------------------------------------------------------------------ البدء
    def start(self, minimized: bool = False) -> None:
        """يوصّل الإشارات ويُظهر الأيقونة ويقرّر هل تُفتح الإعدادات عند البدء.

        Args:
            minimized: True يعني بدءًا مخفيًا (العلم --minimized) فلا تُفتح الإعدادات.
        أول تشغيل: تُفتح الإعدادات ويظهر إشعار يوضح أن التطبيق يبقى في الشريط.
        """
        self._tray_available = self._tray.is_available()
        self._tray.open_settings_requested.connect(self.show_settings)
        self._tray.toggle_enabled_requested.connect(self.toggle_enabled)
        self._tray.randomize_requested.connect(self.randomize)
        self._tray.preset_requested.connect(self.apply_preset)
        self._tray.quit_requested.connect(self.quit_app)
        self._store.changed.connect(self._on_setting_changed)
        self._translator.language_changed.connect(self._on_language_changed)
        self._guard.activation_requested.connect(self.show_settings)

        enabled = bool(self._store.get("enabled"))
        self._manager.set_pause_reason("user_disabled", not enabled)
        self._tray.set_enabled_state(enabled)
        if self._tray_available:
            self._tray.show()
        else:
            _LOG.warning("system tray is not available")

        first_run = not bool(self._store.get("first_run_completed"))
        open_now = first_run or not self._tray_available or (
            not minimized and not bool(self._store.get("start_hidden_in_tray"))
        )
        if open_now:
            self.show_settings()
        if first_run:
            self._tray.notify(
                self._translator.tr("msg.first_run_title"),
                self._translator.tr("msg.first_run_body"),
            )
            self._store.set("first_run_completed", True)

    # ------------------------------------------------------------------ الإجراءات
    def show_settings(self) -> None:
        """ينشئ نافذة الإعدادات عند أول طلب ثم يُظهرها ويرفعها."""
        if self._settings_window is None:
            window = SettingsWindow(self._store, self._translator, self._theme)
            window.setWindowIcon(self._tray.app_icon)
            window.randomize_requested.connect(self.randomize)
            window.reset_requested.connect(self._reset)
            window.set_quit_on_close(not self._tray_available)
            self._settings_window = window
            if not self._tray_available:
                window.show_notice(self._translator.tr("msg.tray_unavailable"))
        self._settings_window.show_and_raise()

    def toggle_enabled(self) -> None:
        self._store.set("enabled", not bool(self._store.get("enabled")))

    def randomize(self) -> None:
        """يسحب قيمًا منتظمة لكل مفتاح في RANDOMIZE_RANGES ويكتبها دفعة واحدة (preset=custom).

        ParamSmoother يتكفل بالانتقال الناعم إلى القيم الجديدة.
        """
        rng = np.random.default_rng()  # عشوائية المستخدم لا ترتبط ببذرة المحاكاة
        values: dict[str, object] = {
            key: round(float(rng.uniform(low, high)), _RANDOM_DECIMALS)
            for key, (low, high) in RANDOMIZE_RANGES.items()
        }
        values["preset"] = "custom"
        self._store.update(values)

    def apply_preset(self, name: str) -> None:
        self._store.apply_preset(name)

    def _reset(self) -> None:
        self._store.reset_to_defaults()

    def quit_app(self) -> None:
        """خروج نظيف؛ الحفظ وإغلاق النوافذ يتمان في aboutToQuit."""
        _LOG.info("quit requested")
        self.shutdown()
        QApplication.quit()

    def shutdown(self) -> None:
        """يحفظ هندسة النافذة ويخفي الأيقونة (كي لا تبقى شبحية)؛ آمن عند التكرار."""
        if self._shut_down:
            return
        self._shut_down = True
        if self._settings_window is not None:
            self._settings_window.save_geometry()
        self._tray.hide()

    # ------------------------------------------------------------------ التوجيه
    def _on_language_changed(self, _code: str) -> None:
        self._tray.retranslate()  # النافذة تعيد ترجمة نفسها بنفسها

    def _on_setting_changed(self, key: str) -> None:
        if key == "language":
            self._translator.set_language(str(self._store.get("language")))
        elif key == "theme":
            self._theme.apply(str(self._store.get("theme")))
        elif key == "enabled":
            enabled = bool(self._store.get("enabled"))
            self._manager.set_pause_reason("user_disabled", not enabled)
            self._tray.set_enabled_state(enabled)
        elif key == "log_level":
            configure_logging(str(self._store.get("log_level")))
        elif key in _REBUILD_KEYS:
            self._manager.rebuild()
        elif key in _OPTION_KEYS:
            self._manager.refresh_options()
        elif key == "launch_at_login":
            _LOG.debug("launch_at_login saved; the registry entry is applied in stage M8")