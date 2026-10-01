"""raindesk/i18n/translator.py

الغرض: ترجمة مفاتيح الواجهة فوريًا (عربي/إنجليزي/تلقائي) مع إشعار الواجهات عند التبديل.
المسؤوليات: تحديد اللغة الفعلية، والبحث بسلسلة احتياط، وتنسيق المتغيرات، وتحديد اتجاه RTL.
الاعتماديات: QtCore وstrings_en وstrings_ar.
النمط التصميمي: Observer (الإشارة language_changed) مع Fallback Chain للنصوص.
ملاحظات: سلسلة الاحتياط: اللغة الحالية ثم الإنجليزية ثم المفتاح نفسه (مع تحذير مرة واحدة).
    الأرقام الغربية (0-9) في اللغتين، وتبديل اتجاه الواجهة (Layout Direction) يتم في bootstrap.
مثال: translator.tr('msg.settings_corrupt', name='settings.corrupt-1.json')
"""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtCore import QLocale, QObject, Signal

from raindesk.i18n import strings_ar, strings_en

_LOG = logging.getLogger(__name__)

LANGUAGE_AUTO: Final[str] = "auto"
LANGUAGE_AR: Final[str] = "ar"
LANGUAGE_EN: Final[str] = "en"

_SUPPORTED_CODES: Final[tuple[str, ...]] = (LANGUAGE_AUTO, LANGUAGE_AR, LANGUAGE_EN)
_TABLES: Final[dict[str, dict[str, str]]] = {
    LANGUAGE_EN: strings_en.STRINGS,
    LANGUAGE_AR: strings_ar.STRINGS,
}
_NATIVE_NAMES: Final[dict[str, str]] = {LANGUAGE_AR: "العربية", LANGUAGE_EN: "English"}
_RTL_LANGUAGES: Final[frozenset[str]] = frozenset({LANGUAGE_AR})
_AUTO_KEY: Final[str] = "lang.auto"  # مفتاح اسم خيار "تلقائي" في القائمة


def _system_ui_language() -> str:
    """لغة واجهة النظام كنص مثل 'ar-SA' (دالة منفصلة ليسهل استبدالها في الاختبارات)."""
    locale = QLocale.system()
    languages = locale.uiLanguages()
    return str(languages[0]) if languages else locale.name()


class Translator(QObject):
    """يترجم المفاتيح ويبلّغ عن تغيّر اللغة الفعلية (وليس عن تغيّر الطلب فقط)."""

    language_changed = Signal(str)  # اللغة الفعلية الجديدة: 'ar' أو 'en'

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._language: str = self._resolve(LANGUAGE_AUTO)
        self._warned: set[str] = set()  # مفاتيح حُذّر منها، كي لا يتكرر التحذير كل رسمة

    @staticmethod
    def _resolve(code: str) -> str:
        """يحوّل 'auto' إلى 'ar' إن بدأت لغة النظام بـ 'ar'، وإلا 'en'؛ وغير ذلك يبقى كما هو."""
        if code == LANGUAGE_AUTO:
            is_arabic = _system_ui_language().lower().startswith(LANGUAGE_AR)
            return LANGUAGE_AR if is_arabic else LANGUAGE_EN
        return code

    def set_language(self, code: str) -> None:
        """يضبط اللغة ('auto' أو 'ar' أو 'en')؛ رمز غير معروف يُعامَل كـ 'auto' مع تحذير.

        تُصدَر language_changed فقط إذا تغيّرت اللغة الفعلية.
        """
        if code not in _SUPPORTED_CODES:
            _LOG.warning("unsupported language code %r; falling back to auto", code)
            code = LANGUAGE_AUTO
        resolved = self._resolve(code)
        if resolved == self._language:
            return
        self._language = resolved
        self.language_changed.emit(resolved)

    @property
    def language(self) -> str:
        """اللغة الفعلية الحالية: 'ar' أو 'en' (لا تكون 'auto' أبدًا)."""
        return self._language

    @property
    def is_rtl(self) -> bool:
        """True إذا كانت اللغة الحالية تُكتب من اليمين إلى اليسار."""
        return self._language in _RTL_LANGUAGES

    def _warn_once(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            _LOG.warning("%s: %s", message, key)

    def tr(self, key: str, **fmt: object) -> str:  # type: ignore[override]
        """يترجم مفتاحًا؛ يستبدل تعريف QObject.tr عمدًا لأن العقد يفرض هذا التوقيع.

        Args:
            key: مفتاح النص (مثل 'msg.first_run_title').
            **fmt: قيم المتغيرات {placeholders}؛ غياب متغير يعيد النص الخام مع تحذير.
        Returns:
            النص المترجم، أو النص الإنجليزي، أو المفتاح نفسه إن لم يوجد في أي منهما.
        """
        text = _TABLES[self._language].get(key)
        if text is None:
            text = _TABLES[LANGUAGE_EN].get(key)
        if text is None:
            self._warn_once(key, "missing translation key")
            return key
        if not fmt:
            return text
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            self._warn_once(key, "bad format arguments for key")
            return text

    def available_languages(self) -> list[tuple[str, str]]:
        """قائمة (الرمز، الاسم الظاهر) للقائمة المنسدلة؛ أسماء اللغات بلغاتها الأصلية."""
        return [
            (LANGUAGE_AUTO, self.tr(_AUTO_KEY)),
            (LANGUAGE_AR, _NATIVE_NAMES[LANGUAGE_AR]),
            (LANGUAGE_EN, _NATIVE_NAMES[LANGUAGE_EN]),
        ]