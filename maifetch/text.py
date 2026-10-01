"""面向规划器 / 用户的纯文字输出，以及工具入参解析。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from maifetch.fmt import (
    UNKNOWN,
    capped,
    fmt_cost,
    fmt_datetime,
    fmt_duration_zh,
    fmt_int,
    fmt_latency,
    fmt_short_datetime,
    fmt_tokens,
    fmt_used_total,
)
from maifetch.snapshot import Snapshot

INJECTION_TAG = "【maifetch·自身信息】"
REPLY_HINT = "（回复用户时，请把与问题相关的事实写进 reply 工具的 reply_reference，回复器看不到本工具结果。）"
SECTIONS: tuple[str, ...] = ("all", "identity", "runtime", "plugins", "models", "usage", "hardware")

_SECTION_ALIASES: dict[str, str] = {
    "": "all",
    "all": "all",
    "全部": "all",
    "所有": "all",
    "identity": "identity",
    "身份": "identity",
    "我是谁": "identity",
    "runtime": "runtime",
    "运行": "runtime",
    "版本": "runtime",
    "在线": "runtime",
    "plugins": "plugins",
    "插件": "plugins",
    "工具": "plugins",
    "models": "models",
    "模型": "models",
    "usage": "usage",
    "用量": "usage",
    "用量统计": "usage",
    "token": "usage",
    "tokens": "usage",
    "hardware": "hardware",
    "硬件": "hardware",
    "机器": "hardware",
    "配置": "hardware",
}
_TRUE_STRINGS = frozenset({"true", "1", "yes", "y", "on", "是", "要", "好", "发", "发送"})


def parse_bool(value: Any) -> bool:
    """规划器传参不精确：只有明确的「真」才算 True，"false"/"0"/"否" 等一律 False。"""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in _TRUE_STRINGS


def normalize_section(value: Any) -> tuple[str, str | None]:
    key = str(value if value is not None else "").strip().lower()
    if key in _SECTION_ALIASES:
        return _SECTION_ALIASES[key], None
    return "all", f"（未识别的 section「{value}」，已返回全部信息。）"


def _identity_block(s: Snapshot) -> str:
    identity = s.identity
    name = identity.nickname or UNKNOWN
    if identity.alias_names:
        name += f"（别名：{'、'.join(identity.alias_names)}）"
    parts = [f"昵称：{name}"]
    if identity.platforms:
        parts.append(f"平台：{'、'.join(identity.platforms)}")
    if identity.account:
        parts.append(f"账号：{identity.account}")
    if identity.local_time:
        clock = f"本地时间：{fmt_datetime(identity.local_time)}"
        if identity.timezone:
            clock += f"（{identity.timezone}）"
        parts.append(clock)
    return "【身份】" + "；".join(parts)


def _runtime_block(s: Snapshot) -> str:
    runtime = s.runtime
    versions = (
        f"MaiBot {runtime.host_version or UNKNOWN} · 插件 SDK {runtime.sdk_version or UNKNOWN} · "
        f"maifetch {runtime.plugin_version or UNKNOWN}"
    )
    uptime = s.uptime_seconds()
    if uptime is None or runtime.online_since is None:
        online = f"本次在线时长：{UNKNOWN}"
    else:
        online = f"本次在线 {fmt_duration_zh(uptime)}（自 {fmt_short_datetime(runtime.online_since)}）"
    return f"【运行】{versions}；{online}"


def _plugins_block(s: Snapshot) -> str:
    runtime = s.runtime
    if runtime.plugin_count is None:
        return f"【插件】{UNKNOWN}"
    head = f"{runtime.plugin_count} 个已加载"
    if runtime.tool_count is not None:
        head += f"、{runtime.tool_count} 个工具"
    if runtime.plugins:
        head += "：" + "、".join(
            f"{plugin.plugin_id}@{plugin.version}" if plugin.version else plugin.plugin_id for plugin in runtime.plugins
        )
    return f"【插件】{head}"


def _tasks_block(s: Snapshot) -> str:
    tasks = s.runtime.model_tasks
    return "【模型任务】" + ("、".join(tasks) if tasks else UNKNOWN)


def _models_block(s: Snapshot) -> str:
    usage = s.usage
    title = f"【模型用量·近 {usage.window_days} 天】"
    if usage.total_requests is None:
        return title + UNKNOWN
    if not usage.models:
        return title + "暂无模型调用记录"
    items: list[str] = []
    for model in usage.models:
        bits = [f"{fmt_int(model.requests)} 次", f"{fmt_tokens(model.tokens)} tok"]
        if model.avg_latency_s is not None:
            bits.append(fmt_latency(model.avg_latency_s))
        if model.cost is not None:
            bits.append(fmt_cost(model.cost))
        items.append(f"{model.model_name} " + "/".join(bits))
    return title + _models_scope(usage.model_count, len(usage.models), usage.totals_capped) + "；".join(items)


def _models_scope(model_count: int | None, listed: int, is_capped: bool) -> str:
    """说明这里列的是全部模型还是只是前几个，避免把列出的数加起来与「合计」对不上。"""

    if model_count is None:
        return ""
    if model_count <= listed and not is_capped:
        return f"全部 {model_count} 个模型："
    return f"调用次数最多的前 {listed} 个（共 {capped(str(model_count), is_capped)} 个模型，其余未列出）："


def _totals_block(s: Snapshot) -> str:
    usage = s.usage
    parts: list[str] = []
    if usage.total_requests is not None:
        parts.append(f"{capped(fmt_int(usage.total_requests), usage.totals_capped)} 次请求")
        parts.append(f"{capped(fmt_tokens(usage.total_tokens or 0), usage.totals_capped)} tokens")
    if usage.total_messages is not None:
        parts.append(f"{capped(fmt_int(usage.total_messages), usage.messages_capped)} 条消息")
    if usage.total_cost is not None:
        parts.append(f"花费 {capped(fmt_cost(usage.total_cost), usage.totals_capped)}")
    return f"【合计·近 {usage.window_days} 天（全部模型）】" + ("、".join(parts) if parts else UNKNOWN)


def _hardware_block(s: Snapshot) -> str:
    hw = s.hardware
    if hw is None:
        return "【硬件】运维未开启硬件信息"
    parts: list[str] = []
    for value in (hw.os, hw.arch):
        if value:
            parts.append(value)
    if hw.kernel:
        parts.append(f"内核 {hw.kernel}")
    if hw.virt:
        parts.append(hw.virt)
    if hw.cpu:
        parts.append(hw.cpu + (f" ×{hw.cpu_cores}" if hw.cpu_cores else ""))
    memory = fmt_used_total(hw.mem_used, hw.mem_total)
    if memory:
        parts.append(f"内存 {memory}")
    disk = fmt_used_total(hw.disk_used, hw.disk_total)
    if disk:
        parts.append(f"磁盘 {disk}")
    if hw.python:
        parts.append(f"Python {hw.python}")
    if hw.uptime_s is not None:
        parts.append(f"开机 {fmt_duration_zh(hw.uptime_s)}")
    return "【硬件】" + (" · ".join(parts) if parts else "（所有硬件字段均已隐藏）")


_Block = Callable[[Snapshot], str]
_ALL_BLOCKS: tuple[_Block, ...] = (
    _identity_block,
    _runtime_block,
    _plugins_block,
    _tasks_block,
    _models_block,
    _totals_block,
)
_SECTION_BLOCKS: dict[str, tuple[_Block, ...]] = {
    "identity": (_identity_block,),
    "runtime": (_runtime_block,),
    "plugins": (_plugins_block,),
    "models": (_tasks_block, _models_block),
    "usage": (_models_block, _totals_block),
    "hardware": (_hardware_block,),
}


def _blocks(s: Snapshot, section: str) -> list[str]:
    if section == "all":
        builders = list(_ALL_BLOCKS) + ([_hardware_block] if s.hardware is not None else [])
    else:
        builders = list(_SECTION_BLOCKS[section])
    return [build(s) for build in builders]


def format_tool_text(s: Snapshot, section: Any = "all") -> str:
    key, note = normalize_section(section)
    lines = _blocks(s, key)
    if note:
        lines.append(note)
    if s.failed_sources:
        lines.append(f"（数据源未响应：{'、'.join(s.failed_sources)}）")
    lines.append(REPLY_HINT)
    return "\n".join(lines)


def format_user_text(s: Snapshot) -> str:
    return "\n".join(_blocks(s, "all"))


def format_injection(s: Snapshot) -> str:
    """规划器系统提示词里的自身信息摘要：只含慢变事实，不含计数与时间（保持提示词缓存稳定）。"""

    identity, runtime, usage = s.identity, s.runtime, s.usage
    head: list[str] = []
    if identity.nickname:
        head.append(f"你是「{identity.nickname}」")
    if runtime.host_version:
        running = f"运行在 MaiBot {runtime.host_version}"
        if runtime.sdk_version:
            running += f"（插件 SDK {runtime.sdk_version}）"
        head.append(running)
    elif runtime.sdk_version:
        head.append(f"运行在插件 SDK {runtime.sdk_version} 之上")
    if identity.platforms:
        head.append(f"接入平台：{'、'.join(identity.platforms)}")

    facts: list[str] = []
    if usage.models:
        names = "、".join(model.model_name for model in usage.models[:3])
        facts.append(f"近 {usage.window_days} 天主要使用的模型：{names}")
    if runtime.plugin_count is not None:
        loaded = f"已加载 {runtime.plugin_count} 个插件"
        if runtime.tool_count is not None:
            loaded += f"、{runtime.tool_count} 个工具"
        facts.append(loaded)

    lines: list[str] = []
    if head:
        lines.append("，".join(head) + "。")
    if facts:
        lines.append("；".join(facts) + "。")
    lines.append("需要版本、插件、模型、用量、在线时长等详情时调用 maifetch 工具，不要凭印象回答。")
    return INJECTION_TAG + "\n".join(lines)
