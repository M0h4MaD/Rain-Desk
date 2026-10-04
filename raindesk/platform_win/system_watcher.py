"""raindesk/platform_win/system_watcher.py

الغرض: مراقبة حالة النظام التي تستوجب إيقاف المطر مؤقتًا: تطبيق بملء الشاشة، وجلسة مقفلة أو
    شاشة توقف، وموفّر البطارية.
المسؤوليات: استطلاع دوري (كل SYSTEM_WATCH_INTERVAL_MS) وإصدار reasons_changed عند تغيّر
    مجموعة الأسباب فقط.
الاعتماديات: QtCore وraindesk.platform_win.win32_api وraindesk.core.constants.
النمط التصميمي: Polling Observer (الاستطلاع أبسط وأوثق من نوافذ الرسائل لإشعارات النظام).
ملاحظات: التحويل من حالة SHQueryUserNotificationState: NOT_PRESENT يعني session_inactive دائمًا
    (لا معنى للرسم والجلسة مقفلة)، وBUSY أو RUNNING_D3D_FULL_SCREEN أو PRESENTATION_MODE تعني
    fullscreen إن فُعّل الخيار. الاستطلاع كل ثانيتين يمتص وميض الحالات العابرة (Alt+Tab).
    خارج Windows تعيد الدوال الأساسية قيمًا محايدة فلا أسباب إيقاف.
مثال: watcher = SystemWatcher(); watcher.reasons_changed.connect(f); watcher.start()
"""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtCore import QObject, QTimer, Signal

from raindesk.core.constants import SYSTEM_WATCH_INTERVAL_MS
from raindesk.platform_win import win32_api
from raindesk.platform_win.win32_api import UserNotificationState

_LOG = logging.getLogger(__name__)

REASON_FULLSCREEN: Final[str] = "fullscreen"
REASON_SESSION: Final[str] = "session_inactive"
REASON_BATTERY: Final[str] = "battery_saver"
_FULLSCREEN_STATES: Final[frozenset[UserNotificationState]] = frozenset({
    UserNotificationState.BUSY,
    UserNotificationState.RUNNING_D3D_FULL_SCREEN,
    UserNotificationState.PRESENTATION_MODE,
})


class SystemWatcher(QObject):
    """يستطلع النظام ويُصدر مجموعة أسباب الإيقاف الحالية عند تغيّرها."""

    reasons_changed = Signal(object)  # frozenset[str]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pause_on_fullscreen = True
        self._pause_on_battery_saver = True
        self._reasons: frozenset[str] = frozenset()
        self._timer = QTimer(self)
        self._timer.setInterval(SYSTEM_WATCH_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

    def set_options(self, pause_on_fullscreen: bool, pause_on_battery_saver: bool) -> None:
        """يضبط الخيارات ويعيد الاستطلاع فورًا إن كانت المراقبة تعمل (أثر فوري للمستخدم)."""
        self._pause_on_fullscreen = pause_on_fullscreen
        self._pause_on_battery_saver = pause_on_battery_saver
        if self._timer.isActive():
            self._poll()

    def start(self) -> None:
        """يبدأ المراقبة باستطلاع فوري ثم دوري؛ آمن عند التكرار."""
        if not self._timer.isActive():
            self._timer.start()
        self._poll()

    def stop(self) -> None:
        """يوقف المراقبة (المؤقّت فقط؛ الأسباب الحالية تبقى كما هي)."""
        self._timer.stop()

    def current_reasons(self) -> frozenset[str]:
        """الأسباب القائمة حاليًا (آخر استطلاع)."""
        return self._reasons

    def _compute_reasons(self) -> frozenset[str]:
        reasons: set[str] = set()
        state = win32_api.query_user_notification_state()
        if state == UserNotificationState.NOT_PRESENT:
            reasons.add(REASON_SESSION)
        elif self._pause_on_fullscreen and state in _FULLSCREEN_STATES:
            reasons.add(REASON_FULLSCREEN)
        if self._pause_on_battery_saver and win32_api.is_battery_saver_on():
            reasons.add(REASON_BATTERY)
        return frozenset(reasons)

    def _poll(self) -> None:
        reasons = self._compute_reasons()
        if reasons == self._reasons:
            return
        _LOG.info("pause reasons changed: %s -> %s", sorted(self._reasons), sorted(reasons))
        self._reasons = reasons
        self.reasons_changed.emit(reasons)