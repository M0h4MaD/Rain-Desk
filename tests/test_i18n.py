"""tests/test_i18n.py: تطابق ملفات النصوص وسلوك Translator الأساسي."""

from __future__ import annotations

from string import Formatter

import pytest

from raindesk.i18n.strings_ar import STRINGS as AR
from raindesk.i18n.strings_en import STRINGS as EN
from raindesk.i18n.translator import Translator


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def test_strings_have_identical_key_sets() -> None:
    assert set(EN) == set(AR)


def test_strings_have_identical_placeholders() -> None:
    for key in EN:
        assert _placeholders(EN[key]) == _placeholders(AR[key]), key


def test_no_empty_strings() -> None:
    for table in (EN, AR):
        for key, text in table.items():
            assert text.strip(), key


@pytest.mark.usefixtures("qapp")
def test_translator_language_switch_and_signal() -> None:
    translator = Translator()
    translator.set_language("en")
    seen: list[str] = []
    translator.language_changed.connect(lambda code: seen.append(code))
    translator.set_language("en")  # لا تغيير فعلي
    assert seen == []
    translator.set_language("ar")
    assert seen == ["ar"] and translator.language == "ar" and translator.is_rtl
    assert translator.tr("msg.first_run_title") == AR["msg.first_run_title"]
    translator.set_language("en")
    assert not translator.is_rtl


@pytest.mark.usefixtures("qapp")
def test_translator_fallback_and_formatting() -> None:
    translator = Translator()
    translator.set_language("en")
    assert translator.tr("no.such.key") == "no.such.key"
    assert "x.json" in translator.tr("msg.settings_corrupt", name="x.json")
    assert "{name}" in translator.tr("msg.settings_corrupt", other=1)  # متغير ناقص: بلا استثناء
    assert [code for code, _ in translator.available_languages()] == ["auto", "ar", "en"]