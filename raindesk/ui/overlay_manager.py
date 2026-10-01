"""raindesk/ui/overlay_manager.py

الغرض: يدير نوافذ overlay (واحدة لكل شاشة مختارة) ويقود المحاكاة المشتركة بينها.
المسؤوليات: اختيار الشاشات وإعادة البناء مع إعادة استخدام النوافذ، وأسباب الإيقاف، وحارس
    التثبيت، وتنعيم المعاملات (ParamSmoother) والعصف المشترك، وتمرير tick إلى كل النوافذ.
الاعتماديات: config.store وengine (math_utils وparams) وui.frame_clock وui.overlay_window.
النمط التصميمي: Mediator بين FrameClock والنوافذ، مع Debounce لأحداث توصيل الشاشات.
ملاحظات: العصف والمعاملات المنعّمة مشتركة بين الشاشات كي تتحرك الرياح بتناسق عبر الأجهزة.
    الإيقاف = hide() + إيقاف الساعة (لا نُتلف النوافذ لتجنّب الوميض). تُضاف آلة الطقس لاحقًا
    عبر _weather_overrides().
مثال: manager = OverlayManager(store, clock); manager.rebuild()
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import Final

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QScreen

from raindesk.config.store import SettingsStore
from raindesk.core.constants import TOPMOST_WATCHDOG_INTERVAL_MS
from raindesk.engine.math_utils import gust_signal
from raindesk.engine.params import ParamSmoother, params_from_settings
from raindesk.ui.frame_clock import FrameClock
from raindesk.ui.overlay_window import OverlayWindow, compute_screen_key

_LOG = logging.getLogger(__name__)

_HOTPLUG_DEBOUNCE_MS: Final[int] = 150  # ms: دمج أحداث توصيل/فصل الشاشات المتلاحقة
_MIN_GUST_PERIOD_S: Final[float] = 0.1  # ثانية: حماية القسمة (المخطط يضمن >= 2)
_GUST_PHASE_COUNT: Final[int] = 3  # عدد مكوّنات العصف (طور عشوائي لكل مكوّن)
_KNOWN_REASONS: Final[frozenset[str]] = frozenset(
    {"user_disabled", "fullscreen", "session_inactive", "battery_saver"}
)
# مفاتيح تتطلب من النوافذ إعادة قراءة خيارات الرسم (يعالجها المدير بنفسه).
_RENDER_KEYS: Final[frozenset[str]] = frozenset(
    {"antialiasing", "quality", "splash_zone"}
)


class OverlayManager(QObject):
    """مالك نوافذ الشاشات؛ الإيقاف المؤقت يوقف الساعة ويخفي النوافذ (استهلاك معالج نحو 0)."""

    simulation_updated = Signal(
        object, float
    )  # (EngineParams المنعّمة، العصف) بعد كل tick

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
        self._smoother = ParamSmoother(params_from_settings(store.snapshot()))
        self._target_dirty = False

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

    # ------------------------------------------------------------------ البناء
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
        self._clock.start()

    def refresh_options(self) -> None:
        """يعيد قراءة الخيارات الحية: خيارات الرسم وحارس التثبيت واستثناء اللقطات."""
        for window in self._windows:
            window.refresh_render_options()
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

    # ------------------------------------------------------------------ المحاكاة المشتركة
    def _weather_overrides(self) -> Mapping[str, float] | None:
        """قيم تتقدم على الإعدادات من آلة الطقس؛ لا شيء حتى تُضاف آلة الطقس (مرحلة لاحقة)."""
        return None

    def _refresh_target(self, *, snap: bool = False) -> None:
        """يعيد بناء الهدف من الإعدادات الحالية؛ snap=True يقفز إليه دون تنعيم."""
        self._smoother.set_target(
            params_from_settings(self._store.snapshot(), self._weather_overrides())
        )
        if snap:
            self._smoother.snap()
        self._target_dirty = False

    def _on_setting_changed(self, key: str) -> None:
        self._target_dirty = True  # يُعاد بناء الهدف مرة واحدة في أول tick تالٍ
        if key in _RENDER_KEYS:
            self.refresh_options()

    def _on_store_reloaded(self) -> None:
        """بعد load() أو استبدال كامل: نقفز للقيم الجديدة بدل تنعيمها من القديمة."""
        self._refresh_target(snap=True)

    def _on_tick(self, dt: float) -> None:
        if self._target_dirty:
            self._refresh_target()
        params = self._smoother.step(dt)
        period = max(params.gust_period_s, _MIN_GUST_PERIOD_S)
        self._gust_cycles += dt / period
        # t = cycles * T يعطي t / T = cycles، فيبقى الطور متصلًا حتى لو تغيّرت الدورة T.
        gust = gust_signal(self._gust_cycles * period, period, self._gust_phases)
        for window in self._windows:
            window.advance(dt, params, gust)
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
