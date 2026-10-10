"""数字、体积、时长与时间的展示格式（文字输出与卡片共用）。"""

from __future__ import annotations

from datetime import datetime

UNKNOWN = "未知"
DEFAULT_CURRENCY_SYMBOL = "¥"


def fmt_int(value: int) -> str:
    return f"{value:,}"


def fmt_tokens(value: int) -> str:
    if value < 1_000:
        return str(value)
    if value < 1_000_000:
        return f"{value / 1_000:.1f}K"
    if value < 1_000_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value / 1_000_000_000:.2f}B"


def fmt_cost(value: float, symbol: str) -> str:
    """只换显示用的货币符号，不做汇率换算。"""

    return f"{symbol}{value:.2f}"


def fmt_latency(seconds: float) -> str:
    return f"{seconds:.1f}s"


def fmt_bytes(value: int) -> str:
    gib = value / 1024**3
    if gib >= 1:
        return f"{gib:.1f} GiB"
    return f"{value / 1024**2:.0f} MiB"


def fmt_used_total(used: int | None, total: int | None) -> str | None:
    if total is None:
        return None
    if used is None:
        return fmt_bytes(total)
    return f"{fmt_bytes(used)} / {fmt_bytes(total)}"


def _split_duration(seconds: float) -> tuple[int, int, int]:
    minutes = int(seconds // 60)
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    return days, hours, mins


def fmt_duration_zh(seconds: float) -> str:
    days, hours, mins = _split_duration(seconds)
    if days:
        return f"{days} 天 {hours} 小时"
    if hours:
        return f"{hours} 小时 {mins} 分钟"
    if mins:
        return f"{mins} 分钟"
    return "不到 1 分钟"


def fmt_duration_short(seconds: float) -> str:
    days, hours, mins = _split_duration(seconds)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    if mins:
        return f"{mins}m"
    return "<1m"


def fmt_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def fmt_short_datetime(value: datetime) -> str:
    return value.strftime("%m-%d %H:%M")


def capped(text: str, is_capped: bool) -> str:
    """Host 统计接口最多返回 50 行；触顶时合计只是下限，加「+」标明。"""

    return f"{text}+" if is_capped else text
