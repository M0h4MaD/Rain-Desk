"""raindesk/ui/overlay_window.py

الغرض: نافذة شفافة بلا إطار تغطي شاشة واحدة، ترسم المطر ومؤثراته، وتمرّر النقرات، ولا تظهر
    في شريط المهام.
المسؤوليات: أعلام النافذة، والهندسة حسب cover_taskbar، والتثبيت فوق الأخرى، وحقل المطر
    (RainField) والرذاذ (SplashSystem) وجداول الحواف (EdgeStreams)، وترتيب الرسم: تظليل
    الأجواء ثم الجداول ثم المطر ثم الرذاذ ثم وميض البرق ثم لوحة التشخيص.
الاعتماديات: PySide6 وraindesk.config وraindesk.engine وraindesk.platform_win وui.painters.
النمط التصميمي: Template Method (paintEvent) مع Adapter فوق أعلام Qt وواجهات Win32.
ملاحظات: الأعلام تُضبط في __init__ قبل أول show()؛ تغييرها لاحقًا يعيد إنشاء النافذة الأصلية.
    تُضاف الشخصية في مرحلة لاحقة (set_mascot أيضًا). وميض البرق يأتي من OverlayManager
    (حدث واحد مشترك بين الشاشات) عبر set_flash_alpha.
مثال: window = OverlayWindow(screen, store, rng); window.show(); window.advance(dt, params, gust)
"""

from __future__ import annotations

import time
from typing import Final

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (
    QColor,
    QHideEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QScreen,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from raindesk.config.schema import QUALITY_PROFILES
from raindesk.config.store import SettingsStore
from raindesk.core.constants import APP_NAME
from raindesk.engine.edge_streams import EdgeStreams
from raindesk.engine.math_utils import clamp
from raindesk.engine.params import EngineParams
from raindesk.engine.rain_field import GROUND_BOTTOM_EDGE, RainField
from raindesk.engine.splash_system import SplashSystem
from raindesk.engine.weather_fsm import LIGHTNING_PEAK_MAX
from raindesk.platform_win import win32_api
from raindesk.ui.painters.effects_painter import (
    paint_edge_streams,
    paint_lightning,
    paint_mood,
    paint_splashes,
)
from raindesk.ui.painters.hud_painter import paint_hud
from raindesk.ui.painters.rain_painter import paint_rain

_MS_PER_SECOND: Final[float] = 1000.0
_CLEAR_COLOR: Final[QColor] = QColor(0, 0, 0, 0)  # شفاف تمامًا
_DEFAULT_MULTIPLIER: Final[float] = 1.0  # معامل الكثافة إن لم يُعرف ملف الجودة
_DEFAULT_STREAM_COUNT: Final[int] = 3
_DEFAULT_MOOD_COLOR: Final[str] = "#0B1A2B"
_RNG_CHILDREN: Final[int] = 3  # مطر ورذاذ وجداول: تيار عشوائي مستقل لكل منها


def _as_float(value: object, default: float = 0.0) -> float:
    """قيمة إعداد عددية أو الافتراضي (bool ليس رقمًا هنا)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def compute_screen_key(screen: QScreen) -> str:
    """مفتاح ثابت للشاشة: الطراز مع الرقم التسلسلي، وإن غاب الرقم فاسم الشاشة (\\\\.\\DISPLAY1)."""
    return f"{screen.model()}:{screen.serialNumber() or screen.name()}"


class OverlayWindow(QWidget):
    """نافذة overlay لشاشة واحدة؛ لا تتلقى مدخلات ولا تأخذ التركيز أبدًا.

    الثوابت: حجم RainField وEdgeStreams يطابق حجم النافذة بعد كل advance؛ الرسم لا يغيّر حالة
    المحاكاة. سلامة الخيوط: خيط الواجهة فقط.
    """

    def __init__(
        self,
        screen: QScreen,
        store: SettingsStore,
        rng: np.random.Generator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._qscreen = screen
        self._store = store
        self._screen_key = compute_screen_key(screen)
        self._params: EngineParams | None = None
        self._last_paint_ms = 0.0
        self._exclude_applied = False
        self._closed = False
        self._multiplier = _DEFAULT_MULTIPLIER  # من ملف الجودة (drop_multiplier)
        self._adaptive_scale = 1.0  # من AdaptiveQuality عبر OverlayManager
        self._antialiasing = True
        self._splash_zone = GROUND_BOTTOM_EDGE
        self._streams_enabled = True
        self._streams_count = _DEFAULT_STREAM_COUNT
        self._streams_opacity = 0.0
        self._mood_enabled = False
        self._mood_color = _DEFAULT_MOOD_COLOR
        self._mood_opacity = 0.0
        self._flash_alpha = 0.0
        self._hud_enabled = False
        self._hud_fps = 0.0
        self._hud_interval_ms = 0.0
        self._last_advance_ms = 0.0

        # --- أعلام النافذة (تُضبط قبل أول show) ---
        # WindowTransparentForInput: click-through على مستوى النظام؛ Qt يطبّق النمط الموسّع
        # WS_EX_TRANSPARENT، وهو يعمل كتمرير نقرات على نافذة layered (WS_EX_LAYERED)، والخلفية
        # الشفافة تنتج تلك النافذة. WA_TransparentForMouseEvents وحدها تغيّر توزيع أحداث Qt
        # فقط ولا تكفي. كإجراء احتياطي نستدعي ensure_click_through بعد الإظهار (idempotent).
        # Tool: يطبّق WS_EX_TOOLWINDOW فلا زر في شريط المهام ولا ظهور في Alt+Tab.
        # WindowDoesNotAcceptFocus: يطبّق WS_EX_NOACTIVATE فلا تصبح النافذة الأمامية أبدًا.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        # WA_TranslucentBackground: شفافية لكل بكسل عبر نافذة layered. يجب أن يمسح
        # paintEvent المخزن في كل إطار (CompositionMode_Source مع تعبئة شفافة ثم العودة
        # إلى SourceOver) وإلا تتراكم الإطارات القديمة.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle(f"{APP_NAME} overlay")

        rect = self._target_rect()
        rain_rng, splash_rng, streams_rng = rng.spawn(_RNG_CHILDREN)
        self._field = RainField(rect.width(), rect.height(), rain_rng)
        self._splashes = SplashSystem(splash_rng)
        self._streams = EdgeStreams(rect.width(), rect.height(), streams_rng)
        self._field_size = (rect.width(), rect.height())
        self.refresh_render_options()

        self.setScreen(
            screen
        )  # قبل الهندسة كي تُفسَّر الإحداثيات على الشاشة الصحيحة (DPI)
        self.apply_geometry()
        screen.geometryChanged.connect(self._on_screen_geometry_changed)
        screen.availableGeometryChanged.connect(self._on_screen_geometry_changed)

    # ------------------------------------------------------------------ خصائص
    @property
    def screen_key(self) -> str:
        """مفتاح الشاشة المستقر (يُخزَّن به اختيار المستخدم)."""
        return self._screen_key

    @property
    def qscreen(self) -> QScreen:
        """كائن QScreen المربوط بهذه النافذة (للمقارنة بالهوية عند إعادة البناء)."""
        return self._qscreen

    @property
    def last_paint_ms(self) -> float:
        """زمن آخر paintEvent بالميلي ثانية."""
        return self._last_paint_ms

    @property
    def last_advance_ms(self) -> float:
        """زمن آخر advance (محاكاة المطر والرذاذ والجداول) بالميلي ثانية."""
        return self._last_advance_ms

    @property
    def drop_count(self) -> int:
        """عدد قطرات المطر الفعّالة حاليًا."""
        return self._field.active_count

    # ------------------------------------------------------------------ الهندسة
    def _target_rect(self) -> QRect:
        """geometry() كاملة إذا cover_taskbar، وإلا availableGeometry() (بدون شريط المهام)."""
        if bool(self._store.get("cover_taskbar")):
            return self._qscreen.geometry()
        return self._qscreen.availableGeometry()

    def apply_geometry(self) -> None:
        """يطبّق الهندسة المطلوبة؛ لا نستعمل showFullScreen لأنه يغيّر سلوك شريط المهام."""
        rect = self._target_rect()
        if rect != self.geometry():
            self.setGeometry(rect)

    def _on_screen_geometry_changed(self, _rect: QRect) -> None:
        if not self._closed:
            self.apply_geometry()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_field_size()

    def _sync_field_size(self) -> None:
        """يوفّق المحاكيات مع حجم النافذة (بالبكسل المنطقي)؛ لا شيء إن لم يتغيّر."""
        size = (self.width(), self.height())
        if size != self._field_size:
            self._field.resize(size[0], size[1])
            self._field.set_ground(size[1], self._splash_zone)
            self._streams.resize(size[0], size[1])
            self._field_size = size

    # ------------------------------------------------------------------ Win32
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        hwnd = int(self.winId())  # المقبض الأصلي صالح بعد الإظهار
        win32_api.ensure_click_through(hwnd)
        win32_api.set_topmost(hwnd)
        self.refresh_native_options()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        """عند الإخفاء (إيقاف مؤقت) نمسح الرذاذ والوميض كي لا تظهر بقاياهما عند الاستئناف."""
        super().hideEvent(event)
        self._splashes.clear()
        self._flash_alpha = 0.0

    def reassert_topmost(self) -> None:
        """يعيد تثبيت النافذة فوق الأخرى (بعد الاستئناف أو الفتح أو مؤقّت الحراسة)."""
        if self.isVisible():
            win32_api.set_topmost(int(self.winId()))

    def refresh_native_options(self) -> None:
        """يطبّق exclude_from_capture عند اختلافه عن الحالة المطبَّقة (تجريبي)."""
        wanted = bool(self._store.get("exclude_from_capture"))
        if wanted == self._exclude_applied or not self.isVisible():
            return
        if win32_api.set_exclude_from_capture(int(self.winId()), wanted):
            self._exclude_applied = wanted

    # ------------------------------------------------------------------ خيارات الرسم
    def refresh_render_options(self) -> None:
        """يعيد قراءة خيارات الرسم ويخزّنها (لا نقرأ المخزن كل إطار)."""
        get = self._store.get
        self._antialiasing = bool(get("antialiasing"))
        profile = QUALITY_PROFILES.get(str(get("quality")))
        self._multiplier = profile.drop_multiplier if profile else _DEFAULT_MULTIPLIER
        self._splash_zone = str(get("splash_zone"))
        self._field.set_ground(self.height() or self._field_size[1], self._splash_zone)

        self._streams_enabled = bool(get("edge_streams_enabled"))
        self._streams_count = round(
            _as_float(get("edge_streams_count"), _DEFAULT_STREAM_COUNT)
        )
        self._streams_opacity = _as_float(get("edge_streams_opacity"))
        self._streams.configure(
            self._streams_count if self._streams_enabled else 0, self._streams_opacity
        )

        self._mood_enabled = bool(get("mood_enabled"))
        self._mood_color = str(get("mood_color"))
        self._mood_opacity = _as_float(get("mood_opacity"))
        self._hud_enabled = bool(get("debug_hud"))

    def set_adaptive_scale(self, scale: float) -> None:
        """معامل الجودة التكيفية في [0, 1]؛ يُضرب في العدد المستهدف للقطرات."""
        self._adaptive_scale = clamp(scale, 0.0, 1.0)

    def set_hud_metrics(self, fps: float, interval_ms: float) -> None:
        """قياسات الإطار المشتركة (من OverlayManager) لعرضها في لوحة التشخيص."""
        self._hud_fps = fps
        self._hud_interval_ms = interval_ms

    def set_flash_alpha(self, alpha: float) -> None:
        """شدة وميض البرق الحالية (من OverlayManager)؛ تُقيَّد بسقف الأمان مهما كانت القيمة."""
        self._flash_alpha = clamp(alpha, 0.0, LIGHTNING_PEAK_MAX)

    # ------------------------------------------------------------------ المحاكاة والرسم
    def advance(self, dt: float, params: EngineParams, gust: float) -> None:
        """يقدّم المحاكاة بزمن dt ويطلب إعادة الرسم.

        العدد المستهدف = target_count(الحجم، الشدة، معامل الجودة * المعامل التكيفي، زاوية الرياح).
        نفرّغ هبوطات المطر كل إطار (حتى لو كان الرذاذ معطّلًا) كي لا يمتلئ مخزنها الداخلي.
        """
        started = time.perf_counter()
        self._params = params
        self._sync_field_size()
        count = RainField.target_count(
            self._field_size[0],
            self._field_size[1],
            params.intensity,
            self._multiplier * self._adaptive_scale,
            params.wind_angle_deg,
        )
        self._field.set_active_count(count)
        self._field.step(dt, params, gust)
        self._splashes.spawn(self._field.drain_landings(), params.splash_amount)
        self._splashes.step(dt)
        self._streams.step(dt, gust)
        self._last_advance_ms = (time.perf_counter() - started) * _MS_PER_SECOND
        self.update()

    def _hud_lines(self) -> list[str]:
        """أسطر لوحة التشخيص: معدل الإطارات، وأزمنة المحاكاة والرسم، وعدد القطرات والمعامل."""
        return [
            f"FPS {self._hud_fps:5.1f}   frame {self._hud_interval_ms:5.1f} ms",
            f"engine {self._last_advance_ms:5.2f} ms   paint {self._last_paint_ms:5.2f} ms",
            f"drops {self._field.active_count:4d}   scale {self._adaptive_scale:4.2f}",
        ]

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        started = time.perf_counter()
        painter = QPainter(self)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), _CLEAR_COLOR)  # مسح المخزن بشفافية كاملة
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, self._antialiasing)
            width, height = float(self.width()), float(self.height())
            if self._params is not None:
                if self._mood_enabled:
                    paint_mood(
                        painter, width, height, self._mood_color, self._mood_opacity
                    )
                paint_edge_streams(painter, self._streams, self._params, height)
                paint_rain(painter, self._field, self._params)
                paint_splashes(painter, self._splashes, self._params)
            paint_lightning(painter, width, height, self._flash_alpha)
            if self._hud_enabled:
                paint_hud(painter, self._hud_lines())
        finally:
            painter.end()
        self._last_paint_ms = (time.perf_counter() - started) * _MS_PER_SECOND

    # ------------------------------------------------------------------ الإنهاء
    def shutdown(self) -> None:
        """يفصل الإشارات ويخفي النافذة ويجدول حذفها؛ آمن عند التكرار."""
        if self._closed:
            return
        self._closed = True
        for signal in (
            self._qscreen.geometryChanged,
            self._qscreen.availableGeometryChanged,
        ):
            try:
                signal.disconnect(self._on_screen_geometry_changed)
            except (RuntimeError, TypeError):
                pass  # الشاشة حُذفت أو الاتصال مفصول أصلًا
        self.hide()
        self.deleteLater()
