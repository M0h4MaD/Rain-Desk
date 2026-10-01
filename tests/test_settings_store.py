"""tests/test_settings_store.py: اختبارات SettingsStore (تحتاج QApplication عبر qapp)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtTest import QTest

import raindesk.config.store as store_module
from raindesk.config.schema import default_settings
from raindesk.config.store import SettingsStore

pytestmark = pytest.mark.usefixtures("qapp")

_FAST_DEBOUNCE_MS = 30  # نقصّر مهلة الحفظ المؤجَّل في الاختبارات فقط
_WAIT_MS = 250  # أطول بكثير من المهلة المقصّرة


def _make(tmp_path: Path) -> SettingsStore:
    return SettingsStore(path=tmp_path / "settings.json")


def _record(store: SettingsStore) -> list[str]:
    emitted: list[str] = []
    store.changed.connect(lambda key: emitted.append(key))
    return emitted


def test_atomic_write_leaves_no_tmp_file(tmp_path: Path) -> None:
    store = _make(tmp_path)
    store.set("intensity", 0.9)
    assert store.save_now() is True
    target = tmp_path / "settings.json"
    assert list(tmp_path.glob("*.tmp")) == []
    assert json.loads(target.read_text(encoding="utf-8"))["intensity"] == 0.9


def test_failed_save_keeps_memory_and_cleans_tmp(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    target.mkdir()  # مجلد بدل الملف: os.replace سيفشل دائمًا
    store = SettingsStore(path=target)
    store.set("intensity", 0.9)
    assert store.save_now() is False
    assert store.get("intensity") == 0.9
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", ""])
def test_corrupt_file_is_renamed_and_defaults_loaded(tmp_path: Path, content: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    store = SettingsStore(path=path)
    store.load()
    backups = list(tmp_path.glob("settings.corrupt-*.json"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == content
    assert not path.exists()
    assert store.last_corrupt_backup == backups[0].name
    assert store.snapshot() == default_settings()


def test_missing_file_gives_defaults_without_backup(tmp_path: Path) -> None:
    store = _make(tmp_path)
    reloaded: list[int] = []
    store.reloaded.connect(lambda: reloaded.append(1))
    store.load()
    assert store.snapshot() == default_settings()
    assert store.last_corrupt_backup is None
    assert reloaded == [1]


def test_load_coerces_values_and_drops_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"intensity": 5, "bogus": 1}), encoding="utf-8")
    store = SettingsStore(path=path)
    store.load()
    assert store.get("intensity") == 1.0
    assert store.last_corrupt_backup is None


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    first = _make(tmp_path)
    first.update({"intensity": 0.8, "drop_color": "#112233", "selected_screens": ["A"]})
    assert first.save_now()
    second = _make(tmp_path)
    second.load()
    assert second.snapshot() == first.snapshot()


def test_rapid_sets_produce_a_single_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_module, "SETTINGS_SAVE_DEBOUNCE_MS", _FAST_DEBOUNCE_MS)
    calls: list[int] = []
    original = SettingsStore.save_now

    def counting(self: SettingsStore) -> bool:
        calls.append(1)
        return original(self)

    monkeypatch.setattr(SettingsStore, "save_now", counting)
    store = _make(tmp_path)
    for i in range(20):
        store.set("intensity", 0.1 + i * 0.01)  # 20 قيمة مختلفة كلها تغيير فعلي
    QTest.qWait(_WAIT_MS)
    assert len(calls) == 1
    assert (tmp_path / "settings.json").exists()


def test_changed_is_emitted_only_on_effective_change(tmp_path: Path) -> None:
    store = _make(tmp_path)
    emitted = _record(store)
    store.set("intensity", 0.5)  # يساوي الافتراضي: لا تغيير
    assert emitted == []
    store.set("intensity", 0.7)
    store.set("intensity", 0.7)
    assert emitted == ["intensity"]
    store.set("speed", 99)  # يُقصّ إلى الحد الأعلى 2.5
    assert store.get("speed") == 2.5
    store.set("speed", 2.5)
    assert emitted == ["intensity", "speed"]


def test_invalid_value_falls_back_to_default(tmp_path: Path) -> None:
    store = _make(tmp_path)
    store.set("intensity", 0.9)
    store.set("intensity", "abc")
    assert store.get("intensity") == 0.5


def test_unknown_key_is_ignored_and_get_raises(tmp_path: Path) -> None:
    store = _make(tmp_path)
    emitted = _record(store)
    store.set("bogus", 1)
    assert emitted == []
    with pytest.raises(KeyError):
        store.get("bogus")


def test_update_applies_all_before_emitting(tmp_path: Path) -> None:
    store = _make(tmp_path)
    seen: list[object] = []
    store.changed.connect(lambda key: seen.append(store.get("speed")))
    store.update({"intensity": 0.2, "speed": 2.0})
    assert seen == [2.0, 2.0]  # المستمع الأول يرى القيمتين معًا


def test_apply_preset_writes_fields_and_slider_flips_to_custom(tmp_path: Path) -> None:
    store = _make(tmp_path)
    emitted = _record(store)
    store.apply_preset("heavy")
    snap = store.snapshot()
    assert snap.preset == "heavy"
    assert (snap.intensity, snap.speed, snap.wind_angle_deg) == (0.8, 1.2, 18.0)
    assert "preset" in emitted and "intensity" in emitted
    store.set("intensity", 0.3)
    assert store.get("preset") == "custom"
    assert emitted[-2:] == ["intensity", "preset"]


def test_explicit_preset_in_batch_is_not_flipped(tmp_path: Path) -> None:
    store = _make(tmp_path)
    store.update({"preset": "storm", "intensity": 1.0})
    assert store.get("preset") == "storm"


def test_unknown_preset_and_quality_change_nothing(tmp_path: Path) -> None:
    store = _make(tmp_path)
    emitted = _record(store)
    store.apply_preset("nope")
    store.apply_quality("nope")
    assert emitted == []


def test_apply_quality_writes_fps_and_antialiasing(tmp_path: Path) -> None:
    store = _make(tmp_path)
    store.apply_quality("low")
    assert (store.get("quality"), store.get("fps_cap"), store.get("antialiasing")) == (
        "low", 20, False,
    )


def test_reset_to_defaults_keeps_requested_keys(tmp_path: Path) -> None:
    store = _make(tmp_path)
    store.update({"intensity": 0.9, "first_run_completed": True, "window_geometry": "abc"})
    store.reset_to_defaults()
    assert store.get("intensity") == 0.5
    assert store.get("first_run_completed") is True
    assert store.get("window_geometry") == "abc"


def test_snapshot_is_an_independent_copy(tmp_path: Path) -> None:
    store = _make(tmp_path)
    snap = store.snapshot()
    snap.intensity = 0.99
    snap.selected_screens.append("x")
    assert store.get("intensity") == 0.5
    assert store.get("selected_screens") == []


def test_export_then_import_restores_settings_but_not_device_fields(tmp_path: Path) -> None:
    store = _make(tmp_path)
    store.update({"intensity": 0.9, "first_run_completed": True})
    export_path = tmp_path / "export.json"
    assert store.export_to(export_path)
    store.update({"intensity": 0.1, "first_run_completed": False})
    assert store.import_from(export_path)
    assert store.get("intensity") == 0.9
    assert store.get("first_run_completed") is False  # لم يُستورد


def test_import_of_bad_file_returns_false(tmp_path: Path) -> None:
    store = _make(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("[1]", encoding="utf-8")
    assert store.import_from(bad) is False
    assert store.import_from(tmp_path / "missing.json") is False