"""tests/test_theme_contrast.py: تباين ألوان السمة (WCAG 2.1 AA) وسلامة ThemeManager."""

from __future__ import annotations

import pytest

from raindesk.core.color_utils import contrast_ratio, is_valid_hex
from raindesk.ui.theme import TOKENS_DARK, TOKENS_LIGHT, ThemeManager

_MIN_TEXT_CONTRAST = 4.5  # AA للنص العادي
_MIN_UI_CONTRAST = 3.0  # WCAG 1.4.11 لمكوّنات الواجهة (مثل حلقة التركيز)
_REQUIRED_PAIRS = [
    ("text", "bg"), ("text", "surface"), ("text", "surface_alt"),
    ("text_muted", "bg"), ("text_muted", "surface"), ("text_muted", "surface_alt"),
    ("accent_text", "accent"), ("accent_text", "accent_hover"),
    ("danger", "surface"), ("success", "surface"),
]
_THEMES = {"dark": TOKENS_DARK, "light": TOKENS_LIGHT}


def test_both_themes_have_identical_token_names_and_valid_colors() -> None:
    assert set(TOKENS_DARK) == set(TOKENS_LIGHT)
    for tokens in _THEMES.values():
        assert all(is_valid_hex(value) for value in tokens.values())


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize(("foreground", "background"), _REQUIRED_PAIRS)
def test_required_pairs_meet_wcag_aa(theme_name: str, foreground: str, background: str) -> None:
    tokens = _THEMES[theme_name]
    ratio = contrast_ratio(tokens[foreground], tokens[background])
    assert ratio >= _MIN_TEXT_CONTRAST, f"{theme_name}: {foreground} on {background} = {ratio:.2f}"


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("background", ["bg", "surface"])
def test_focus_ring_is_visible_against_backgrounds(theme_name: str, background: str) -> None:
    tokens = _THEMES[theme_name]
    assert contrast_ratio(tokens["focus_ring"], tokens[background]) >= _MIN_UI_CONTRAST


@pytest.mark.usefixtures("qapp")
def test_theme_manager_resolves_modes_and_builds_stylesheet() -> None:
    manager = ThemeManager()
    seen: list[str] = []
    manager.theme_changed.connect(lambda mode: seen.append(mode))
    manager.apply("dark")
    assert manager.effective_mode == "dark" and manager.tokens == TOKENS_DARK
    manager.apply("light")
    assert manager.effective_mode == "light" and manager.tokens == TOKENS_LIGHT
    # آخر تغيّر فعلي هو light؛ قد لا تُصدَر 'dark' إن كان النظام داكنًا أصلًا.
    assert seen and seen[-1] == "light"
    sheet = manager.stylesheet()
    assert TOKENS_LIGHT["accent"] in sheet and "${" not in sheet
    manager.apply("nonsense")  # قيمة مجهولة: تُعامل كنظام دون استثناء
    assert manager.effective_mode in ("light", "dark")