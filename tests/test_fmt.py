from __future__ import annotations

from datetime import datetime

import pytest

from maifetch.fmt import (
    capped,
    fmt_bytes,
    fmt_cost,
    fmt_datetime,
    fmt_duration_short,
    fmt_duration_zh,
    fmt_int,
    fmt_latency,
    fmt_short_datetime,
    fmt_tokens,
    fmt_used_total,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "0"), (999, "999"), (1500, "1.5K"), (2_410_000, "2.41M"), (3_000_000_000, "3.00B")],
)
def test_fmt_tokens(value: int, expected: str) -> None:
    assert fmt_tokens(value) == expected


@pytest.mark.parametrize(
    ("seconds", "zh", "short"),
    [
        (3 * 86400 + 4 * 3600 + 5, "3 天 4 小时", "3d 4h"),
        (4 * 3600 + 12 * 60, "4 小时 12 分钟", "4h 12m"),
        (600, "10 分钟", "10m"),
        (59, "不到 1 分钟", "<1m"),
    ],
)
def test_fmt_durations(seconds: float, zh: str, short: str) -> None:
    assert fmt_duration_zh(seconds) == zh
    assert fmt_duration_short(seconds) == short


def test_fmt_bytes_and_used_total() -> None:
    assert fmt_bytes(67_216_478_208) == "62.6 GiB"
    assert fmt_bytes(500 * 1024**2) == "500 MiB"
    assert fmt_used_total(None, None) is None
    assert fmt_used_total(None, 67_216_478_208) == "62.6 GiB"
    assert fmt_used_total(12_025_908_428, 67_216_478_208) == "11.2 GiB / 62.6 GiB"


def test_small_formatters() -> None:
    assert fmt_int(1774) == "1,774"
    assert fmt_cost(4.871) == "¥4.87"
    assert fmt_latency(2.06) == "2.1s"
    assert capped("1,774", True) == "1,774+"
    assert capped("1,774", False) == "1,774"
    moment = datetime(2026, 9, 28, 10, 2)
    assert fmt_datetime(moment) == "2026-09-28 10:02"
    assert fmt_short_datetime(moment) == "09-28 10:02"
