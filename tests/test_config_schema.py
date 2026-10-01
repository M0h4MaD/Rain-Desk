"""tests/test_config_schema.py: اختبارات raindesk.config.schema (بلا Qt)."""

from __future__ import annotations

from dataclasses import fields

import pytest

from raindesk.config.schema import (
    FIELD_SPECS,
    PRESETS,
    QUALITY_PROFILES,
    RANDOMIZE_RANGES,
    SETTINGS_SCHEMA_VERSION,
    FieldSpec,
    Settings,
    default_settings,
    migrate,
    settings_to_dict,
    validate_and_coerce,
)


def _bounds(spec: FieldSpec) -> tuple[float, float]:
    assert spec.minimum is not None and spec.maximum is not None
    return spec.minimum, spec.maximum


def test_default_settings_validates_unchanged() -> None:
    defaults = default_settings()
    assert validate_and_coerce(settings_to_dict(defaults)) == defaults


def test_settings_fields_match_specs_and_defaults() -> None:
    assert {f.name for f in fields(Settings)} == set(FIELD_SPECS)
    defaults = settings_to_dict(Settings())
    for key, spec in FIELD_SPECS.items():
        assert defaults[key] == spec.default, key


def test_every_default_lies_inside_its_own_range_or_choices() -> None:
    for key, spec in FIELD_SPECS.items():
        if spec.kind in ("int", "float"):
            low, high = _bounds(spec)
            assert isinstance(spec.default, (int, float))
            assert low <= spec.default <= high, key
        elif spec.kind == "choice":
            assert spec.choices is not None and spec.default in spec.choices, key


def test_clamping() -> None:
    result = validate_and_coerce(
        {
            "intensity": 7, "speed": -3, "wind_angle_deg": 999, "depth_layers": 100,
            "edge_streams_count": 0, "rng_seed": -5,
        }
    )
    assert result.intensity == 1.0
    assert result.speed == 0.25
    assert result.wind_angle_deg == 60.0
    assert result.depth_layers == 8
    assert result.edge_streams_count == 1
    assert result.rng_seed == -1


def test_coercion() -> None:
    result = validate_and_coerce(
        {
            "intensity": "0.7", "enabled": "false", "language": "AR", "log_level": "debug",
            "drop_color": "#a9c7e8", "depth_layers": 4.6, "fps_cap": 33.0,
        }
    )
    assert result.intensity == 0.7
    assert result.enabled is False
    assert result.language == "ar"
    assert result.log_level == "DEBUG"
    assert result.drop_color == "#A9C7E8"
    assert result.depth_layers == 5
    assert result.fps_cap == 35  # يُقرَّب لأقرب مضاعف لـ 5


@pytest.mark.parametrize(("raw_fps", "expected"), [(2, 10), (1000, 60), (12, 10), (58, 60)])
def test_fps_cap_snaps_to_multiples_of_five_within_range(raw_fps: int, expected: int) -> None:
    assert validate_and_coerce({"fps_cap": raw_fps}).fps_cap == expected


def test_invalid_values_fall_back_to_defaults() -> None:
    defaults = default_settings()
    result = validate_and_coerce(
        {
            "intensity": "abc", "speed": float("nan"), "drop_opacity": True,
            "enabled": "maybe", "theme": "neon", "drop_color": "red", "depth_layers": None,
            "sound_volume": float("inf"), "parallax_strength": 10**400,
        }
    )
    assert result == defaults


def test_unknown_keys_are_dropped() -> None:
    result = validate_and_coerce({"bogus": 1, "intensity": 0.3})
    assert not hasattr(result, "bogus")
    assert "bogus" not in settings_to_dict(result)
    assert result.intensity == 0.3


def test_non_mapping_input_gives_defaults() -> None:
    assert validate_and_coerce([1, 2]) == default_settings()  # type: ignore[arg-type]


def test_str_list_filters_non_strings() -> None:
    assert validate_and_coerce({"selected_screens": ["a", 3, "b"]}).selected_screens == ["a", "b"]
    assert validate_and_coerce({"selected_screens": "a"}).selected_screens == []


def test_default_instances_do_not_share_lists() -> None:
    first = default_settings()
    first.selected_screens.append("x")
    assert default_settings().selected_screens == []


def test_round_trip_of_modified_settings() -> None:
    modified = default_settings()
    modified.intensity = 0.9
    modified.drop_color = "#112233"
    modified.selected_screens = ["A", "B"]
    assert validate_and_coerce(settings_to_dict(modified)) == modified


def test_migrate_upgrades_synthetic_v0() -> None:
    raw: dict[str, object] = {
        "schema_version": 0, "fps": 45, "rain_color": "#112233", "intensity": 0.4,
    }
    migrated = migrate(raw)
    assert migrated["schema_version"] == SETTINGS_SCHEMA_VERSION
    assert migrated["fps_cap"] == 45 and "fps" not in migrated
    assert migrated["drop_color"] == "#112233" and "rain_color" not in migrated
    assert migrated["intensity"] == 0.4
    assert raw["schema_version"] == 0 and "fps" in raw  # المُدخل لم يُعدَّل (دالة نقية)
    assert validate_and_coerce(migrated).fps_cap == 45


def test_migrate_keeps_existing_new_key_over_old_one() -> None:
    migrated = migrate({"schema_version": 0, "fps": 45, "fps_cap": 25})
    assert migrated["fps_cap"] == 25


@pytest.mark.parametrize(
    "raw",
    [{"schema_version": 1, "x": 1}, {"intensity": 0.2}, {"schema_version": 99}],
)
def test_migrate_leaves_current_missing_and_future_versions_untouched(
    raw: dict[str, object],
) -> None:
    migrated = migrate(raw)
    assert migrated == raw
    assert migrated is not raw


def test_presets_are_consistent_with_specs() -> None:
    assert set(PRESETS) | {"custom"} == set(FIELD_SPECS["preset"].choices or ())
    for values in PRESETS.values():
        for key, value in values.items():
            low, high = _bounds(FIELD_SPECS[key])
            assert low <= value <= high, key


def test_quality_profiles_are_consistent_with_specs() -> None:
    assert set(QUALITY_PROFILES) == set(FIELD_SPECS["quality"].choices or ())
    low, high = _bounds(FIELD_SPECS["fps_cap"])
    for profile in QUALITY_PROFILES.values():
        assert low <= profile.fps_cap <= high
        assert profile.fps_cap % 5 == 0
        assert profile.drop_multiplier > 0


def test_randomize_ranges_are_valid() -> None:
    for key, (lo, hi) in RANDOMIZE_RANGES.items():
        low, high = _bounds(FIELD_SPECS[key])
        assert low <= lo < hi <= high, key