"""The two languages, and which one a run opens in.

`pick_lang` has a counterpart in lang.bat and lang.sh, and the three have to
agree - the launcher prints its messages before the window exists, so a
disagreement shows up as a banner in one language above a window in the other.
The order of the sources is the part worth pinning down.
"""

from __future__ import annotations

import pytest

from hfdl import i18n


def test_a_text_carries_both_wordings():
    text = i18n.Text("Files", "Файлы")
    assert text("en") == "Files"
    assert text("ru") == "Файлы"


def test_an_unknown_language_reads_as_english():
    """The window only ever holds "en" or "ru", but nothing here should crash."""
    assert i18n.Text("Files", "Файлы")("de") == "Files"


def test_fmt_fills_both_wordings_from_one_set_of_values():
    filled = i18n.MSG_FINISHED.fmt(ok=3, skip=1, fail=0)
    assert "3" in filled.en and "3" in filled.ru
    assert filled.en != filled.ru


def test_fmt_leaves_the_original_alone():
    before = i18n.MSG_DONE_FILE.en
    i18n.MSG_DONE_FILE.fmt(name="x.safetensors")
    assert i18n.MSG_DONE_FILE.en == before


def test_a_failure_says_it_in_english_to_a_traceback():
    exc = i18n.Failure(i18n.ERR_NO_SELECTION)
    assert str(exc) == i18n.ERR_NO_SELECTION.en
    assert exc.text("ru") == i18n.ERR_NO_SELECTION.ru


def test_every_string_has_both_languages():
    """A string added in one language only would silently show blank in the other."""
    missing = [
        name
        for name, value in vars(i18n).items()
        if isinstance(value, i18n.Text) and (not value.en.strip() or not value.ru.strip())
    ]
    assert not missing


def test_the_two_wordings_use_the_same_placeholders():
    import re

    fields = lambda s: sorted(set(re.findall(r"{(\w+)}", s)))  # noqa: E731
    mismatched = [
        name
        for name, value in vars(i18n).items()
        if isinstance(value, i18n.Text) and fields(value.en) != fields(value.ru)
    ]
    assert not mismatched


@pytest.fixture
def no_env(monkeypatch):
    monkeypatch.delenv("HFDL_LANG", raising=False)


def test_the_environment_wins(monkeypatch):
    monkeypatch.setenv("HFDL_LANG", "ru")
    assert i18n.pick_lang("en") == "ru"


def test_the_environment_accepts_a_full_locale(monkeypatch):
    monkeypatch.setenv("HFDL_LANG", "ru_RU.UTF-8")
    assert i18n.pick_lang("en") == "ru"


def test_an_unrecognised_environment_value_is_ignored(monkeypatch):
    """Matching lang.bat: anything unrecognised falls through, it does not win."""
    monkeypatch.setenv("HFDL_LANG", "de")
    assert i18n.pick_lang("ru") == "ru"


def test_the_saved_setting_comes_next(no_env):
    assert i18n.pick_lang("ru") == "ru"
    assert i18n.pick_lang("en") == "en"


def test_an_empty_setting_falls_through_to_the_system(no_env):
    """settings.json says "" until the RU / EN button has been pressed."""
    assert i18n.pick_lang("") == i18n.system_lang()


def test_the_system_answer_is_one_of_the_two(no_env):
    assert i18n.system_lang() in i18n.LANGS
