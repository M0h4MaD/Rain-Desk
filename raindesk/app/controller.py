"""raindesk/app/controller.py

الغرض: AppController: الوسيط (Mediator) الذي يوجّه أحداث الشريط والإعدادات والنسخة الواحدة.
المسؤوليات: بدء الواجهة (أول تشغيل، بدء مخفيًا)، وإنشاء نافذة الإعدادات كسولًا، وتوجيه
    تغيّر الإعدادات إلى المترجم والسمة والمدير، والعشوائي والإعدادات المسبقة والخروج.
الاعتماديات: كل طبقات الواجهة والإعدادات (الجذر app هو الوحيد المسموح له بذلك).
النمط التصميمي: Mediator. كل طرف يعرف المتحكم فقط لا بعضه بعضًا.
ملاحظات: SystemWatcher يوقف المطر عند ملء الشاشة والجلسة المقفلة وموفّر البطارية، والتشغيل
    التلقائي يُطابَق مع السجل عند البدء، والمتحكم يملك مشغّل الصوت ويغذّيه بمعاملات المحاكاة
    كل إطار ويوقفه مع المطر. سرعة الإطارات (fps_cap) تتولاها bootstrap لأنها تملك FrameClock.
مثال: controller = AppController(store, translator, theme, manager, watcher, tray, guard)
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
from raindesk.engine.math_utils import clamp
from raindesk.engine.params import EngineParams
from raindesk.i18n.translator import Translator
from raindesk.platform_win import autostart
from raindesk.platform_win.system_watcher import (
    REASON_BATTERY,
    REASON_FULLSCREEN,
    REASON_SESSION,
    SystemWatcher,
)
from raindesk.ui.audio.audio_player import RainAudioPlayer
from raindesk.ui.overlay_manager import OverlayManager
from raindesk.ui.settings_window import SettingsWindow
from raindesk.ui.theme import ThemeManager
from raindesk.ui.tray import TrayController

_LOG = logging.getLogger(__name__)

_RANDOM_DECIMALS: Final[int] = (
    2  # منزلتان عشريتان للقيم العشوائية (تتطابق مع خطوة المنزلقات)
)
# مفاتيح تُعيد بناء النوافذ، ومفاتيح تحدّث خيارات حية (الرسم يعالجه المدير بنفسه).
_REBUILD_KEYS: Final[frozenset[str]] = frozenset(
    {"screens_mode", "selected_screens", "cover_taskbar"}
)
_OPTION_KEYS: Final[frozenset[str]] = frozenset(
    {"topmost_watchdog", "exclude_from_capture"}
)
_WATCHER_KEYS: Final[frozenset[str]] = frozenset(
    {"pause_on_fullscreen", "pause_on_battery_saver"}
)
_WATCHER_REASONS: Final[tuple[str, ...]] = (
    REASON_FULLSCREEN,
    REASON_SESSION,
    REASON_BATTERY,
)
_SOUND_KEYS: Final[frozenset[str]] = frozenset(
     {"sound_enabled", "sound_volume", "sound_follows_intensity", "sound_wind", "sound_thunder"}
)
_FIXED_SOUND_INTENSITY: Final[float] = 0.5  # شدة الصوت عند إيقاف "يتبع شدة المطر"
_WIND_ANGLE_REFERENCE_DEG: Final[float] = 60.0  # أقصى زاوية رياح في الواجهة
_WIND_ANGLE_WEIGHT: Final[float] = 0.4  # وزن زاوية الرياح في كمية صوت الرياح
_WIND_GUST_WEIGHT: Final[float] = 0.6  # وزن الهبّات (مجموع الوزنين 1)


class AppController(QObject):
    """وسيط التطبيق؛ لا يحمل منطقًا رياضيًا ولا رسمًا."""

    def __init__(
        self,
        store: SettingsStore,
        translator: Translator,
        theme: ThemeManager,
        manager: OverlayManager,
        watcher: SystemWatcher | None,
        tray: TrayController,
        guard: SingleInstanceGuard,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._translator = translator
        self._theme = theme
        self._manager = manager
        self._watcher = watcher
        self._tray = tray
        self._guard = guard
        self._settings_window: SettingsWindow | None = None
        self._audio = RainAudioPlayer(self)
        self._sound_enabled = False
        self._sound_follows_intensity = True
        self._sound_wind = True
        self._sound_thunder = True
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
        self._tray.toggle_sound_requested.connect(self.toggle_sound)
        self._store.changed.connect(self._on_setting_changed)
        self._translator.language_changed.connect(self._on_language_changed)
        self._guard.activation_requested.connect(self.show_settings)
        self._manager.simulation_updated.connect(self._on_simulation_updated)
        self._manager.paused_changed.connect(self._on_paused_changed)
        self._manager.lightning_struck.connect(self._on_lightning_struck)
        self._audio.availability_changed.connect(self._on_audio_availability)
        self._apply_sound_settings()
        self._reconcile_autostart()
        if self._watcher is not None:
            self._watcher.reasons_changed.connect(self._on_watcher_reasons)
            self._apply_watcher_options()
            self._watcher.start()

        enabled = bool(self._store.get("enabled"))
        self._manager.set_pause_reason("user_disabled", not enabled)
        self._tray.set_enabled_state(enabled)
        if self._tray_available:
            self._tray.show()
        else:
            _LOG.warning("system tray is not available")

        first_run = not bool(self._store.get("first_run_completed"))
        open_now = (
            first_run
            or not self._tray_available
            or (not minimized and not bool(self._store.get("start_hidden_in_tray")))
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
            window.set_sound_available(self._audio.is_available)
            self._settings_window = window
            if not self._tray_available:
                window.show_notice(self._translator.tr("msg.tray_unavailable"))
        self._settings_window.show_and_raise()

    def toggle_enabled(self) -> None:
        self._store.set("enabled", not bool(self._store.get("enabled")))

    def toggle_sound(self) -> None:
        self._store.set("sound_enabled", not bool(self._store.get("sound_enabled")))

    def randomize(self) -> None:
        """يسحب قيمًا منتظمة لكل مفتاح في RANDOMIZE_RANGES ويكتبها دفعة واحدة (preset=custom).

        ParamSmoother يتكفل بالانتقال الناعم إلى القيم الجديدة (نحو ثانية). يوقف أيضًا الطقس
        التلقائي لأن قيمه كانت ستتقدم على القيم العشوائية فلا يظهر لزر "عشوائي" أثر.
        """
        rng = np.random.default_rng()  # عشوائية المستخدم لا ترتبط ببذرة المحاكاة
        values: dict[str, object] = {
            key: round(float(rng.uniform(low, high)), _RANDOM_DECIMALS)
            for key, (low, high) in RANDOMIZE_RANGES.items()
        }
        values["preset"] = "custom"
        values["auto_weather"] = (
            False  # اختيار المستخدم اليدوي ينهي الطقس التلقائي (وإلا غلبه)
        )
        self._store.update(values)

    def apply_preset(self, name: str) -> None:
        """يطبّق إعدادًا مسبقًا؛ إن كان الطقس التلقائي مفعّلًا يُوقَف أولًا كي يظهر أثر الاختيار."""
        if bool(self._store.get("auto_weather")):
            self._store.set("auto_weather", False)
        self._store.apply_preset(name)

    def _reset(self) -> None:
        self._store.reset_to_defaults()

    def quit_app(self) -> None:
        """خروج نظيف؛ الحفظ وإغلاق النوافذ يتمان في aboutToQuit."""
        _LOG.info("quit requested")
        self.shutdown()
        QApplication.quit()

    def shutdown(self) -> None:
        """يوقف المراقبة ويحفظ هندسة النافذة ويخفي الأيقونة (كي لا تبقى شبحية)؛ آمن عند التكرار."""
        if self._shut_down:
            return
        self._shut_down = True
        self._audio.shutdown()
        if self._watcher is not None:
            self._watcher.stop()
        if self._settings_window is not None:
            self._settings_window.save_geometry()
        self._tray.hide()

    # ------------------------------------------------------------------ الصوت
    def _apply_sound_settings(self) -> None:
        """يقرأ إعدادات الصوت ويطبّقها على المشغّل والشريط (تُستدعى عند البدء وعند أي تغيّر)."""
        get = self._store.get
        self._sound_enabled = bool(get("sound_enabled"))
        self._sound_follows_intensity = bool(get("sound_follows_intensity"))
        self._sound_wind = bool(get("sound_wind"))
        self._sound_thunder = bool(get("sound_thunder"))
        volume = get("sound_volume")
        self._audio.set_volume(
            float(volume) if isinstance(volume, (int, float)) else 0.0
        )
        self._audio.set_active(not self._manager.paused)
        self._audio.set_enabled(self._sound_enabled)
        self._tray.set_sound_state(self._sound_enabled)
        self._tray.set_sound_available(self._audio.is_available)

    def _on_simulation_updated(self, params: object, gust: float) -> None:
        """يغذّي الصوت بمعاملات الإطار: الشدة، وكمية الرياح من زاويتها وهبّاتها."""
        if not self._sound_enabled or not isinstance(params, EngineParams):
            return
        intensity = (
            params.intensity
            if self._sound_follows_intensity
            else _FIXED_SOUND_INTENSITY
        )
        wind_amount = clamp(
            _WIND_ANGLE_WEIGHT * abs(params.wind_angle_deg) / _WIND_ANGLE_REFERENCE_DEG
            + _WIND_GUST_WEIGHT * params.wind_gusts,
            0.0,
            1.0,
        )
        self._audio.update_params(intensity, wind_amount, gust, self._sound_wind)

    def _on_lightning_struck(self, flash_peak: float) -> None:
        """كل وميض برق يتبعه رعد بعد تأخير يناسب بعده، إن كان الصوت والرعد مفعّلين."""
        if self._sound_enabled and self._sound_thunder:
            self._audio.trigger_thunder(flash_peak)

    def _on_paused_changed(self, paused: bool) -> None:
        self._audio.set_active(not paused)

    def _on_audio_availability(self, available: bool) -> None:
        self._tray.set_sound_available(available)
        if self._settings_window is not None:
            self._settings_window.set_sound_available(available)

    # ------------------------------------------------------------------ النظام والتشغيل التلقائي
    def _apply_watcher_options(self) -> None:
        if self._watcher is not None:
            self._watcher.set_options(
                bool(self._store.get("pause_on_fullscreen")),
                bool(self._store.get("pause_on_battery_saver")),
            )

    def _on_watcher_reasons(self, reasons: object) -> None:
        """يحوّل مجموعة الأسباب الواردة من المراقب إلى أسباب إيقاف في المدير."""
        active = reasons if isinstance(reasons, frozenset) else frozenset()
        for reason in _WATCHER_REASONS:
            self._manager.set_pause_reason(reason, reason in active)

    def _reconcile_autostart(self) -> None:
        """السجل هو مصدر الحقيقة: يطابق مفتاح launch_at_login مع وجود إدخال Run فعلًا."""
        actual = autostart.is_enabled()
        if actual != bool(self._store.get("launch_at_login")):
            self._store.set("launch_at_login", actual)

    def _apply_launch_at_login(self) -> None:
        """يكتب إدخال التشغيل التلقائي أو يحذفه؛ عند الفشل يعود المفتاح إلى حالة السجل الفعلية."""
        wanted = bool(self._store.get("launch_at_login"))
        if wanted == autostart.is_enabled():
            return
        if not autostart.set_enabled(wanted):
            _LOG.warning("could not change the startup entry; reverting the setting")
            self._store.set("launch_at_login", autostart.is_enabled())

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
            self._apply_launch_at_login()
        elif key in _SOUND_KEYS:
            self._apply_sound_settings()
        elif key in _WATCHER_KEYS:
            self._apply_watcher_options()
