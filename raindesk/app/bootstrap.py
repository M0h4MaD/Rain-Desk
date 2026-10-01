"""raindesk/app/bootstrap.py

الغرض: Composition Root: يبني الكائنات ويربطها ويشغّل حلقة الأحداث ويعيد رمز الخروج.
المسؤوليات (نسخة M5): سطر الأوامر، والسجلات، وQApplication، والنسخة الواحدة، والإعدادات،
    والترجمة واتجاه الواجهة، والسمة، وFrameClock وOverlayManager، وأيقونة الشريط، وAppController،
    وسرعة الإطارات، وترتيب الإنهاء.
الاعتماديات: كل الطبقات (الجذر الوحيد المسموح له بذلك).
النمط التصميمي: Composition Root (تجميع الاعتماديات في مكان واحد).
ملاحظات: أعلام سطر الأوامر: --minimized و--selftest و--selftest-seconds N.
    توجيه تغيّر الإعدادات صار في AppController، وتبقى هنا fps_cap فقط لأن bootstrap تملك الساعة.
مثال: raise SystemExit(main())
"""

from __future__ import annotations

import argparse
import logging
import math
import signal
import sys
from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from raindesk.app.controller import AppController
from raindesk.config.store import SettingsStore
from raindesk.core.constants import APP_NAME, APP_VERSION
from raindesk.core.logging_setup import configure_logging, install_excepthook
from raindesk.core.single_instance import SingleInstanceGuard
from raindesk.i18n.translator import Translator
from raindesk.ui.frame_clock import FrameClock
from raindesk.ui.overlay_manager import OverlayManager
from raindesk.ui.theme import ThemeManager
from raindesk.ui.tray import TrayController

_LOG = logging.getLogger(__name__)

_SELFTEST_SECONDS: Final[float] = 1.0  # زمن تشغيل --selftest قبل الخروج التلقائي
_MS_PER_SECOND: Final[int] = 1000
_SIGNAL_POLL_MS: Final[int] = 200  # ms: يمنح بايثون فرصة لمعالجة Ctrl+C أثناء حلقة Qt
_DEFAULT_FPS: Final[int] = 30
_EXIT_OK: Final[int] = 0
_EXIT_ERROR: Final[int] = 1


@dataclass(frozen=True, slots=True)
class _Options:
    """خيارات سطر الأوامر بعد التحليل."""

    minimized: bool
    selftest: bool
    selftest_seconds: float | None
    qt_args: list[str]  # أعلام لا نعرفها تُمرَّر إلى Qt (مثل -platform)


def _positive_float(text: str) -> float:
    """محوّل argparse لرقم موجب منتهٍ (يرفض 0 وNaN وinf والقيم السالبة)."""
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return value


def _parse_args(argv: list[str]) -> _Options:
    """يحلّل الأعلام؛ يرفع SystemExit عند --help أو عند خطأ في القيم (سلوك argparse)."""
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Rain overlay for Windows.")
    parser.add_argument("--minimized", action="store_true", help="start in the tray")
    parser.add_argument("--selftest", action="store_true", help="start, log, quit after 1 s")
    parser.add_argument(
        "--selftest-seconds", type=_positive_float, metavar="N", help="run normally for N seconds"
    )
    known, unknown = parser.parse_known_args(argv)
    return _Options(known.minimized, known.selftest, known.selftest_seconds, list(unknown))


def _as_int(value: object, default: int) -> int:
    """قيمة إعداد صحيحة أو الافتراضي (يستبعد bool لأنه فرع من int)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _apply_layout_direction(app: QApplication, translator: Translator) -> None:
    """RTL للعربية وLTR للإنجليزية، فوريًا ولكل النوافذ."""
    app.setLayoutDirection(
        Qt.LayoutDirection.RightToLeft if translator.is_rtl else Qt.LayoutDirection.LeftToRight
    )


def _install_interrupt_handler(app: QApplication) -> None:
    """يجعل Ctrl+C يغلق التطبيق بأمان (فيُحفظ كل شيء) بدل قتل العملية.

    مؤقّت فارغ يوقظ مفسّر بايثون بشكل دوري، لأن معالجات الإشارات لا تعمل أثناء
    QApplication.exec() ما لم يعُد التحكم لبايثون من حين لآخر.
    """
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer(app)
    heartbeat.setInterval(_SIGNAL_POLL_MS)
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start()


def main(argv: list[str] | None = None) -> int:
    """نقطة الدخول: يبني التطبيق ويشغّله ويعيد رمز الخروج (0 نجاح، 1 فشل، 2 خطأ في الأعلام)."""
    raw_args = sys.argv[1:] if argv is None else argv
    try:
        options = _parse_args(raw_args)
    except SystemExit as exc:  # --help أو قيمة خاطئة: رمز argparse (0 أو 2)
        code = exc.code
        return code if isinstance(code, int) else (_EXIT_OK if code is None else _EXIT_ERROR)

    configure_logging()  # مستوى مبدئي INFO حتى تُحمَّل الإعدادات
    install_excepthook()

    app = QApplication([sys.argv[0] if sys.argv else APP_NAME, *options.qt_args])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)  # التطبيق يعيش في شريط النظام لا في نافذة

    guard = SingleInstanceGuard(parent=app)
    if not guard.acquire():
        guard.notify_primary()
        _LOG.info("another instance is already running; exiting")
        return _EXIT_OK

    store = SettingsStore(parent=app)
    store.load()
    configure_logging(str(store.get("log_level")))  # إعادة الضبط بمستوى المستخدم
    if store.last_corrupt_backup is not None:
        _LOG.warning("settings were damaged; backup: %s", store.last_corrupt_backup)

    translator = Translator(app)
    translator.set_language(str(store.get("language")))
    _apply_layout_direction(app, translator)
    translator.language_changed.connect(lambda _code: _apply_layout_direction(app, translator))

    theme = ThemeManager(app)
    theme.apply(str(store.get("theme")))  # قبل إنشاء أي نافذة كي تولد بالسمة الصحيحة

    clock = FrameClock(app)
    clock.set_fps(_as_int(store.get("fps_cap"), _DEFAULT_FPS))
    store.changed.connect(
        lambda key: clock.set_fps(_as_int(store.get("fps_cap"), _DEFAULT_FPS))
        if key == "fps_cap"
        else None
    )
    manager = OverlayManager(store, clock, app)
    manager.set_pause_reason("user_disabled", not bool(store.get("enabled")))  # قبل البناء
    manager.rebuild()

    tray = TrayController(translator, app)
    app.setWindowIcon(tray.app_icon)
    controller = AppController(store, translator, theme, manager, None, tray, guard, app)
    controller.start(minimized=options.minimized)

    def on_about_to_quit() -> None:
        """ترتيب الإنهاء: الواجهة والأيقونة، ثم الساعة والنوافذ، ثم الحفظ، ثم حارس النسخة."""
        controller.shutdown()
        manager.shutdown()
        store.save_now()
        guard.shutdown()
        _LOG.info("RainDesk stopped")

    app.aboutToQuit.connect(on_about_to_quit)
    _install_interrupt_handler(app)

    quit_after_s = _SELFTEST_SECONDS if options.selftest else options.selftest_seconds
    if quit_after_s is not None:
        QTimer.singleShot(int(quit_after_s * _MS_PER_SECOND), app.quit)

    _LOG.info("RainDesk started")
    _LOG.debug(
        "version=%s language=%s minimized=%s", APP_VERSION, translator.language, options.minimized
    )
    return int(app.exec())