"""raindesk/ui/mascot_host.py

الغرض: يملك الشخصية Drip الوحيدة ويستضيفها على نافذة شاشة واحدة ويقدّمها مع كل tick.
المسؤوليات: قراءة إعدادات الشخصية (mascot_enabled وmascot_frequency وmascot_scale)، واختيار
    نافذة المضيف (الشاشة الأساسية وإلا أول نافذة)، وتمرير الكائن إليها أو سحبه، وتغذية الشخصية
    بما تتفاعل معه: موضع المؤشر بإحداثيات النافذة، وميل الرياح (نظرة العينين)، وشدة المطر،
    وحافة صعود وميض البرق (فزع)، وعدم فعل أي شيء إن عُطّلت.
الاعتماديات: config.store وengine.mascot وengine.math_utils وui.overlay_window وPySide6.QtGui.
النمط التصميمي: Facade صغير يخفي تفاصيل الاستضافة عن OverlayManager (Single Responsibility).
ملاحظات: ليس QObject: لا إشارات ولا مؤقتات، فالمدير يستدعي sync عند تغيّر الإعدادات أو النوافذ
    وstep مع كل tick. قراءة موضع الفأرة (QCursor.pos) للقراءة فقط: لا نعترض أي مدخلات والنافذة
    تبقى click-through. التعطيل يخفي الشخصية فورًا ويسحبها من النافذة فلا خطوة ولا رسم.
مثال: host = MascotHost(store, rng); host.sync(windows); host.step(dt, angle, rain, flash)
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Final

from PySide6.QtGui import QCursor, QGuiApplication

from raindesk.config.store import SettingsStore
from raindesk.engine.mascot import Mascot
from raindesk.engine.math_utils import clamp
from raindesk.ui.overlay_window import OverlayWindow

MASCOT_KEYS: Final[frozenset[str]] = frozenset(
    {"mascot_enabled", "mascot_frequency", "mascot_scale"}
)
_DEFAULT_FREQUENCY: Final[float] = 0.4  # يطابق الافتراضي في المخطط
_WIND_LOOK_DEADZONE_DEG: Final[float] = 2.0  # درجة: ميل أصغر من هذا لا يحرّك نظرة العينين
_WIND_LOOK_FULL_DEG: Final[float] = 30.0  # درجة: الميل الذي تنظر عنده العينان بأقصى إزاحة
_FLASH_STARTLE_ALPHA: Final[float] = 0.03  # شدة وميض تُعدّ برقًا يفزع Drip (عند الصعود فقط)


def wind_look(angle_deg: float) -> float:
    """اتجاه نظر Drip في [-1, 1] من ميل الرياح (موجب = يميل المطر نحو اليمين)."""
    if abs(angle_deg) < _WIND_LOOK_DEADZONE_DEG:
        return 0.0
    return clamp(angle_deg / _WIND_LOOK_FULL_DEG, -1.0, 1.0)


def _as_float(value: object, default: float) -> float:
    """قيمة إعداد عددية أو الافتراضي (bool ليس رقمًا هنا)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


class MascotHost:
    """مالك Drip ومضيفها؛ يعيش مع OverlayManager ويُنهى معه بـ shutdown().

    الثوابت (invariants): تحمل نافذةٌ واحدة على الأكثر الشخصية، ولا تحملها أي نافذة إن
        كانت معطّلة. التعقيد: sync هو O(عدد النوافذ)، وstep هو O(1). سلامة الخيوط: الواجهة فقط.
    """

    def __init__(self, store: SettingsStore, rng: random.Random) -> None:
        self._store = store
        self._mascot = Mascot(rng)
        self._enabled = False
        self._window: OverlayWindow | None = None
        self._flash_high = False  # لاكتشاف حافة الصعود: وميض واحد = فزعة واحدة

    @property
    def mascot(self) -> Mascot:
        """الشخصية نفسها (للقراءة والاختبار)."""
        return self._mascot

    @property
    def window(self) -> OverlayWindow | None:
        """النافذة المضيفة حاليًا (None إن عُطّلت الشخصية أو لا نوافذ)."""
        return self._window

    def sync(self, windows: Sequence[OverlayWindow]) -> None:
        """يطابق الشخصية والمضيف مع الإعدادات والنوافذ الحالية (آمن عند التكرار)."""
        get = self._store.get
        self._enabled = bool(get("mascot_enabled"))
        self._mascot.configure(
            self._enabled,
            _as_float(get("mascot_frequency"), _DEFAULT_FREQUENCY),
            _as_float(get("mascot_scale"), 1.0),
        )
        host = self._pick(windows) if self._enabled else None
        if host is self._window:
            return
        if self._window is not None:
            self._window.set_mascot(None)
        self._window = host
        if host is not None:
            host.set_mascot(self._mascot)

    @staticmethod
    def _pick(windows: Sequence[OverlayWindow]) -> OverlayWindow | None:
        """نافذة الشاشة الأساسية، وإلا أول نافذة."""
        primary = QGuiApplication.primaryScreen()
        for window in windows:
            if window.qscreen is primary:
                return window
        return windows[0] if windows else None

    @staticmethod
    def _pointer_in(window: OverlayWindow) -> tuple[float, float] | None:
        """موضع الفأرة بإحداثيات النافذة المنطقية، أو None إن كانت خارجها (شاشة أخرى مثلًا)."""
        point = window.mapFromGlobal(QCursor.pos())
        if not window.rect().contains(point):
            return None
        return float(point.x()), float(point.y())

    def step(self, dt: float, wind_angle_deg: float, rain: float = 0.0, flash: float = 0.0) -> None:
        """يغذّي الشخصية بالمؤشر والمطر والبرق ثم يقدّمها؛ لا شيء إن عُطّلت (كلفة صفرية)."""
        window = self._window
        if not self._enabled or window is None:
            return
        self._mascot.set_weather(rain)
        self._mascot.set_pointer(self._pointer_in(window))
        high = flash >= _FLASH_STARTLE_ALPHA
        if high and not self._flash_high:
            self._mascot.startle()
        self._flash_high = high
        self._mascot.step(dt, wind_look(wind_angle_deg))

    def shutdown(self) -> None:
        """يسحب الشخصية من النافذة ويعطّلها؛ آمن عند التكرار."""
        self._enabled = False
        self._flash_high = False
        if self._window is not None:
            self._window.set_mascot(None)
            self._window = None
        self._mascot.configure(False, 0.0, 1.0)
