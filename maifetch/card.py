"""状态卡片 HTML：标量占位符、预渲染片段、data_json 与单遍替换。

模板里写「花括号 + 名称」作为占位符；替换只做一遍，值里出现的花括号不会被再次展开。
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping

from maifetch.fmt import (
    UNKNOWN,
    capped,
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
from maifetch.logo import maimai_svg
from maifetch.snapshot import Hardware, Snapshot, snapshot_to_dict

MAX_PLUGIN_CHIPS = 8
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
_SEPARATOR = "──────────────────────"

SCALAR_KEYS: tuple[str, ...] = (
    "nickname",
    "nickname_initial",
    "alias_names",
    "platforms",
    "account",
    "local_time",
    "timezone",
    "host_version",
    "sdk_version",
    "plugin_version",
    "uptime",
    "uptime_short",
    "online_since",
    "plugin_count",
    "tool_count",
    "model_tasks",
    "window_days",
    "total_requests",
    "total_tokens",
    "total_cost",
    "total_messages",
    "top_model",
    "top_model_more",
    "hw_os",
    "hw_kernel",
    "hw_arch",
    "hw_cpu",
    "hw_memory",
    "hw_disk",
    "hw_python",
    "hw_uptime",
    "hw_virt",
    "generated_at",
)
FRAGMENT_KEYS: tuple[str, ...] = (
    "tiles_html",
    "model_rows_html",
    "plugin_list_html",
    "hardware_block_html",
    "hardware_lines_html",
    "identity_rows_html",
    "runtime_rows_html",
    "model_table_rows_html",
    "hardware_table_html",
    "maimai_logo_svg",
)
PLACEHOLDER_KEYS: frozenset[str] = frozenset(SCALAR_KEYS + FRAGMENT_KEYS + ("data_json",))


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _v(value: object, *, hideable: bool = False) -> str:
    """标量取值：可隐藏字段缺失时为空串，其余缺失显示「未知」。"""

    if value is None or value == "":
        return "" if hideable else UNKNOWN
    return _e(str(value))


def short_plugin_name(plugin_id: str) -> str:
    return plugin_id.rsplit(".", 1)[-1] or plugin_id


def _cpu_text(hw: Hardware) -> str | None:
    if not hw.cpu:
        return None
    return hw.cpu + (f" ({hw.cpu_cores})" if hw.cpu_cores else "")


def build_scalars(s: Snapshot) -> dict[str, str]:
    identity, runtime, usage, hw = s.identity, s.runtime, s.usage, s.hardware
    uptime = s.uptime_seconds()
    totals_known = usage.total_requests is not None
    more = len(usage.models) - 1 if usage.models else 0
    return {
        "nickname": _v(identity.nickname),
        "nickname_initial": _e(identity.nickname[0]) if identity.nickname else "麦",
        "alias_names": _e("、".join(identity.alias_names)),
        "platforms": _v("、".join(identity.platforms)),
        "account": _v(identity.account, hideable=True),
        "local_time": _v(fmt_datetime(identity.local_time) if identity.local_time else None),
        "timezone": _v(identity.timezone),
        "host_version": _v(runtime.host_version),
        "sdk_version": _v(runtime.sdk_version),
        "plugin_version": _v(runtime.plugin_version),
        "uptime": _v(fmt_duration_zh(uptime) if uptime is not None else None),
        "uptime_short": _v(fmt_duration_short(uptime) if uptime is not None else None),
        "online_since": _v(fmt_short_datetime(runtime.online_since) if runtime.online_since else None),
        "plugin_count": _v(runtime.plugin_count),
        "tool_count": _v(runtime.tool_count),
        "model_tasks": _v("、".join(runtime.model_tasks) if runtime.model_tasks else None),
        "window_days": _e(str(usage.window_days)),
        "total_requests": _v(capped(fmt_int(usage.total_requests), usage.totals_capped) if totals_known else None),
        "total_tokens": _v(
            capped(fmt_tokens(usage.total_tokens or 0), usage.totals_capped) if totals_known else None
        ),
        "total_cost": _v(
            capped(fmt_cost(usage.total_cost), usage.totals_capped) if usage.total_cost is not None else None,
            hideable=True,
        ),
        "total_messages": _v(
            capped(fmt_int(usage.total_messages), usage.messages_capped) if usage.total_messages is not None else None
        ),
        "top_model": _v(usage.models[0].model_name if usage.models else None),
        "top_model_more": f"(+{more})" if more > 0 else "",
        "hw_os": _v(hw.os if hw else None, hideable=True),
        "hw_kernel": _v(hw.kernel if hw else None, hideable=True),
        "hw_arch": _v(hw.arch if hw else None, hideable=True),
        "hw_cpu": _v(_cpu_text(hw) if hw else None, hideable=True),
        "hw_memory": _v(fmt_used_total(hw.mem_used, hw.mem_total) if hw else None, hideable=True),
        "hw_disk": _v(fmt_used_total(hw.disk_used, hw.disk_total) if hw else None, hideable=True),
        "hw_python": _v(hw.python if hw else None, hideable=True),
        "hw_uptime": _v(fmt_duration_zh(hw.uptime_s) if hw and hw.uptime_s is not None else None, hideable=True),
        "hw_virt": _v(hw.virt if hw else None, hideable=True),
        "generated_at": _e(fmt_datetime(s.collected_at)),
    }


def _tiles(s: Snapshot) -> str:
    usage, runtime = s.usage, s.runtime
    uptime = s.uptime_seconds()
    known = usage.total_requests is not None
    tool_label = runtime.tool_count if runtime.tool_count is not None else UNKNOWN
    tiles = [
        (fmt_duration_short(uptime) if uptime is not None else UNKNOWN, "本次在线"),
        (fmt_int(runtime.plugin_count) if runtime.plugin_count is not None else UNKNOWN, f"插件 · {tool_label} 工具"),
        (
            capped(fmt_tokens(usage.total_tokens or 0), usage.totals_capped) if known else UNKNOWN,
            f"tokens · {usage.window_days} 天",
        ),
    ]
    if usage.total_cost is not None:
        tiles.append((capped(fmt_cost(usage.total_cost), usage.totals_capped), f"花费 · {usage.window_days} 天"))
    else:
        tiles.append(
            (
                capped(fmt_int(usage.total_requests), usage.totals_capped) if known else UNKNOWN,
                f"请求 · {usage.window_days} 天",
            )
        )
    return "".join(f'<div class="mf-tile"><b>{_e(value)}</b><span>{_e(label)}</span></div>' for value, label in tiles)


def _model_rows(s: Snapshot) -> str:
    usage = s.usage
    if usage.total_requests is None:
        return f'<div class="mf-empty">{UNKNOWN}</div>'
    if not usage.models:
        return f'<div class="mf-empty">近 {usage.window_days} 天暂无模型调用记录</div>'
    top = max(model.requests for model in usage.models) or 1
    rows: list[str] = []
    for model in usage.models:
        pct = round(model.requests / top * 100)
        cost = f'<span class="mf-model-cost">{_e(fmt_cost(model.cost))}</span>' if model.cost is not None else ""
        rows.append(
            '<div class="mf-model-row">'
            f'<span class="mf-model-name">{_e(model.model_name)}</span>'
            f'<div class="mf-model-bar"><i style="width:{pct}%"></i></div>'
            f'<span class="mf-model-req">{_e(fmt_int(model.requests))} 次</span>'
            f'<span class="mf-model-tok">{_e(fmt_tokens(model.tokens))}</span>'
            f"{cost}</div>"
        )
    return "".join(rows)


def _plugin_chips(s: Snapshot) -> str:
    plugins = s.runtime.plugins
    if not plugins:
        return ""
    chips = [f'<span class="mf-chip">{_e(short_plugin_name(p.plugin_id))}</span>' for p in plugins[:MAX_PLUGIN_CHIPS]]
    extra = len(plugins) - MAX_PLUGIN_CHIPS
    if extra > 0:
        chips.append(f'<span class="mf-chip mf-more">+{extra}</span>')
    return "".join(chips)


def _hw_rows(hw: Hardware) -> list[tuple[str, str]]:
    candidates = [
        ("系统", hw.os),
        ("架构", hw.arch),
        ("内核", hw.kernel),
        ("虚拟化", hw.virt),
        ("CPU", _cpu_text(hw)),
        ("内存", fmt_used_total(hw.mem_used, hw.mem_total)),
        ("磁盘", fmt_used_total(hw.disk_used, hw.disk_total)),
        ("Python", hw.python),
        ("开机", fmt_duration_zh(hw.uptime_s) if hw.uptime_s is not None else None),
    ]
    return [(label, value) for label, value in candidates if value]


def _terminal_hw_lines(hw: Hardware) -> list[tuple[str, str]]:
    os_text = " ".join(part for part in (hw.os, hw.arch) if part) or None
    candidates = [
        ("OS", os_text),
        ("Kernel", hw.kernel),
        ("Virt", hw.virt),
        ("CPU", _cpu_text(hw)),
        ("Memory", fmt_used_total(hw.mem_used, hw.mem_total)),
        ("Disk", fmt_used_total(hw.disk_used, hw.disk_total)),
        ("Python", hw.python),
        ("Uptime", fmt_duration_short(hw.uptime_s) if hw.uptime_s is not None else None),
    ]
    return [(key, value) for key, value in candidates if value]


def _hardware_block(s: Snapshot) -> str:
    rows = _hw_rows(s.hardware) if s.hardware else []
    if not rows:
        return ""
    body = "".join(
        f'<div class="mf-hw-row"><span class="mf-k">{_e(k)}</span><span class="mf-v">{_e(v)}</span></div>'
        for k, v in rows
    )
    return f'<div class="mf-hw"><div class="mf-hw-title">硬件</div><div class="mf-hw-grid">{body}</div></div>'


def _hardware_lines(s: Snapshot) -> str:
    lines = _terminal_hw_lines(s.hardware) if s.hardware else []
    if not lines:
        return ""
    return f'<div class="dim">{_SEPARATOR}</div>' + "".join(
        f'<div><span class="k">{_e(k)}</span>: {_e(v)}</div>' for k, v in lines
    )


def _tr(label: str, value: str) -> str:
    return f"<tr><td>{_e(label)}</td><td>{_e(value)}</td></tr>"


def _identity_rows(s: Snapshot) -> str:
    identity = s.identity
    rows = [_tr("昵称", identity.nickname or UNKNOWN)]
    if identity.alias_names:
        rows.append(_tr("别名", "、".join(identity.alias_names)))
    rows.append(_tr("平台", "、".join(identity.platforms) if identity.platforms else UNKNOWN))
    if identity.account:
        rows.append(_tr("账号", identity.account))
    if identity.local_time:
        zone = f" {identity.timezone}" if identity.timezone else ""
        rows.append(_tr("本地时间", fmt_datetime(identity.local_time) + zone))
    return "".join(rows)


def _runtime_rows(s: Snapshot) -> str:
    runtime = s.runtime
    uptime = s.uptime_seconds()
    if uptime is not None and runtime.online_since is not None:
        online = f"{fmt_duration_zh(uptime)}（自 {fmt_short_datetime(runtime.online_since)}）"
    else:
        online = UNKNOWN
    rows = [_tr("本次在线", online)]
    if runtime.plugin_count is not None:
        tools = runtime.tool_count if runtime.tool_count is not None else UNKNOWN
        rows.append(_tr("插件", f"{runtime.plugin_count} 个 · {tools} 个工具"))
    else:
        rows.append(_tr("插件", UNKNOWN))
    if runtime.plugins:
        rows.append(_tr("插件列表", "、".join(short_plugin_name(p.plugin_id) for p in runtime.plugins)))
    rows.append(_tr("模型任务", "、".join(runtime.model_tasks) if runtime.model_tasks else UNKNOWN))
    return "".join(rows)


def _model_table_rows(s: Snapshot) -> str:
    usage = s.usage
    if usage.total_requests is None:
        return _tr("模型", UNKNOWN)
    rows: list[str] = []
    for model in usage.models:
        bits = [f"{fmt_int(model.requests)} 次", f"{fmt_tokens(model.tokens)} tok"]
        if model.avg_latency_s is not None:
            bits.append(fmt_latency(model.avg_latency_s))
        if model.cost is not None:
            bits.append(fmt_cost(model.cost))
        rows.append(_tr(model.model_name, " · ".join(bits)))
    if not usage.models:
        rows.append(_tr("模型", f"近 {usage.window_days} 天暂无调用记录"))
    totals = [
        f"{capped(fmt_int(usage.total_requests), usage.totals_capped)} 次",
        f"{capped(fmt_tokens(usage.total_tokens or 0), usage.totals_capped)} tok",
    ]
    if usage.total_messages is not None:
        totals.append(f"消息 {capped(fmt_int(usage.total_messages), usage.messages_capped)} 条")
    if usage.total_cost is not None:
        totals.append(capped(fmt_cost(usage.total_cost), usage.totals_capped))
    rows.append(_tr("合计", " · ".join(totals)))
    return "".join(rows)


def _hardware_table(s: Snapshot) -> str:
    rows = _hw_rows(s.hardware) if s.hardware else []
    if not rows:
        return ""
    return '<div class="sec">硬件</div><table>' + "".join(_tr(k, v) for k, v in rows) + "</table>"


def build_fragments(s: Snapshot) -> dict[str, str]:
    return {
        "tiles_html": _tiles(s),
        "model_rows_html": _model_rows(s),
        "plugin_list_html": _plugin_chips(s),
        "hardware_block_html": _hardware_block(s),
        "hardware_lines_html": _hardware_lines(s),
        "identity_rows_html": _identity_rows(s),
        "runtime_rows_html": _runtime_rows(s),
        "model_table_rows_html": _model_table_rows(s),
        "hardware_table_html": _hardware_table(s),
        "maimai_logo_svg": maimai_svg(),
    }


def build_data_json(s: Snapshot) -> str:
    """脱敏后的完整快照 JSON；转义 < 与 >，可安全放进 <script> 或 HTML 注释。"""

    return (
        json.dumps(snapshot_to_dict(s), ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    )


def fill_template(template: str, values: Mapping[str, str]) -> str:
    """单遍替换已知占位符；未知的花括号内容（CSS、JS）原样保留。"""

    return _PLACEHOLDER_RE.sub(lambda match: values.get(match.group(1), match.group(0)), template)


def build_card_html(s: Snapshot, template: str, font_css: str = "") -> str:
    values = {**build_scalars(s), **build_fragments(s), "data_json": build_data_json(s)}
    body = fill_template(template, values)
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"{font_css}"
        "<style>html,body{margin:0;padding:0;background:transparent;}</style>"
        f"</head><body>{body}</body></html>"
    )
