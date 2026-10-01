"""tests/conftest.py

الغرض: إعدادات pytest المشتركة: بيئة Qt بلا شاشة، وfixtures، وعلامة 'windows_only'.
ملاحظات: QT_QPA_PLATFORM يجب ضبطه قبل أول استيراد لـ PySide6، لذلك هو أول سطر تنفيذي هنا.
"""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # منصة Qt بلا نافذة حقيقية (تعمل بلا شاشة)

import sys
from pathlib import Path

import numpy as np
import pytest

# يضمن أن 'import raindesk' يعمل عند تشغيل 'pytest' مباشرة (وليس 'python -m pytest' فقط).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_RNG_SEED = 12345  # بذرة ثابتة: اختبارات حتمية قابلة للتكرار


def pytest_configure(config: pytest.Config) -> None:
    """يسجّل العلامة المخصصة لتجنّب تحذير 'unknown marker'."""
    config.addinivalue_line(
        "markers", "windows_only: اختبارات تلمس winreg أو Win32 وتُتخطّى خارج Windows"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """يتخطى اختبارات 'windows_only' على الأنظمة الأخرى."""
    if sys.platform == "win32":
        return
    skip_marker = pytest.mark.skip(reason="requires Windows")
    for item in items:
        if "windows_only" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture
def rng() -> np.random.Generator:
    """مولّد أعداد عشوائية ببذرة ثابتة."""
    return np.random.default_rng(_RNG_SEED)


@pytest.fixture
def tmp_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """يوجّه APPDATA وLOCALAPPDATA إلى مجلد مؤقت حتى لا تلمس الاختبارات بيانات المستخدم."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    return tmp_path


@pytest.fixture(scope="session")
def qapp() -> object:
    """QApplication واحد لكل جلسة الاختبار (Qt يسمح بنسخة واحدة فقط لكل عملية)."""
    from PySide6.QtWidgets import QApplication  # استيراد كسول: الاختبارات النقية لا تحتاج Qt

    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])