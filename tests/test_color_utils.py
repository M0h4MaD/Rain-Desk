"""tests/test_color_utils.py: اختبارات raindesk.core.color_utils (دوال نقية بلا Qt)."""

from __future__ import annotations

import pytest

from raindesk.core.color_utils import (
    contrast_ratio,
    hex_to_rgb,
    is_valid_hex,
    relative_luminance,
    rgb_to_hex,
)

_TOLERANCE = 1e-9  # الحد المطلوب في المواصفة


@pytest.mark.parametrize("value", ["#000000", "#FFFFFF", "#A9C7E8", "#0B1A2B"])
def test_hex_round_trip(value: str) -> None:
    assert rgb_to_hex(hex_to_rgb(value)) == value


def test_lowercase_hex_is_normalized_to_uppercase() -> None:
    assert hex_to_rgb("#a9c7e8") == (169, 199, 232)
    assert rgb_to_hex((169, 199, 232)) == "#A9C7E8"


@pytest.mark.parametrize(
    "value", ["", "#FFF", "FFFFFF", "#GGGGGG", "#12345", "#1234567", "#ABCDEF\n", " #ABCDEF"]
)
def test_invalid_hex_rejected(value: str) -> None:
    assert not is_valid_hex(value)
    with pytest.raises(ValueError):
        hex_to_rgb(value)


def test_non_string_is_not_valid_hex() -> None:
    assert not is_valid_hex(123)  # type: ignore[arg-type]


@pytest.mark.parametrize("rgb", [(256, 0, 0), (0, -1, 0), (0, 0, 1000)])
def test_rgb_to_hex_rejects_out_of_range(rgb: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        rgb_to_hex(rgb)


def test_relative_luminance_extremes() -> None:
    assert relative_luminance((0, 0, 0)) == 0.0
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0, abs=_TOLERANCE)


def test_contrast_ratio_black_white_is_21() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=_TOLERANCE)


def test_contrast_ratio_is_symmetric_and_identity_is_one() -> None:
    assert contrast_ratio("#123456", "#FEDCBA") == pytest.approx(
        contrast_ratio("#FEDCBA", "#123456"), abs=_TOLERANCE
    )
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0, abs=_TOLERANCE)


def test_contrast_ratio_matches_wcag_aa_boundary() -> None:
    # #767676 هو أفتح رمادي يجتاز AA (4.5) على الأبيض؛ #777777 أفتح منه بدرجة ويفشل.
    assert contrast_ratio("#767676", "#FFFFFF") >= 4.5
    assert contrast_ratio("#777777", "#FFFFFF") < 4.5