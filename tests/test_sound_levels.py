"""tests/test_sound_levels.py: منزلقا مستوى الرياح والرعد: المخطط والنصوص والصفحة والمتحكم."""

from __future__ import annotations

import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from raindesk.app.controller import AppController
from raindesk.config.schema import FIELD_SPECS, Settings, settings_to_dict, validate_and_coerce
from raindesk.config.store import SettingsStore
from raindesk.i18n import strings_ar, strings_en
from raindesk.i18n.translator import Translator
from raindesk.ui.pages.effects_page import EffectsPage

KEYS = ("sound_wind_volume", "sound_thunder_volume")


# ----------------------------------------------------------------------------- المخطط
def test_defaults_are_the_original_level_and_in_spec() -> None:
    settings = Settings()
    for key in KEYS:
        spec = FIELD_SPECS[key]
        assert getattr(settings, key) == spec.default == 0.5
        assert (spec.minimum, spec.maximum) == (0.0, 1.0)


def test_values_are_clamped_and_bad_values_fall_back() -> None:
    result = validate_and_coerce({"sound_wind_volume": 7, "sound_thunder_volume": -3})
    assert (result.sound_wind_volume, result.sound_thunder_volume) == (1.0, 0.0)
    bad = validate_and_coerce({"sound_wind_volume": "loud", "sound_thunder_volume": None})
    assert (bad.sound_wind_volume, bad.sound_thunder_volume) == (0.5, 0.5)


def test_round_trip_keeps_the_levels() -> None:
    settings = validate_and_coerce({"sound_wind_volume": 0.8, "sound_thunder_volume": 0.15})
    again = validate_and_coerce(settings_to_dict(settings))
    assert (again.sound_wind_volume, again.sound_thunder_volume) == (0.8, 0.15)


def test_old_settings_files_without_the_keys_still_load() -> None:
    result = validate_and_coerce({"sound_enabled": True, "sound_volume": 0.4})
    assert result.sound_wind_volume == result.sound_thunder_volume == 0.5


# ----------------------------------------------------------------------------- النصوص
@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("table", [strings_en.STRINGS, strings_ar.STRINGS])
def test_label_and_tip_exist_in_both_languages(table: dict[str, str], key: str) -> None:
    assert table[f"setting.{key}.label"].strip()
    assert table[f"setting.{key}.tip"].strip()


# ----------------------------------------------------------------------------- الصفحة
@pytest.fixture
def page(qapp: object, tmp_path: Path) -> Iterator[tuple[EffectsPage, SettingsStore]]:
    store = SettingsStore(path=tmp_path / "s.json")
    widget = EffectsPage(store, Translator())
    widget.show()
    yield widget, store
    widget.close()
    store.save_now()  # يوقف مؤقّت الحفظ المؤجَّل


def test_sliders_follow_the_sound_and_their_own_switch(
    page: tuple[EffectsPage, SettingsStore],
) -> None:
    widget, store = page
    wind, thunder = widget._wind_volume, widget._thunder_volume
    assert wind is not None and thunder is not None
    assert not wind.isEnabled() and not thunder.isEnabled()  # الصوت مطفأ
    store.set("sound_enabled", True)
    assert wind.isEnabled() and thunder.isEnabled()
    store.set("sound_wind", False)
    assert not wind.isEnabled() and thunder.isEnabled()  # مفتاح الرياح مطفأ فمنزلقها معطّل
    store.set("sound_thunder", False)
    assert not thunder.isEnabled()
    store.set("sound_wind", True)
    assert wind.isEnabled()
    widget.set_sound_available(False)  # لا جهاز صوت: كل شيء معطّل
    assert not wind.isEnabled() and not thunder.isEnabled()


def test_moving_a_slider_writes_the_setting_and_back(
    page: tuple[EffectsPage, SettingsStore],
) -> None:
    widget, store = page
    store.set("sound_enabled", True)
    assert widget._wind_volume is not None and widget._thunder_volume is not None
    widget._wind_volume.set_value(0.9, emit=True)  # type: ignore[attr-defined]
    assert store.get("sound_wind_volume") == pytest.approx(0.9)
    store.set("sound_thunder_volume", 0.2)  # من المخزن إلى المنزلق (مثلًا بعد استيراد إعدادات)
    assert widget._thunder_volume.value() == pytest.approx(0.2)  # type: ignore[attr-defined]


# ----------------------------------------------------------------------------- المتحكم
class _Audio:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any) -> None:
            self.calls.append((name, args[0] if args else None))

        return record

    is_available = True


def _controller(values: dict[str, object]) -> tuple[AppController, _Audio]:
    controller = AppController.__new__(AppController)
    audio = _Audio()
    controller._store = types.SimpleNamespace(get=lambda key: values.get(key))  # type: ignore[assignment]
    controller._audio = audio  # type: ignore[assignment]
    controller._manager = types.SimpleNamespace(paused=False)  # type: ignore[assignment]
    controller._tray = _Audio()  # type: ignore[assignment]
    return controller, audio


def test_controller_pushes_levels_to_the_player() -> None:
    values = {
        "sound_enabled": True,
        "sound_volume": 0.3,
        "sound_wind_volume": 0.8,
        "sound_thunder_volume": 0.1,
        "sound_follows_intensity": True,
        "sound_wind": True,
        "sound_thunder": True,
    }
    controller, audio = _controller(values)
    controller._apply_sound_settings()
    assert ("set_wind_volume", 0.8) in audio.calls
    assert ("set_thunder_volume", 0.1) in audio.calls


def test_controller_falls_back_to_the_original_level_on_bad_values() -> None:
    controller, audio = _controller({"sound_wind_volume": "x", "sound_thunder_volume": None})
    controller._apply_sound_settings()
    assert ("set_wind_volume", 0.5) in audio.calls and ("set_thunder_volume", 0.5) in audio.calls


@pytest.mark.parametrize("key", KEYS)
def test_changing_a_level_key_reapplies_the_sound_settings(key: str) -> None:
    controller, audio = _controller({key: 0.7})
    controller._on_setting_changed(key)
    assert audio.calls  # وصل التغيير إلى المشغّل
