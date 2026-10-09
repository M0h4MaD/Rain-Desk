"""raindesk/ui/overlay_manager.py

الغرض: يدير نوافذ overlay (واحدة لكل شاشة مختارة) ويقود المحاكاة المشتركة بينها.
المسؤوليات: اختيار الشاشات وإعادة البناء مع إعادة استخدام النوافذ، وأسباب الإيقاف، وحارس
    التثبيت، وتنعيم المعاملات (ParamSmoother)، والعصف المشترك، وآلة الطقس التلقائي، وبرق واحد
    مشترك بين الشاشات، والجودة التكيفية، وتفويض الشخصية Drip إلى MascotHost، وتمرير tick إلى
    كل النوافذ.
الاعتماديات: config.store وengine (math_utils وparams وweather_fsm وadaptive_quality)
    وui.frame_clock وui.overlay_window وui.mascot_host وplatform_win.win32_api.
النمط التصميمي: Mediator بين FrameClock والنوافذ، مع Debounce لأحداث توصيل الشاشات.
ملاحظات: العصف والمعاملات والطقس والبرق مشتركة بين الشاشات كي تتحرك الرياح بتناسق عبر الأجهزة.
    الشخصية تتجمد مع الإيقاف لأن الساعة تقف، ولا كلفة لها إن عُطّلت (MascotHost.step).
    الإيقاف = hide() + إيقاف الساعة (لا نُتلف النوافذ لتجنّب الوميض). البرق يُجبَر على الإيقاف
    إن عطّل المستخدم رسوم Windows المتحركة (حساسية الضوء). الطقس التلقائي يتقدم على الإعدادات
    اليدوية للقيم السبع المقابلة لمفاتيح PRESETS ويُنعَّم عبر ParamSmoother.
مثال: manager = OverlayManager(store, clock); manager.rebuild()
"""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Mapping
from typing import Final

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QScreen

from raindesk.config.store import SettingsStore
from raindesk.core.constants import TOPMOST_WATCHDOG_INTERVAL_MS
from raindesk.engine.adaptive_quality import AdaptiveQuality
from raindesk.engine.math_utils import gust_signal
from raindesk.engine.params import ParamSmoother, params_from_settings
from raindesk.engine.weather_fsm import LightningModel, WeatherStateMachine
from raindesk.platform_win import win32_api
from raindesk.ui.frame_clock import FrameClock
from raindesk.ui.mascot_host import MASCOT_KEYS, MascotHost
from raindesk.ui.overlay_window import OverlayWindow, compute_screen_key

_LOG = logging.getLogger(__name__)

_HOTPLUG_DEBOUNCE_MS: Final[int] = 150  # ms: دمج أحداث توصيل/فصل الشاشات المتلاحقة
_MIN_GUST_PERIOD_S: Final[float] = 0.1  # ثانية: حماية القسمة (المخطط يضمن >= 2)
_GUST_PHASE_COUNT: Final[int] = 3  # عدد مكوّنات العصف (طور عشوائي لكل مكوّن)
_DEFAULT_FPS: Final[int] = 30
_KNOWN_REASONS: Final[frozenset[str]] = frozenset(
    {"user_disabled", "fullscreen", "session_inactive", "battery_saver"}
)
# مفاتيح تتطلب من النوافذ إعادة قراءة خيارات الرسم (يعالجها المدير بنفسه).
_RENDER_KEYS: Final[frozenset[str]] = frozenset(
    {
        "antialiasing",
        "quality",
        "splash_zone",
        "edge_streams_enabled",
        "edge_streams_count",
        "edge_streams_opacity",
        "mood_enabled",
        "mood_color",
        "mood_opacity",
        "debug_hud",
    }
)
# مفاتيح تعيد ضبط الطقس التلقائي والبرق والجودة التكيفية.
_EFFECT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "auto_weather",
        "auto_weather_variability",
        "lightning_enabled",
        "lightning_frequency",
        "adaptive_quality",
        "fps_cap",
    }
)


def _as_float(value: object, default: float = 0.0) -> float:
    """قيمة إعداد عددية أو الافتراضي (bool ليس رقمًا هنا)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


class OverlayManager(QObject):
    """مالك نوافذ الشاشات؛ الإيقاف المؤقت يوقف الساعة ويخفي النوافذ (استهلاك معالج نحو 0)."""

    simulation_updated = Signal(
        object, float
    )  # (EngineParams المنعّمة، العصف) بعد كل tick
    paused_changed = Signal(
        bool
    )  # حالة "متوقف/يعمل" بعد أي تغيّر (يستهلكها AppController)

    lightning_struck = Signal(float)  # شدة وميض برق جديد (لإطلاق الرعد المناسب)

    def __init__(
        self, store: SettingsStore, clock: FrameClock, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._clock = clock
        self._windows: list[OverlayWindow] = []
        self._reasons: set[str] = set()
        seed = store.get("rng_seed")
        seed_value = (
            seed if isinstance(seed, int) and not isinstance(seed, bool) else -1
        )
        # SeedSequence يفرّع تيارات عشوائية مستقلة لكل نافذة (وحتمية إذا ثُبّتت البذرة).
        self._seed_sequence = np.random.SeedSequence(
            seed_value if seed_value >= 0 else None
        )
        phases = (
            2.0
            * math.pi
            * np.random.default_rng(self._seed_sequence.spawn(1)[0]).random(
                _GUST_PHASE_COUNT
            )
        )
        self._gust_phases: tuple[float, float, float] = (
            float(phases[0]),
            float(phases[1]),
            float(phases[2]),
        )
        # عدد دورات العصف المنقضية: نتكامل dt / T بدل t / T كي لا يقفز الطور عند تغيير الدورة T.
        self._gust_cycles = 0.0
        self._snapshot = store.snapshot()  # نسخة مخبأة تُجدَّد عند تغيّر الإعدادات فقط
        self._smoother = ParamSmoother(params_from_settings(self._snapshot))
        self._target_dirty = False
        self._weather = WeatherStateMachine(random.Random(self._derive_seed()))
        self._lightning = LightningModel(random.Random(self._derive_seed()))
        self._adaptive = AdaptiveQuality()
        self._configure_effects()
        # آخر استهلاك للبذرة كي لا تتغير تيارات الطقس والبرق عن النسخ السابقة.
        self._mascot = MascotHost(store, random.Random(self._derive_seed()))

        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(_HOTPLUG_DEBOUNCE_MS)
        self._rebuild_timer.timeout.connect(self.rebuild)
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(TOPMOST_WATCHDOG_INTERVAL_MS)
        self._watchdog.timeout.connect(self._on_watchdog)

        clock.tick.connect(self._on_tick)
        clock.stall_detected.connect(self._on_stall)
        store.changed.connect(self._on_setting_changed)
        store.reloaded.connect(self._on_store_reloaded)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.screenAdded.connect(self._schedule_rebuild)
            app.screenRemoved.connect(self._schedule_rebuild)
            app.primaryScreenChanged.connect(self._schedule_rebuild)

    # ------------------------------------------------------------------ الحالة
    @property
    def paused(self) -> bool:
        """True إذا وُجد سبب إيقاف واحد على الأقل."""
        return bool(self._reasons)

    def set_pause_reason(self, reason: str, active: bool) -> None:
        """يضيف سبب إيقاف أو يزيله؛ أي تغيّر في حالة "متوقف/يعمل" يُطبَّق فورًا."""
        if reason not in _KNOWN_REASONS:
            _LOG.warning("unknown pause reason: %r", reason)
            return
        was_paused = self.paused
        if active:
            self._reasons.add(reason)
        else:
            self._reasons.discard(reason)
        if self.paused != was_paused:
            _LOG.info(
                "overlay %s (reasons: %s)",
                "paused" if self.paused else "resumed",
                sorted(self._reasons),
            )
            self._sync_run_state()
            self.paused_changed.emit(self.paused)

    # ------------------------------------------------------------------ البناء
    def _derive_seed(self) -> int:
        """بذرة عدد صحيح لـ random.Random من SeedSequence (حتمية إذا ثُبّتت rng_seed)."""
        return int(self._seed_sequence.spawn(1)[0].generate_state(1)[0])

    def _selected_screens(self) -> list[QScreen]:
        """الشاشات المطلوبة حسب screens_mode؛ إن لم يطابق الاختيار شيئًا نرجع للشاشة الأساسية."""
        primary = QGuiApplication.primaryScreen()
        fallback = [primary] if primary is not None else []
        mode = str(self._store.get("screens_mode"))
        if mode == "primary":
            return fallback
        screens = list(QGuiApplication.screens())
        if mode == "selected":
            raw = self._store.get("selected_screens")
            keys = (
                {item for item in raw if isinstance(item, str)}
                if isinstance(raw, list)
                else set()
            )
            chosen = [s for s in screens if compute_screen_key(s) in keys]
            if not chosen:
                _LOG.info(
                    "no selected screen is connected; falling back to the primary one"
                )
            return chosen or fallback
        return screens

    def _new_rng(self) -> np.random.Generator:
        return np.random.default_rng(self._seed_sequence.spawn(1)[0])

    def _schedule_rebuild(self, *_args: object) -> None:
        """يؤجّل إعادة البناء قليلًا فتُدمج عدة أحداث شاشات في إعادة بناء واحدة."""
        self._rebuild_timer.start()

    def rebuild(self) -> None:
        """يوفّق النوافذ مع الشاشات المطلوبة: يعيد استخدام المطابق ويُنشئ الناقص ويزيل الزائد."""
        existing = {window.screen_key: window for window in self._windows}
        used: set[int] = set()
        result: list[OverlayWindow] = []
        for screen in self._selected_screens():
            window = existing.get(compute_screen_key(screen))
            if (
                window is not None
                and window.qscreen is screen
                and id(window) not in used
            ):
                window.apply_geometry()  # قد تغيّر cover_taskbar
            else:
                window = OverlayWindow(screen, self._store, self._new_rng())
            used.add(id(window))
            result.append(window)
        for window in self._windows:
            if id(window) not in used:
                window.shutdown()
        self._windows = result
        _LOG.info("overlay windows: %d", len(result))
        self._mascot.sync(self._windows)
        self._sync_run_state()

    def _sync_run_state(self) -> None:
        """يوفّق العرض مع الحالة: متوقف = إخفاء وإيقاف الساعة، وإلا إظهار وتشغيلها."""
        if self.paused or not self._windows:
            self._clock.stop()
            self._watchdog.stop()
            for window in self._windows:
                window.hide()
            return
        for window in self._windows:
            window.show()  # لا أثر إن كانت ظاهرة أصلًا
            window.reassert_topmost()
        self.refresh_options()
        if not self._clock.is_running:
            self._adaptive.reset()  # بعد إيقاف مؤقت تُقدَّر الأحمال من جديد (لا متوسطات قديمة)
        self._clock.start()

    def refresh_options(self) -> None:
        """يعيد قراءة الخيارات الحية: الرسم والحارس واستثناء اللقطات وحالة الطقس والبرق."""
        for window in self._windows:
            window.refresh_render_options()
        self._configure_effects()  # idempotent: لا يعيد ضبط الطقس أو البرق إلا عند تغيّر الحالة
        if self.paused or not self._windows:
            self._watchdog.stop()
            return
        for window in self._windows:
            window.refresh_native_options()
        if bool(self._store.get("topmost_watchdog")):
            if not self._watchdog.isActive():
                self._watchdog.start()
        else:
            self._watchdog.stop()

    # ------------------------------------------------------------------ الطقس والبرق والجودة
    def _configure_effects(self) -> None:
        """يضبط الطقس والبرق والجودة التكيفية من الإعدادات.

        البرق يُجبَر على الإيقاف إن عُطّلت رسوم Windows. الدالة idempotent: لا تعيد ضبط شيء
        إلا عند تغيّر الحالة الفعلية.
        """
        get = self._store.get
        self._adaptive.configure(
            bool(get("adaptive_quality")),
            round(_as_float(get("fps_cap"), _DEFAULT_FPS)),
        )
        self._weather.set_variability(_as_float(get("auto_weather_variability"), 0.5))
        self._weather.set_enabled(bool(get("auto_weather")))
        animations_ok = win32_api.client_animations_enabled()
        self._lightning.configure(
            bool(get("lightning_enabled")) and animations_ok,
            _as_float(get("lightning_frequency"), 0.3),
        )

    def _weather_overrides(self) -> Mapping[str, float] | None:
        """قيم الطقس التلقائي إن كان مفعّلًا (تتقدم على الإعدادات)، وإلا لا شيء."""
        return self._weather.blended_values() if self._weather.enabled else None

    # ------------------------------------------------------------------ المحاكاة المشتركة
    def _apply_target(self) -> None:
        """يبني الهدف من النسخة المخبأة وقيم الطقس (إن وُجدت) ويسلّمه للمنعّم."""
        self._smoother.set_target(
            params_from_settings(self._snapshot, self._weather_overrides())
        )

    def _refresh_target(self, *, snap: bool = False) -> None:
        """يجدّد النسخة المخبأة ويعيد بناء الهدف؛ snap=True يقفز إليه دون تنعيم."""
        self._snapshot = self._store.snapshot()
        self._apply_target()
        if snap:
            self._smoother.snap()
        self._target_dirty = False

    def _on_setting_changed(self, key: str) -> None:
        self._target_dirty = True  # يُعاد بناء الهدف مرة واحدة في أول tick تالٍ
        if key in _RENDER_KEYS:
            self.refresh_options()
        if key in _EFFECT_KEYS:
            self._configure_effects()
        if key in MASCOT_KEYS:
            self._mascot.sync(self._windows)

    def _on_store_reloaded(self) -> None:
        """بعد load() أو استبدال كامل: نقفز للقيم الجديدة بدل تنعيمها من القديمة."""
        self._refresh_target(snap=True)
        self._configure_effects()
        self._mascot.sync(self._windows)

    def _on_tick(self, dt: float) -> None:
        if self._target_dirty:
            self._refresh_target()
        self._weather.step(dt)
        if self._weather.enabled:
            self._apply_target()  # قيم الطقس تتغير كل إطار (ينعّمها ParamSmoother)

        strikes_before = self._lightning.event_count
        self._lightning.step(dt)
        if self._lightning.event_count != strikes_before:
            self.lightning_struck.emit(self._lightning.alpha)  # alpha عند بداية الحدث = ذروته

        params = self._smoother.step(dt)
        period = max(params.gust_period_s, _MIN_GUST_PERIOD_S)
        self._gust_cycles += dt / period
        # t = cycles * T يعطي t / T = cycles، فيبقى الطور متصلًا حتى لو تغيّرت الدورة T.
        gust = gust_signal(self._gust_cycles * period, period, self._gust_phases)
        flash = self._lightning.alpha
        self._mascot.step(
            dt, params.wind_angle_deg, params.intensity, flash
        )  # لا كلفة إن عُطّلت
        cost_ms = 0.0
        for window in self._windows:
            window.advance(dt, params, gust)
            window.set_flash_alpha(flash)
            cost_ms += window.last_advance_ms + window.last_paint_ms
        # الكلفة = مجموع محاكاة ورسم كل الشاشات (تُنفَّذ كلها تباعًا على خيط الواجهة).
        self._adaptive.record(self._clock.last_interval_ms, cost_ms)
        scale, fps, interval = (
            self._adaptive.scale,
            self._adaptive.fps,
            self._adaptive.interval_ema,
        )
        for window in self._windows:
            window.set_adaptive_scale(scale)
            window.set_hud_metrics(fps, interval)
        self.simulation_updated.emit(params, gust)

    # ------------------------------------------------------------------ الأحداث
    def _reassert_all(self) -> None:
        for window in self._windows:
            window.reassert_topmost()

    def _on_watchdog(self) -> None:
        if not self.paused:
            self._reassert_all()

    def _on_stall(self, raw_dt: float) -> None:
        """توقف طويل (غالبًا استئناف من السكون): نعيد تثبيت النوافذ دون تسريع المحاكاة."""
        _LOG.info("frame stall of %.1f s detected; re-asserting topmost", raw_dt)
        self._reassert_all()

    # ------------------------------------------------------------------ الإنهاء
    def shutdown(self) -> None:
        """يوقف الساعة والمؤقّتات ويفصل الإشارات ويغلق كل النوافذ؛ آمن عند التكرار."""
        self._rebuild_timer.stop()
        self._watchdog.stop()
        self._clock.stop()
        self._mascot.shutdown()
        for signal, slot in (
            (self._clock.tick, self._on_tick),
            (self._clock.stall_detected, self._on_stall),
            (self._store.changed, self._on_setting_changed),
            (self._store.reloaded, self._on_store_reloaded),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            for signal in (
                app.screenAdded,
                app.screenRemoved,
                app.primaryScreenChanged,
            ):
                try:
                    signal.disconnect(self._schedule_rebuild)
                except (RuntimeError, TypeError):
                    pass
        for window in self._windows:
            window.shutdown()
        self._windows = []
