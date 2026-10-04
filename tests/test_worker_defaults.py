"""Exercise automatic worker selection across local CPU allocations."""

import pytest

import conftest


@pytest.mark.parametrize(
    "available,expected",
    [(None, 1), (1, 1), (2, 1), (3, 1), (4, 2), (8, 4), (16, 8), (32, 8)],
)
def test_automatic_workers_reserve_capacity_and_obey_the_cap(
    monkeypatch, pytestconfig, available, expected
):
    monkeypatch.setattr(pytestconfig.option, "numprocesses", "auto")
    monkeypatch.setattr(conftest.os, "process_cpu_count", lambda: available)
    assert conftest.pytest_xdist_auto_num_workers(pytestconfig) == expected


def test_explicit_logical_selection_keeps_xdist_semantics(monkeypatch, pytestconfig):
    monkeypatch.setattr(pytestconfig.option, "numprocesses", "logical")
    assert conftest.pytest_xdist_auto_num_workers(pytestconfig) is None
