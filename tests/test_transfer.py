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
