from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from maifetch.sample import SAMPLE_PLUGINS, sample_snapshot
from maifetch.snapshot import Snapshot, snapshot_to_dict


def test_uptime_seconds() -> None:
    snap = sample_snapshot()
    assert snap.uptime_seconds() == (3 * 86400 + 4 * 3600 + 22 * 60)


def test_uptime_unknown_and_clock_skew() -> None:
    snap = sample_snapshot()
    assert Snapshot(collected_at=snap.collected_at).uptime_seconds() is None
    skewed = replace(snap, runtime=replace(snap.runtime, online_since=snap.collected_at + timedelta(minutes=5)))
    assert skewed.uptime_seconds() == 0.0


def test_snapshot_to_dict_is_jsonable() -> None:
    data = snapshot_to_dict(sample_snapshot())
    assert data["collected_at"].startswith("2026-10-01T14:24")
    assert data["identity"]["nickname"] == "麦麦"
    assert data["runtime"]["plugins"][0]["plugin_id"] == SAMPLE_PLUGINS[0][0]
    assert isinstance(data["identity"]["platforms"], list)


def test_sample_variants() -> None:
    assert sample_snapshot(hardware=False).hardware is None
    assert sample_snapshot().usage.total_cost is None
    assert sample_snapshot(cost=True).usage.total_cost == 4.87
    assert sample_snapshot().identity.account is None
    assert sample_snapshot(account=True).identity.account == "123456789"
    assert len(sample_snapshot().runtime.plugins or ()) == 12
