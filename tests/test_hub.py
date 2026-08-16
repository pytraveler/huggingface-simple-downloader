"""What people paste into the repository field, and what it has to mean.

Every case here is a real address bar or a real thing to type; the module's whole
job is that all of them land on the same four fields.
"""

from __future__ import annotations

import pytest

from hfdl import hub
from hfdl.i18n import Failure


@pytest.mark.parametrize(
    "text, kind, repo, revision, subfolder",
    [
        ("Qwen/Qwen3-8B", "model", "Qwen/Qwen3-8B", "main", ""),
        ("  Qwen/Qwen3-8B  ", "model", "Qwen/Qwen3-8B", "main", ""),
        ('"Qwen/Qwen3-8B"', "model", "Qwen/Qwen3-8B", "main", ""),
        ("gpt2", "model", "gpt2", "main", ""),
        ("https://huggingface.co/Qwen/Qwen3-8B", "model", "Qwen/Qwen3-8B", "main", ""),
        ("http://huggingface.co/Qwen/Qwen3-8B/", "model", "Qwen/Qwen3-8B", "main", ""),
        ("hf.co/Qwen/Qwen3-8B", "model", "Qwen/Qwen3-8B", "main", ""),
        ("huggingface.co/gpt2/tree/main", "model", "gpt2", "main", ""),
        (
            "https://huggingface.co/black-forest-labs/FLUX.1-dev/tree/main/vae",
            "model", "black-forest-labs/FLUX.1-dev", "main", "vae",
        ),
        (
            "https://huggingface.co/org/model/tree/refs%2Fpr%2F12/sub/dir",
            "model", "org/model", "refs/pr/12", "sub/dir",
        ),
        (
            "https://huggingface.co/org/model/blob/main/unet/diffusion.safetensors",
            "model", "org/model", "main", "unet",
        ),
        (
            "https://huggingface.co/org/model/resolve/main/model.safetensors?download=true",
            "model", "org/model", "main", "",
        ),
        (
            "https://huggingface.co/datasets/squad", "dataset", "squad", "main", "",
        ),
        (
            "datasets/HuggingFaceFW/fineweb", "dataset", "HuggingFaceFW/fineweb", "main", "",
        ),
        (
            "https://huggingface.co/spaces/owner/demo", "space", "owner/demo", "main", "",
        ),
    ],
)
def test_parse_ref(text, kind, repo, revision, subfolder):
    ref = hub.parse_ref(text)
    assert (ref.kind, ref.repo_id, ref.revision, ref.subfolder) == (kind, repo, revision, subfolder)


def test_a_url_beats_the_radio_button():
    """The radio button is a default; a link is a statement of fact."""
    ref = hub.parse_ref("https://huggingface.co/datasets/squad", kind="model")
    assert ref.kind == "dataset"


def test_the_radio_button_is_used_when_nothing_says_otherwise():
    assert hub.parse_ref("HuggingFaceFW/fineweb", kind="dataset").kind == "dataset"


@pytest.mark.parametrize("text", ["", "   ", "/", "https://example.com/foo/bar", "tree/main"])
def test_refusals(text):
    with pytest.raises(Failure):
        hub.parse_ref(text)


def test_download_url_quotes_awkward_names():
    ref = hub.RepoRef("model", "org/model", "main", "")
    url = hub.download_url(ref, "folder/a file #1.safetensors")
    assert url == (
        "https://huggingface.co/org/model/resolve/main/folder/a%20file%20%231.safetensors"
    )


def test_download_url_by_kind():
    assert hub.download_url(hub.RepoRef("dataset", "squad", "main", ""), "x.json").startswith(
        "https://huggingface.co/datasets/squad/resolve/main/"
    )
    assert hub.download_url(hub.RepoRef("space", "o/d", "main", ""), "app.py").startswith(
        "https://huggingface.co/spaces/o/d/resolve/main/"
    )


def test_relative_path_drops_the_opened_folder():
    ref = hub.RepoRef("model", "org/model", "main", "vae")
    assert hub.relative_path(ref, "vae/diffusion.safetensors") == "diffusion.safetensors"
    assert hub.relative_path(ref, "other/file.bin") == "other/file.bin"


def test_page_url_round_trips():
    ref = hub.parse_ref("https://huggingface.co/org/model/tree/dev/sub")
    assert ref.page_url == "https://huggingface.co/org/model/tree/dev/sub"


@pytest.mark.parametrize(
    "typed, slug",
    [
        ("Qwen/Qwen3-8B", "Qwen/Qwen3-8B"),
        ("https://huggingface.co/Qwen/Qwen3-8B", "Qwen/Qwen3-8B"),
        ("gpt2", "gpt2"),
        ("https://huggingface.co/datasets/squad", "datasets/squad"),
        ("https://huggingface.co/spaces/owner/demo", "spaces/owner/demo"),
        ("https://huggingface.co/org/model/tree/dev", "org/model/tree/dev"),
        ("https://huggingface.co/org/model/tree/main/vae", "org/model/tree/main/vae"),
        ("https://huggingface.co/org/model/blob/main/vae/x.bin", "org/model/tree/main/vae"),
        ("https://huggingface.co/org/model/tree/refs%2Fpr%2F12/sub", "org/model/tree/refs/pr/12/sub"),
        ("datasets/HuggingFaceFW/fineweb", "datasets/HuggingFaceFW/fineweb"),
    ],
)
def test_slug_is_what_the_history_stores(typed, slug):
    assert hub.parse_ref(typed).slug == slug


@pytest.mark.parametrize(
    "typed",
    [
        "Qwen/Qwen3-8B",
        "gpt2",
        "https://huggingface.co/datasets/squad",
        "https://huggingface.co/spaces/owner/demo",
        "https://huggingface.co/org/model/tree/dev",
        "https://huggingface.co/org/model/tree/main/vae",
        "https://huggingface.co/org/model/tree/refs%2Fpr%2F12/sub",
    ],
)
def test_a_slug_parses_back_to_the_same_reference(typed):
    """Picking an entry out of the history has to reproduce what was loaded."""
    first = hub.parse_ref(typed)
    again = hub.parse_ref(first.slug)
    assert again == first
    assert again.slug == first.slug


def test_a_slug_carries_no_mirror():
    """A mirror in the history would be a stale answer, and refused after a change."""
    ref = hub.parse_ref("Qwen/Qwen3-8B", endpoint="https://hf-mirror.com")
    assert ref.slug == "Qwen/Qwen3-8B"
    assert hub.parse_ref(ref.slug).endpoint == hub.DEFAULT_ENDPOINT


MIRROR = "https://hf-mirror.com"


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("", hub.DEFAULT_ENDPOINT),
        ("   ", hub.DEFAULT_ENDPOINT),
        ("https://hf-mirror.com", MIRROR),
        ("https://hf-mirror.com/", MIRROR),
        ("hf-mirror.com", MIRROR),
        ('  "https://hf-mirror.com/"  ', MIRROR),
        ("http://10.0.0.5:8080", "http://10.0.0.5:8080"),
        ("https://hub.example.com/hf/", "https://hub.example.com/hf"),
    ],
)
def test_normalise_endpoint(typed, expected):
    assert hub.normalise_endpoint(typed) == expected


@pytest.mark.parametrize("bad", ["://", "ftp://mirror.example.com", "https://"])
def test_normalise_endpoint_refuses(bad):
    with pytest.raises(Failure):
        hub.normalise_endpoint(bad)


def test_every_url_follows_the_endpoint():
    ref = hub.parse_ref("Qwen/Qwen3-8B", endpoint=MIRROR)
    assert ref.endpoint == MIRROR and ref.mirrored
    assert hub.download_url(ref, "config.json") == f"{MIRROR}/Qwen/Qwen3-8B/resolve/main/config.json"
    assert ref.page_url == f"{MIRROR}/Qwen/Qwen3-8B/tree/main"


def test_a_hub_link_is_fetched_from_the_configured_mirror():
    """A link names a repository; it does not get to say where the token goes."""
    ref = hub.parse_ref("https://huggingface.co/Qwen/Qwen3-8B", endpoint=MIRROR)
    assert ref.repo_id == "Qwen/Qwen3-8B"
    assert ref.endpoint == MIRROR


def test_a_mirror_link_is_accepted_once_the_mirror_is_configured():
    ref = hub.parse_ref(f"{MIRROR}/datasets/squad/tree/main/plain", endpoint=MIRROR)
    assert (ref.kind, ref.repo_id, ref.subfolder) == ("dataset", "squad", "plain")
    assert ref.endpoint == MIRROR


def test_a_mirror_link_is_refused_until_then():
    with pytest.raises(Failure) as caught:
        hub.parse_ref(f"{MIRROR}/Qwen/Qwen3-8B")
    assert "hf-mirror.com" in caught.value.text.en


def test_a_path_prefix_is_not_mistaken_for_the_owner():
    endpoint = "https://hub.example.com/hf"
    ref = hub.parse_ref(f"{endpoint}/org/model/tree/main/vae", endpoint=endpoint)
    assert (ref.repo_id, ref.subfolder) == ("org/model", "vae")
    assert hub.download_url(ref, "a.bin") == f"{endpoint}/org/model/resolve/main/a.bin"


def test_the_default_endpoint_reads_hf_endpoint(monkeypatch):
    monkeypatch.setenv("HF_ENDPOINT", "https://hf-mirror.com/")
    assert hub.default_endpoint() == MIRROR


def test_a_broken_hf_endpoint_does_not_stop_the_window_opening(monkeypatch):
    monkeypatch.setenv("HF_ENDPOINT", "://nonsense")
    assert hub.default_endpoint() == hub.DEFAULT_ENDPOINT


def test_without_hf_endpoint_it_is_huggingface(monkeypatch):
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    assert hub.default_endpoint() == hub.DEFAULT_ENDPOINT
    assert not hub.RepoRef().mirrored
