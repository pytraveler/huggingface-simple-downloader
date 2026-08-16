"""The three history lists, and surviving a settings file that says anything.

A settings file is not worth a startup failure, so `load` has to answer with
something usable whatever is in it - including nothing, including a hand-edit
that broke the JSON, including a value of the wrong type.
"""

from __future__ import annotations

import json

import pytest

from hfdl.config import MAX_RECENT, Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr("hfdl.config.SETTINGS_PATH", tmp_path / "settings.json")
    return Settings()


def test_the_newest_goes_first(settings):
    settings.remember_repo("a/one")
    settings.remember_repo("b/two")
    assert settings.recent_repos == ["b/two", "a/one"]


def test_a_repeat_moves_up_instead_of_doubling(settings):
    for slug in ("a/one", "b/two", "a/one"):
        settings.remember_repo(slug)
    assert settings.recent_repos == ["a/one", "b/two"]


def test_duplicates_are_collapsed_ignoring_case(settings):
    settings.remember_endpoint("https://hf-mirror.com")
    settings.remember_endpoint("https://HF-Mirror.com")
    assert settings.recent_endpoints == ["https://HF-Mirror.com"]


def test_the_list_is_capped(settings):
    for n in range(MAX_RECENT + 5):
        settings.remember_repo(f"org/model-{n}")
    assert len(settings.recent_repos) == MAX_RECENT
    assert settings.recent_repos[0] == f"org/model-{MAX_RECENT + 4}"


def test_the_three_lists_are_independent(settings):
    settings.remember_repo("a/one")
    settings.remember_endpoint("https://hf-mirror.com")
    settings.remember_path(r"D:\models")
    settings.forget_paths()
    assert settings.recent_paths == []
    assert settings.recent_repos == ["a/one"]
    assert settings.recent_endpoints == ["https://hf-mirror.com"]


def test_a_round_trip_keeps_everything(settings):
    settings.remember_repo("datasets/squad")
    settings.remember_endpoint("https://hf-mirror.com")
    settings.endpoint = "https://hf-mirror.com"
    settings.lang = "ru"
    settings.save()

    again = Settings.load()
    assert again.recent_repos == ["datasets/squad"]
    assert again.endpoint == "https://hf-mirror.com"
    assert again.lang == "ru"


def test_a_missing_file_is_a_fresh_install(settings):
    assert Settings.load() == Settings()


def test_broken_json_is_a_fresh_install(settings, monkeypatch):
    from hfdl import config

    config.SETTINGS_PATH.write_text("{ not json", encoding="utf-8")
    assert Settings.load() == Settings()


def test_unknown_keys_are_dropped(settings):
    from hfdl import config

    config.SETTINGS_PATH.write_text(
        json.dumps({"lang": "ru", "from_a_later_version": 7}), encoding="utf-8"
    )
    assert Settings.load().lang == "ru"


def test_nonsense_values_are_clamped(settings):
    from hfdl import config

    config.SETTINGS_PATH.write_text(
        json.dumps({"threads": 999, "lang": "klingon"}), encoding="utf-8"
    )
    loaded = Settings.load()
    assert loaded.threads <= 8
    assert loaded.lang == ""
