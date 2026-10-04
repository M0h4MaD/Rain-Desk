"""tests/test_autostart.py: اختبارات التشغيل التلقائي (الكتابة الفعلية في السجل windows_only)."""

from __future__ import annotations

import sys
import uuid

import pytest

from raindesk.platform_win import autostart

windows_only = pytest.mark.windows_only


def test_frozen_command_is_quoted_and_minimized(monkeypatch: pytest.MonkeyPatch) -> None:
    path = r"C:\Program Files\RainDesk\RainDesk.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", path)
    assert autostart.build_launch_command() == f'"{path}" --minimized'


def test_dev_command_quotes_both_paths_and_ends_with_minimized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = autostart.build_launch_command()
    assert command.endswith(" --minimized")
    assert command.startswith('"') and command.count('"') == 4  # المفسّر والسكربت مقتبسان
    assert "main.py" in command


@windows_only
def test_enable_then_disable_round_trip_in_the_registry() -> None:
    name = f"RainDeskTest-{uuid.uuid4().hex}"  # اسم فريد كي لا نلمس إدخال التطبيق الحقيقي
    try:
        assert autostart.is_enabled(name) is False
        assert autostart.set_enabled(True, name) is True
        assert autostart.is_enabled(name) is True
        command = autostart.get_command(name)
        assert command is not None and "--minimized" in command
        assert autostart.set_enabled(False, name) is True
        assert autostart.is_enabled(name) is False
    finally:
        autostart.set_enabled(False, name)  # تنظيف دائم حتى عند فشل أي تأكيد


@windows_only
def test_disabling_a_missing_entry_counts_as_success() -> None:
    name = f"RainDeskTest-{uuid.uuid4().hex}"
    assert autostart.set_enabled(False, name) is True


def test_non_windows_is_neutral() -> None:
    if sys.platform == "win32":
        pytest.skip("only meaningful off Windows")
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(True) is False