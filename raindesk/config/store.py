"""raindesk/config/store.py

الغرض: مخزن الإعدادات الحي: تحميل، وحفظ ذري، وتحقق، وإشعار بالتغيّرات.
المسؤوليات: قراءة settings.json مع عزل الملف التالف، وتطبيق الكتابات بعد التحقق، وإصدار
    'changed' عند التغيّر الفعلي فقط، وحفظ مؤجَّل (debounce)، والإعدادات المسبقة والجودة،
    والاستيراد والتصدير.
الاعتماديات: QtCore وraindesk.config.schema وraindesk.core.
النمط التصميمي: Observer (إشارات Qt) مع Repository لملف JSON وDebounce للكتابة.
ملاحظات: كل الاستدعاءات من خيط الواجهة. الكتابة ذرية: ملف مؤقت ثم fsync ثم os.replace،
    فلا يبقى ملف نصف مكتوب عند انقطاع الكهرباء. الملف صغير (بضع مئات بايت) فلا يعطّل الواجهة.
مثال: store = SettingsStore(); store.load(); store.set('intensity', 0.7)
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Final

from PySide6.QtCore import QObject, QTimer, Signal

from raindesk.config.schema import (
    FIELD_SPECS,
    PRESETS,
    QUALITY_PROFILES,
    Settings,
    default_settings,
    migrate,
    settings_to_dict,
    validate_and_coerce,
)
from raindesk.core.constants import SETTINGS_SAVE_DEBOUNCE_MS
from raindesk.core.paths import settings_path

_LOG = logging.getLogger(__name__)

# الحقول التي تتحكم بها الإعدادات المسبقة: كتابة أي منها من الواجهة تحوّل preset إلى custom.
_PRESET_FIELD_KEYS: Final[frozenset[str]] = frozenset(PRESETS["moderate"])
_MANAGED_KEYS: Final[frozenset[str]] = frozenset({"schema_version"})  # يديرها migrate فقط
# لا تُستورد من ملف آخر لأنها خاصة بهذا الجهاز أو بهذه النسخة.
_IMPORT_SKIP_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "first_run_completed", "window_geometry"}
)
_DEFAULT_KEEP: Final[tuple[str, ...]] = ("first_run_completed", "window_geometry")
_CORRUPT_TIMESTAMP_FORMAT: Final[str] = "%Y%m%d-%H%M%S"
_TMP_SUFFIX: Final[str] = ".tmp"
_JSON_INDENT: Final[int] = 2
_JSON_READ_ENCODING: Final[str] = "utf-8-sig"  # يتسامح مع BOM إن حفظ المحرر الملف به


def _read_json_object(path: Path) -> dict[str, object]:
    """يقرأ ملف JSON جذره كائن (object).

    Raises:
        OSError: تعذّرت القراءة (الملف غير موجود، صلاحيات).
        ValueError: النص ليس JSON صالحًا أو ترميزه خاطئ أو الجذر ليس كائنًا.
        RecursionError: تداخل مفرط في الملف.
    """
    parsed = json.loads(path.read_text(encoding=_JSON_READ_ENCODING))
    if not isinstance(parsed, dict):
        raise ValueError("JSON root is not an object")
    return parsed


def _write_json_atomic(path: Path, data: Mapping[str, object]) -> bool:
    """كتابة ذرية: 'path.tmp' ثم flush وfsync ثم os.replace فوق الهدف. يعيد False عند الفشل.

    الفشل (قرص ممتلئ أو صلاحيات) يُسجَّل ولا يرفع استثناءً، ويُحذف الملف المؤقت.
    """
    tmp_path = path.with_name(path.name + _TMP_SUFFIX)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=_JSON_INDENT) + "\n"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())  # يضمن وصول البايتات للقرص قبل الاستبدال
        os.replace(tmp_path, path)  # عملية ذرية على نفس الوحدة
    except (OSError, ValueError, TypeError) as exc:
        _LOG.warning("could not write %s: %s", path.name, exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


class SettingsStore(QObject):
    """المصدر الوحيد لحقيقة الإعدادات أثناء التشغيل.

    الخاصية العامة last_corrupt_backup: اسم النسخة المعزولة إن كان آخر load() قد وجد ملفًا
    تالفًا، وإلا None؛ يقرؤها المتحكم ليعرض رسالة واحدة في شريط النظام.
    """

    changed = Signal(str)  # المفتاح الذي تغيّر فعليًا
    reloaded = Signal()  # بعد load() أو أي استبدال كامل للحالة

    def __init__(self, path: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path: Path = path if path is not None else settings_path()
        self._settings: Settings = default_settings()
        self.last_corrupt_backup: str | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)  # يُعاد تشغيله عند كل تغيير فيدمج الكتابات
        self._save_timer.setInterval(SETTINGS_SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._on_save_timeout)

    # ------------------------------------------------------------------ القراءة
    def snapshot(self) -> Settings:
        """نسخة مستقلة من الإعدادات الحالية؛ تعديلها لا يمس المخزن."""
        return replace(self._settings, selected_screens=list(self._settings.selected_screens))

    def get(self, key: str) -> object:
        """قيمة مفتاح واحد (القوائم تُنسخ).

        Raises:
            KeyError: إذا لم يكن المفتاح ضمن المخطط (خطأ برمجي).
        """
        if key not in FIELD_SPECS:
            raise KeyError(key)
        value = getattr(self._settings, key)
        return list(value) if isinstance(value, list) else value

    # ------------------------------------------------------------------ التحميل
    def load(self) -> None:
        """يحمّل الإعدادات من القرص؛ الملف الناقص أو التالف يعطي الافتراضيات دون رفع خطأ.

        الملف التالف يُعاد تسميته إلى settings.corrupt-<الوقت>.json ويُسجَّل تحذير.
        """
        self._save_timer.stop()  # لا نريد حفظًا مؤجَّلًا يكتب فوق ما حمّلناه للتو
        self.last_corrupt_backup = None
        settings = default_settings()
        try:
            raw = _read_json_object(self._path)
        except FileNotFoundError:
            _LOG.info("settings file not found; using defaults")
        except OSError as exc:
            _LOG.warning("cannot read settings file: %s; using defaults", exc)
        except (ValueError, RecursionError) as exc:
            _LOG.warning("settings file is corrupt: %s", exc)
            self._quarantine_corrupt_file()
        else:
            settings = validate_and_coerce(migrate(raw))
        self._settings = settings
        self.reloaded.emit()

    def _quarantine_corrupt_file(self) -> None:
        """يعيد تسمية الملف التالف بختم زمني (مع لاحقة رقمية عند تكرار الاسم في الثانية نفسها)."""
        stamp = datetime.now().strftime(_CORRUPT_TIMESTAMP_FORMAT)
        base = f"{self._path.stem}.corrupt-{stamp}"
        target = self._path.with_name(base + self._path.suffix)
        counter = 1
        while target.exists():
            target = self._path.with_name(f"{base}-{counter}{self._path.suffix}")
            counter += 1
        try:
            self._path.rename(target)
        except OSError as exc:
            _LOG.warning("could not move the corrupt settings file: %s", exc)
            return
        self.last_corrupt_backup = target.name
        _LOG.warning("corrupt settings file moved to %s", target.name)

    # ------------------------------------------------------------------ الكتابة
    def set(self, key: str, value: object) -> None:  # noqa: A003  الاسم مفروض بالعقد
        """يكتب مفتاحًا واحدًا بعد التحقق والقص؛ القيمة غير الصالحة تعود للافتراضي."""
        self.update({key: value})

    def update(self, values: Mapping[str, object]) -> None:
        """كتابة دفعة: تُطبَّق كلها أولًا ثم تُصدَر 'changed' لكل مفتاح تغيّر فعليًا بالترتيب.

        كتابة أي حقل مرتبط بإعداد مسبق تجعل preset يساوي 'custom' إلا إذا كانت 'preset'
        ضمن الدفعة نفسها.
        """
        self._finish(self._apply(values, auto_custom=True))

    def apply_preset(self, name: str) -> None:
        """يكتب حقول الإعداد المسبق دون قلب preset إلى custom؛ 'custom' يغيّر الاسم فقط."""
        if name == "custom":
            values: dict[str, object] = {"preset": "custom"}
        elif name in PRESETS:
            values = {"preset": name, **PRESETS[name]}
        else:
            _LOG.warning("unknown preset: %r", name)
            return
        self._finish(self._apply(values, auto_custom=False))

    def apply_quality(self, name: str) -> None:
        """يكتب fps_cap وantialiasing من ملف الجودة؛ معامل الكثافة تطبّقه طبقة العرض ولا يُخزَّن."""
        profile = QUALITY_PROFILES.get(name)
        if profile is None:
            _LOG.warning("unknown quality profile: %r", name)
            return
        values: dict[str, object] = {
            "quality": name,
            "fps_cap": profile.fps_cap,
            "antialiasing": profile.antialiasing,
        }
        self._finish(self._apply(values, auto_custom=False))

    def reset_to_defaults(self, keep: Iterable[str] = _DEFAULT_KEEP) -> None:
        """يعيد كل الإعدادات لافتراضياتها عدا المفاتيح في keep (الحالة الافتراضية: أول تشغيل والنافذة)."""
        keep_set = set(keep)
        values = {
            key: value
            for key, value in settings_to_dict(default_settings()).items()
            if key not in keep_set
        }
        self._finish(self._apply(values, auto_custom=False))

    @staticmethod
    def _coerce_one(key: str, raw: object) -> object:
        """قيمة المفتاح بعد التحقق: تستعمل نفس مسار validate_and_coerce (افتراضي عند الخطأ)."""
        return getattr(validate_and_coerce({key: raw}), key)

    def _apply(self, values: Mapping[str, object], *, auto_custom: bool) -> list[str]:
        """يطبّق القيم على الحالة الحية ويعيد المفاتيح التي تغيّرت فعليًا، دون إصدار إشارات."""
        changed: list[str] = []
        for key, raw in values.items():
            if key not in FIELD_SPECS:
                _LOG.warning("ignoring unknown settings key: %r", key)
                continue
            if key in _MANAGED_KEYS:
                continue
            new_value = self._coerce_one(key, raw)
            if new_value != getattr(self._settings, key):
                setattr(self._settings, key, new_value)
                changed.append(key)
        flips_preset = (
            auto_custom
            and "preset" not in values
            and self._settings.preset != "custom"
            and any(key in _PRESET_FIELD_KEYS for key in changed)
        )
        if flips_preset:
            self._settings.preset = "custom"
            changed.append("preset")
        return changed

    def _finish(self, changed: list[str]) -> None:
        """يجدول الحفظ ثم يصدر الإشارات (الحالة اكتملت قبل أول إشارة، فالمستمع يرى كل الدفعة)."""
        if not changed:
            return
        self._save_timer.start()
        for key in changed:
            self.changed.emit(key)

    # ------------------------------------------------------------------ الحفظ
    def _on_save_timeout(self) -> None:
        self.save_now()

    def save_now(self) -> bool:
        """حفظ فوري ذري؛ يعيد False عند الفشل مع بقاء الإعدادات في الذاكرة (وتُعاد المحاولة لاحقًا)."""
        self._save_timer.stop()
        return _write_json_atomic(self._path, settings_to_dict(self._settings))

    def export_to(self, path: Path) -> bool:
        """يصدّر الإعدادات الحالية كاملة إلى ملف JSON؛ False عند الفشل."""
        return _write_json_atomic(path, settings_to_dict(self._settings))

    def import_from(self, path: Path) -> bool:
        """يستورد إعدادات من ملف JSON (مع الترحيل والتحقق)؛ False إذا تعذّرت القراءة.

        لا يستورد الحقول الخاصة بالجهاز (النسخة، أول تشغيل، هندسة النافذة).
        """
        try:
            raw = _read_json_object(path)
        except (OSError, ValueError, RecursionError) as exc:
            _LOG.warning("cannot import settings from %s: %s", path.name, exc)
            return False
        imported = settings_to_dict(validate_and_coerce(migrate(raw)))
        self.update({k: v for k, v in imported.items() if k not in _IMPORT_SKIP_KEYS})
        return True