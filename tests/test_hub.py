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


def test_the_client_checks_certificates_against_the_system_store_by_default():
    import ssl

    with hub.make_client() as client:
        context = client._transport._pool._ssl_context
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


def test_the_client_can_be_told_not_to_check_certificates():
    import ssl

    with hub.make_client(verify=False) as client:
        context = client._transport._pool._ssl_context
    assert context.verify_mode == ssl.CERT_NONE


MS = "https://modelscope.cn"


@pytest.mark.parametrize("url", [
    "https://modelscope.cn", "https://www.modelscope.cn", "https://modelscope.ai",
    "https://www.modelscope.ai/", "https://cdn-lfs-cn-1.modelscope.cn/prod/x",
])
def test_modelscope_is_recognised_by_host(url):
    assert hub.is_modelscope(url)


@pytest.mark.parametrize("url", [
    hub.DEFAULT_ENDPOINT, MIRROR, "https://notmodelscope.cn", "https://modelscope.cn.example.com",
])
def test_nothing_else_is_modelscope(url):
    assert not hub.is_modelscope(url)


@pytest.mark.parametrize(
    "text, kind, repo, revision, subfolder",
    [
        ("Qwen/Qwen2.5-0.5B-Instruct", "model", "Qwen/Qwen2.5-0.5B-Instruct", "master", ""),
        ("models/Qwen/Qwen2.5-0.5B-Instruct", "model", "Qwen/Qwen2.5-0.5B-Instruct", "master", ""),
        ("https://modelscope.cn/models/Qwen/Qwen3-8B", "model", "Qwen/Qwen3-8B", "master", ""),
        ("https://www.modelscope.cn/models/Qwen/Qwen3-8B/files", "model", "Qwen/Qwen3-8B", "master", ""),
        ("modelscope.cn/models/Qwen/Qwen3-8B/summary", "model", "Qwen/Qwen3-8B", "master", ""),
        ("www.modelscope.cn/models/Qwen/Qwen3-8B", "model", "Qwen/Qwen3-8B", "master", ""),
        ("https://modelscope.ai/models/Qwen/Qwen3-8B", "model", "Qwen/Qwen3-8B", "master", ""),
        (
            "https://modelscope.cn/models/o/n/resolve/master/vae/model.safetensors",
            "model", "o/n", "master", "vae",
        ),
        (
            "https://modelscope.cn/models/o/n/file/view/master/unet/config.json",
            "model", "o/n", "master", "unet",
        ),
        ("https://modelscope.cn/models/o/n/tree/v1.0/sub", "model", "o/n", "v1.0", "sub"),
        (
            "https://modelscope.cn/datasets/modelscope/MMLU-Pro/files",
            "dataset", "modelscope/MMLU-Pro", "master", "",
        ),
        ("datasets/modelscope/gsm8k", "dataset", "modelscope/gsm8k", "master", ""),
        ("https://huggingface.co/Qwen/Qwen3-8B", "model", "Qwen/Qwen3-8B", "master", ""),
    ],
)
def test_parse_ref_on_modelscope(text, kind, repo, revision, subfolder):
    ref = hub.parse_ref(text, endpoint=MS)
    assert (ref.kind, ref.repo_id, ref.revision, ref.subfolder) == (kind, repo, revision, subfolder)
    assert ref.endpoint == MS and ref.modelscope


def test_either_modelscope_site_names_a_repository_on_the_other():
    ref = hub.parse_ref("https://modelscope.ai/models/Qwen/Qwen3-8B", endpoint=MS)
    assert (ref.repo_id, ref.endpoint) == ("Qwen/Qwen3-8B", MS)


def test_a_modelscope_link_says_which_value_to_pick():
    with pytest.raises(Failure) as caught:
        hub.parse_ref("https://www.modelscope.cn/models/Qwen/Qwen3-8B")
    assert "https://www.modelscope.cn" in caught.value.text.en


@pytest.mark.parametrize("text, kind", [("owner/demo", "space"), ("studios/owner/demo", "model")])
def test_modelscope_studios_are_refused(text, kind):
    with pytest.raises(Failure) as caught:
        hub.parse_ref(text, kind=kind, endpoint=MS)
    assert caught.value.text == hub.i18n.ERR_MS_NO_SPACE


@pytest.mark.parametrize(
    "typed",
    [
        "Qwen/Qwen3-8B",
        "https://modelscope.cn/datasets/modelscope/MMLU-Pro",
        "https://modelscope.cn/models/o/n/tree/v1.0/sub",
        "https://modelscope.cn/models/o/n/tree/master/vae",
    ],
)
def test_a_modelscope_slug_parses_back_to_the_same_reference(typed):
    first = hub.parse_ref(typed, endpoint=MS)
    assert hub.parse_ref(first.slug, endpoint=MS) == first


def test_a_modelscope_slug_leaves_master_out():
    ref = hub.parse_ref("https://modelscope.cn/models/Qwen/Qwen3-8B", endpoint=MS)
    assert ref.slug == "Qwen/Qwen3-8B"


def test_modelscope_urls():
    model = hub.parse_ref("o/n", endpoint=MS)
    assert hub.download_url(model, "a dir/x #1.bin") == (
        f"{MS}/models/o/n/resolve/master/a%20dir/x%20%231.bin"
    )
    assert model.page_url == f"{MS}/models/o/n/files"
    data = hub.parse_ref("datasets/o/d", endpoint=MS)
    assert hub.download_url(data, "data/t 1.parquet") == (
        f"{MS}/api/v1/datasets/o/d/repo?Revision=master&FilePath=data%2Ft%201.parquet"
    )
    assert data.page_url == f"{MS}/datasets/o/d/files"


def test_the_hf_token_never_goes_to_modelscope():
    assert hub.token_for(hub.parse_ref("o/n", endpoint=MS), "hf_secret") == ""
    assert hub.token_for(hub.parse_ref("o/n"), "hf_secret") == "hf_secret"


def _mock(handler):
    import httpx

    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped)), seen


def _ms_body(**data):
    return {"Code": 200, "Data": data, "Message": "success", "Success": True}


def test_modelscope_model_files_keep_blobs_with_their_real_sizes():
    import httpx

    files = [
        {"Path": "vae", "Type": "tree", "Size": 0, "IsLFS": False},
        {"Path": "vae/diffusion.safetensors", "Type": "blob", "Size": 334643268, "IsLFS": True},
        {"Path": "config.json", "Type": "blob", "Size": 659, "IsLFS": False},
    ]
    client, seen = _mock(lambda r: httpx.Response(200, json=_ms_body(Files=files)))
    listed = hub.list_files(client, hub.parse_ref("o/n", endpoint=MS), token="hf_secret")
    assert [(f.path, f.size, f.is_lfs) for f in listed] == [
        ("config.json", 659, False),
        ("vae/diffusion.safetensors", 334643268, True),
    ]
    assert seen[0].url.path == "/api/v1/models/o/n/repo/files"
    assert seen[0].url.params["Revision"] == "master"
    assert "authorization" not in seen[0].headers

    ref = hub.parse_ref("https://modelscope.cn/models/o/n/tree/master/vae", endpoint=MS)
    assert [f.path for f in hub.list_files(client, ref)] == ["vae/diffusion.safetensors"]


def test_a_missing_modelscope_branch_is_not_an_empty_repository():
    import httpx

    client, _ = _mock(lambda r: httpx.Response(200, json=_ms_body(Files=None)))
    with pytest.raises(Failure) as caught:
        hub.list_files(client, hub.parse_ref("o/n/tree/nope", endpoint=MS))
    assert "ModelScope" in caught.value.text.en and "nope" in caught.value.text.en


def test_modelscope_dataset_files_follow_the_pages(monkeypatch):
    import httpx

    everything = [{"Path": f"f{i}.json", "Type": "blob", "Size": i, "IsLFS": False} for i in range(7)]
    everything.insert(3, {"Path": "data", "Type": "tree", "Size": 0})
    monkeypatch.setattr(hub, "MS_PAGE_SIZE", 3)

    def handler(request):
        page = int(request.url.params["PageNumber"])
        chunk = everything[(page - 1) * 3: page * 3]
        return httpx.Response(200, json=_ms_body(Files=chunk, TotalCount=len(everything)))

    client, seen = _mock(handler)
    listed = hub.list_files(client, hub.parse_ref("datasets/o/d", endpoint=MS))
    assert len(listed) == 7 and len(seen) == 3
    assert seen[0].url.path == "/api/v1/datasets/o/d/repo/tree"


@pytest.mark.parametrize("status, wording", [(404, "ERR_MS_NOT_FOUND"), (403, "ERR_MS_PRIVATE")])
def test_modelscope_refusals_say_only_public_repositories_work(status, wording):
    import httpx

    client, _ = _mock(lambda r: httpx.Response(status, json={"Code": 1, "Message": "x"}))
    with pytest.raises(Failure) as caught:
        hub.list_files(client, hub.parse_ref("o/n", endpoint=MS))
    assert caught.value.text == getattr(hub.i18n, wording).fmt(repo="o/n")
    assert "public" in caught.value.text.en


def test_modelscope_revisions_put_master_first():
    import httpx

    body = _ms_body(RevisionMap={
        "Branches": [{"Revision": "dev"}, {"Revision": "master"}],
        "Tags": [{"Revision": "v1.0"}],
    })
    client, _ = _mock(lambda r: httpx.Response(200, json=body))
    assert hub.list_revisions(client, hub.parse_ref("o/n", endpoint=MS)) == ["master", "dev", "v1.0"]
    assert hub.list_revisions(client, hub.parse_ref("datasets/o/d", endpoint=MS)) == ["master"]
