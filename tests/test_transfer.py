"""The parts of a transfer that can be checked without a network.

The path guard and the resume measurement are both places where being wrong is
silent: one writes outside the chosen folder, the other reports a finished file
that is half a file.
"""

from __future__ import annotations

import pytest

from hfdl import transfer
from hfdl.i18n import Failure


def test_safe_destination_joins(tmp_path):
    assert transfer.safe_destination(tmp_path, "vae/model.safetensors") == (
        tmp_path / "vae" / "model.safetensors"
    )


def test_safe_destination_normalises_separators(tmp_path):
    assert transfer.safe_destination(tmp_path, "a\\b/c.bin") == tmp_path / "a" / "b" / "c.bin"


@pytest.mark.parametrize("bad", ["../escape.bin", "a/../../escape.bin", "", "/", "."])
def test_safe_destination_refuses_to_climb_out(tmp_path, bad):
    with pytest.raises(Failure):
        transfer.safe_destination(tmp_path, bad)


def test_measure_finds_nothing(tmp_path):
    assert transfer.measure(tmp_path / "absent.bin", 100) == (0, False)


def test_measure_finds_a_finished_file(tmp_path):
    target = tmp_path / "done.bin"
    target.write_bytes(b"x" * 100)
    assert transfer.measure(target, 100) == (100, True)


def test_a_file_of_the_wrong_size_is_not_finished(tmp_path):
    target = tmp_path / "short.bin"
    target.write_bytes(b"x" * 60)
    assert transfer.measure(target, 100) == (60, False)


def test_measure_finds_a_part_file(tmp_path):
    target = tmp_path / "big.bin"
    transfer.part_path(target).write_bytes(b"x" * 40)
    assert transfer.measure(target, 100) == (40, False)


def test_an_unknown_size_trusts_the_file_on_disk(tmp_path):
    target = tmp_path / "any.bin"
    target.write_bytes(b"x" * 7)
    assert transfer.measure(target, None) == (7, True)


def test_check_space_says_nothing_when_it_fits(tmp_path):
    transfer.check_space(tmp_path, 1)
    transfer.check_space(tmp_path, None)


def test_check_space_refuses_the_impossible(tmp_path):
    with pytest.raises(Failure):
        transfer.check_space(tmp_path, 1 << 60)  # an exabyte


def test_control_stops_a_parked_worker():
    """Stop has to reach a thread parked inside Pause, or it would never return."""
    control = transfer.Control()
    control.pause()
    assert control.paused
    control.stop()
    assert control.stopped and not control.paused
    with pytest.raises(transfer.Cancelled):
        control.checkpoint()


def test_control_lets_work_through_by_default():
    control = transfer.Control()
    control.checkpoint()
    assert not control.paused and not control.stopped


def test_a_redirect_that_only_a_get_gets_is_followed(tmp_path):
    """ModelScope answers HEAD on `resolve` with 200 and redirects only the GET.

    Writing that 302's body into the file would be a download of the wrong
    bytes; the redirect has to be walked, the resume kept, and the token left
    behind at the first host.
    """
    import httpx

    payload = b"0123456789" * 50
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "modelscope.cn":
            if request.method == "HEAD":
                return httpx.Response(200)
            return httpx.Response(
                302,
                headers={"location": "https://cdn-lfs-cn-1.modelscope.cn/obj"},
                content=b"<html>redirect</html>",
            )
        start = int(request.headers.get("range", "bytes=0-")[6:].rstrip("-") or 0)
        return httpx.Response(
            206 if start else 200,
            content=payload[start:],
            headers={"content-range": f"bytes {start}-{len(payload) - 1}/{len(payload)}"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    target = tmp_path / "model.safetensors"
    transfer.part_path(target).write_bytes(payload[:120])
    result = transfer.fetch(
        client,
        "https://modelscope.cn/models/o/n/resolve/master/model.safetensors",
        target,
        token="secret",
        size=len(payload),
    )
    assert target.read_bytes() == payload
    assert result.resumed_from == 120
    cdn = [r for r in seen if r.url.host != "modelscope.cn"]
    assert cdn and all("authorization" not in r.headers for r in cdn)
    assert cdn[-1].headers["range"] == "bytes=120-"


@pytest.mark.parametrize("url, repo", [
    ("https://huggingface.co/org/model/resolve/main/x.bin", "org/model"),
    ("https://huggingface.co/datasets/org/data/resolve/main/x.bin", "org/data"),
    ("https://modelscope.cn/models/Qwen/Qwen3-8B/resolve/master/x.bin", "Qwen/Qwen3-8B"),
    ("https://modelscope.cn/api/v1/datasets/o/d/repo?Revision=master&FilePath=a", "o/d"),
])
def test_the_repository_is_read_back_out_of_a_link(url, repo):
    assert transfer._repo_from(url) == repo


def test_a_modelscope_refusal_does_not_ask_for_a_token():
    text = transfer._explain(403, "https://modelscope.cn/models/o/n/resolve/master/x.bin")
    assert "o/n" in text.en and "public" in text.en
    assert "token" not in text.en.lower()
