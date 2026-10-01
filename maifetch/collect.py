"""从 Host 采集自身信息快照。

所有来源并发执行、各自限时；单个来源失败只影响自己的字段并记入 failed_sources，整体永不抛错。
统一使用 ctx.call_capability：Host 失败时它原样返回 {"success": False, ...}，在这里识别为失败
（部分 SDK 便捷方法会把失败吞成 []，会被误显示成「0 次」）。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Any

from maifetch.config import Settings
from maifetch.hardware import collect_hardware
from maifetch.snapshot import Hardware, Identity, ModelUsage, PluginInfo, Runtime, Snapshot, Usage

SOURCE_TIMEOUT_S = 3.0
STATS_ROW_CAP = 50
HOST_VERSION_ENV = "MAIBOT_HOST_VERSION"
_TOOL_COMPONENT_TYPES = frozenset({"tool", "action"})
_IDENTITY_KEYS = ("bot.nickname", "bot.alias_names", "bot.platform", "bot.platforms")
_ACCOUNT_KEY = "bot.qq_account"


class SourceError(RuntimeError):
    """单个数据源调用失败或返回格式异常。"""


def _check(result: Any) -> Any:
    if isinstance(result, Mapping) and result.get("success") is False:
        raise SourceError(str(result.get("error") or "Host 返回失败"))
    return result


async def _guarded(name: str, awaitable: Awaitable[Any], failed: list[str], logger: Any) -> Any:
    try:
        return _check(await asyncio.wait_for(awaitable, SOURCE_TIMEOUT_S))
    except Exception as exc:  # noqa: BLE001 - 单个来源失败不影响整体
        failed.append(name)
        logger.debug("maifetch 数据源 %s 不可用：%s", name, exc)
        return None


def _parsed(name: str, failed: list[str], logger: Any, parser: Callable[..., Any], *args: Any) -> Any:
    try:
        return parser(*args)
    except Exception as exc:  # noqa: BLE001
        failed.append(name)
        logger.debug("maifetch 数据源 %s 返回格式异常：%s", name, exc)
        return None


async def _nothing() -> None:
    return None


def _str_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _str_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


async def _fetch_identity(ctx: Any, show_account: bool) -> dict[str, Any]:
    keys = list(_IDENTITY_KEYS) + ([_ACCOUNT_KEY] if show_account else [])
    results = await asyncio.gather(*(ctx.call_capability("config.get", key=key, default=None) for key in keys))
    return {key: _check(result) for key, result in zip(keys, results)}


def local_timezone_name() -> str | None:
    """尽量给出 IANA 时区名（TZ 或 /etc/localtime），否则退回时区缩写。"""

    tz_env = os.environ.get("TZ", "").strip().lstrip(":")
    if "/" in tz_env:
        return tz_env
    try:
        target = os.path.realpath("/etc/localtime")
    except OSError:
        target = ""
    if "zoneinfo/" in target:
        return target.split("zoneinfo/", 1)[1]
    return datetime.now().astimezone().tzname()


def _platform_names(primary: Any, extra: Any) -> tuple[str, ...]:
    """bot.platform 与 bot.platforms（格式为 platform:账号）只取平台名；账号 ID 一律丢弃，绝不输出。"""

    names: list[str] = []
    for entry in (primary, *_str_tuple(extra)):
        name = str(entry or "").partition(":")[0].strip().lower()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def parse_identity(values: Mapping[str, Any] | None, *, now: datetime, timezone: str | None) -> Identity:
    values = values or {}
    return Identity(
        nickname=_str_or_none(values.get("bot.nickname")),
        alias_names=_str_tuple(values.get("bot.alias_names")),
        platforms=_platform_names(values.get("bot.platform"), values.get("bot.platforms")),
        account=_str_or_none(values.get(_ACCOUNT_KEY)),
        local_time=now,
        timezone=timezone,
    )


def parse_online_since(record: Any) -> datetime | None:
    if isinstance(record, list):
        record = record[0] if record else None
    if record is None:
        return None
    if not isinstance(record, Mapping):
        raise SourceError("在线记录格式异常")
    raw = record.get("start_timestamp")
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str) and raw.strip():
        value = datetime.fromisoformat(raw.strip())
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = datetime.fromtimestamp(raw, tz=dt_timezone.utc)
    else:
        return None
    return value.astimezone() if value.tzinfo is None else value


def parse_plugins(raw: Any) -> tuple[tuple[PluginInfo, ...], int, int]:
    if not isinstance(raw, Mapping):
        raise SourceError("插件列表格式异常")
    infos: list[PluginInfo] = []
    tools = 0
    for plugin_id, info in raw.items():
        version = ""
        if isinstance(info, Mapping):
            version = str(info.get("version") or "")
            for component in info.get("components") or []:
                if (
                    isinstance(component, Mapping)
                    and str(component.get("type") or "").lower() in _TOOL_COMPONENT_TYPES
                    and component.get("enabled", True)
                ):
                    tools += 1
        infos.append(PluginInfo(plugin_id=str(plugin_id), version=version))
    infos.sort(key=lambda item: item.plugin_id)
    return tuple(infos), len(infos), tools


def parse_model_tasks(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple)):
        raise SourceError("模型任务列表格式异常")
    return _str_tuple(raw)


def parse_models(raw: Any, top_k: int) -> dict[str, Any]:
    """解析模型统计为 Usage 字段：调用次数排行、花费排行（同一批行，不额外请求）与覆盖全部模型的合计。"""

    if not isinstance(raw, list):
        raise SourceError("模型统计格式异常")
    rows = [
        ModelUsage(
            model_name=str(row.get("model_name") or "Unknown"),
            requests=_int(row.get("request_count")),
            tokens=_int(row.get("total_tokens")),
            avg_latency_s=_float_or_none(row.get("avg_response_time")),
            cost=_float_or_none(row.get("total_cost")),
        )
        for row in raw
        if isinstance(row, Mapping)
    ]
    rows.sort(key=lambda item: (-item.requests, item.model_name))
    total_requests = sum(item.requests for item in rows)
    total_tokens = sum(item.tokens for item in rows)
    total_cost = sum(item.cost or 0.0 for item in rows)
    costed = sorted(
        (item for item in rows if (item.cost or 0.0) > 0), key=lambda item: (-(item.cost or 0.0), item.model_name)
    )
    return {
        "models": tuple(rows[:top_k]),
        "model_count": len(rows),
        "models_by_cost": tuple(costed[:top_k]),
        "costed_model_count": len(costed),
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "totals_capped": len(raw) >= STATS_ROW_CAP,
    }


def parse_messages(raw: Any) -> tuple[int, bool]:
    """只取合计；聊天名称（其他群名）立即丢弃，绝不进入快照。"""

    if not isinstance(raw, Mapping):
        raise SourceError("消息统计格式异常")
    keys = raw.get("values_by_key")
    capped = isinstance(keys, Mapping) and len(keys) >= STATS_ROW_CAP
    return _int(raw.get("total")), capped


def _sdk_version() -> str | None:
    try:
        import maibot_sdk

        return str(getattr(maibot_sdk, "__version__", "") or "") or None
    except Exception:  # noqa: BLE001
        return None


async def collect_snapshot(
    ctx: Any,
    settings: Settings,
    *,
    plugin_version: str,
    plugin_dir: Path,
    now: datetime | None = None,
) -> Snapshot:
    collected_at = now or datetime.now().astimezone()
    failed: list[str] = []
    logger = ctx.logger
    days = settings.window_days
    identity_raw, online_raw, plugins_raw, tasks_raw, models_raw, messages_raw, hardware_raw = await asyncio.gather(
        _guarded("identity", _fetch_identity(ctx, settings.visibility.show_account), failed, logger),
        _guarded(
            "online",
            ctx.call_capability(
                "database.get",
                model_name="OnlineTime",
                filters={},
                limit=1,
                order_by="-end_timestamp",
                single_result=True,
            ),
            failed,
            logger,
        ),
        _guarded("plugins", ctx.call_capability("component.get_all_plugins"), failed, logger),
        _guarded("model_tasks", ctx.call_capability("llm.get_available_models"), failed, logger),
        _guarded(
            "models",
            ctx.call_capability("statistics.local.models", days=days, limit=STATS_ROW_CAP),
            failed,
            logger,
        ),
        _guarded(
            "messages",
            ctx.call_capability("statistics.local.message_trend", days=days, bucket="day", top_chats=STATS_ROW_CAP),
            failed,
            logger,
        ),
        _guarded("hardware", asyncio.to_thread(collect_hardware, plugin_dir), failed, logger)
        if settings.hardware.enabled
        else _nothing(),
    )

    identity = parse_identity(identity_raw, now=collected_at, timezone=local_timezone_name())
    online_since = _parsed("online", failed, logger, parse_online_since, online_raw)
    plugins_parsed = _parsed("plugins", failed, logger, parse_plugins, plugins_raw) if plugins_raw is not None else None
    tasks = _parsed("model_tasks", failed, logger, parse_model_tasks, tasks_raw) if tasks_raw is not None else None
    models_parsed = (
        _parsed("models", failed, logger, parse_models, models_raw, settings.top_models)
        if models_raw is not None
        else None
    )
    messages_parsed = (
        _parsed("messages", failed, logger, parse_messages, messages_raw) if messages_raw is not None else None
    )

    plugins, plugin_count, tool_count = plugins_parsed if plugins_parsed else (None, None, None)
    runtime = Runtime(
        host_version=_str_or_none(os.environ.get(HOST_VERSION_ENV)),
        sdk_version=_sdk_version(),
        plugin_version=plugin_version,
        online_since=online_since,
        plugins=plugins,
        plugin_count=plugin_count,
        tool_count=tool_count,
        model_tasks=tasks,
    )
    usage_fields: dict[str, Any] = models_parsed or {}
    total_messages, messages_capped = messages_parsed if messages_parsed else (None, False)
    usage = Usage(window_days=days, total_messages=total_messages, messages_capped=messages_capped, **usage_fields)
    return Snapshot(
        collected_at=collected_at,
        identity=identity,
        runtime=runtime,
        usage=usage,
        hardware=hardware_raw if isinstance(hardware_raw, Hardware) else None,
        failed_sources=tuple(sorted(set(failed))),
    )
