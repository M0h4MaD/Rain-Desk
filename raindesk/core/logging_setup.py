"""raindesk/core/logging_setup.py

الغرض: إعداد السجلات (logging) ومعالج الاستثناءات غير الملتقطة.
المسؤوليات: ملف سجل دوّار في log_dir()، وطرفية عند التشغيل من المصدر فقط، وتسجيل
    الأخطاء غير الملتقطة دون إسقاط التطبيق.
الاعتماديات: raindesk.core.paths والمكتبة القياسية.
النمط التصميمي: Idempotent Configuration (الاستدعاء المتكرر لا يضاعف المعالجات).
ملاحظات: الحزمة 'raindesk' لها سجلّها الخاص؛ الوحدات تستعمل logging.getLogger(__name__)
    فترث إعداداته تلقائيًا. الملف الدوّار يحدّ استهلاك القرص: 1 MB * (1 + 3 نسخ) = 4 MB كحد أقصى.
مثال: configure_logging('DEBUG'); install_excepthook()
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from types import TracebackType
from typing import Final

from raindesk.core.paths import log_dir

_LOGGER_NAME: Final[str] = "raindesk"  # اسم سجل الحزمة الجذر
_LOG_FILENAME: Final[str] = "raindesk.log"
_LOG_MAX_BYTES: Final[int] = 1024 * 1024  # 1 MB للملف الواحد قبل التدوير
_LOG_BACKUP_COUNT: Final[int] = 3  # عدد النسخ القديمة المحفوظة
_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DEFAULT_LEVEL: Final[int] = logging.INFO  # يُستعمل عند تمرير اسم مستوى غير معروف
_FILE_HANDLER_NAME: Final[str] = "raindesk-file"  # أسماء تميّز معالجاتنا عن أي معالج آخر
_CONSOLE_HANDLER_NAME: Final[str] = "raindesk-console"


def _remove_own_handlers(logger: logging.Logger) -> None:
    """يزيل ويغلق معالجاتنا السابقة فقط، حتى لا تتكرر الأسطر عند إعادة الإعداد."""
    for handler in list(logger.handlers):
        if handler.get_name() in (_FILE_HANDLER_NAME, _CONSOLE_HANDLER_NAME):
            logger.removeHandler(handler)
            handler.close()


def configure_logging(level: str = "INFO") -> None:
    """يضبط سجل الحزمة: ملف دوّار دائمًا، وطرفية إذا لم يكن التطبيق مجمّدًا بـ PyInstaller.

    Args:
        level: اسم المستوى ('DEBUG'، 'INFO'، ...) غير حساس لحالة الأحرف؛ غير المعروف يصبح INFO.
    فشل إنشاء ملف السجل (صلاحيات، قرص ممتلئ) لا يوقف التطبيق: نكتفي بالطرفية إن وُجدت.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.getLevelNamesMapping().get(level.upper(), _DEFAULT_LEVEL))
    _remove_own_handlers(logger)
    formatter = logging.Formatter(_LOG_FORMAT)

    try:
        file_handler = RotatingFileHandler(
            log_dir() / _LOG_FILENAME,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",  # ترميز صريح لأن ترميز Windows الافتراضي قد يكسر الأحرف العربية
        )
    except OSError:
        file_handler = None
    if file_handler is not None:
        file_handler.set_name(_FILE_HANDLER_NAME)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # في الحزمة النهائية (windowed) لا توجد طرفية، فنتجنّب معالجًا بلا وجهة.
    if not getattr(sys, "frozen", False):
        console_handler = logging.StreamHandler()
        console_handler.set_name(_CONSOLE_HANDLER_NAME)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


def install_excepthook() -> None:
    """يثبّت معالجًا لكل الاستثناءات غير الملتقطة (الخيط الرئيسي وبقية الخيوط).

    المعالج يسجّل الخطأ بمستوى CRITICAL مع traceback ولا يعيد رفعه، فيبقى التطبيق حيًّا
    بدل الانهيار عند خطأ داخل slot تستدعيه Qt. Ctrl+C يمرَّر للمعالج الافتراضي.
    """
    logger = logging.getLogger(_LOGGER_NAME)

    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        try:
            logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        except Exception:  # noqa: BLE001  المعالج نفسه يجب ألا يرفع خطأً أبدًا
            pass

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit or args.exc_value is None:
            return  # خروج طبيعي من خيط، أو استثناء بلا قيمة يمكن تسجيلها
        _hook(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _hook
    threading.excepthook = _thread_hook