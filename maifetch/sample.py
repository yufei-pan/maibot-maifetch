"""示例快照：单元测试与模板预览共用（数据为虚构示例）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from maifetch.snapshot import Hardware, Identity, ModelUsage, PluginInfo, Runtime, Snapshot, Usage

SAMPLE_PLUGINS: tuple[tuple[str, str], ...] = (
    ("com.0-hz.corpus-callosum", "1.3.4"),
    ("com.0-hz.email-adapter", "0.1.2"),
    ("com.0-hz.fetch-url", "0.4.1"),
    ("com.0-hz.image-recompress", "0.2.5"),
    ("com.0-hz.impression-card", "0.3.3"),
    ("com.0-hz.maibook", "0.1.3"),
    ("com.0-hz.maifetch", "0.1.0"),
    ("com.0-hz.maitrpg", "0.1.1"),
    ("com.0-hz.plastic-memory", "0.4.6"),
    ("com.0-hz.rss-reader", "0.4.3"),
    ("com.0-hz.world-clock", "0.1.1"),
    ("maibot-team.napcat-adapter", "1.5.0"),
)

_CST = timezone(timedelta(hours=8), "CST")


def sample_snapshot(*, hardware: bool = True, cost: bool = False, account: bool = False) -> Snapshot:
    """构造示例快照。cost / account 为 False 时对应字段为 None（相当于已脱敏）。"""

    now = datetime(2026, 10, 1, 14, 24, tzinfo=_CST)
    models = (
        ModelUsage("deepseek-v3.2", 1284, 1_860_000, 2.1, 3.42 if cost else None),
        ModelUsage("qwen3-235b", 402, 410_000, 3.4, 0.96 if cost else None),
        ModelUsage("glm-4.6v", 88, 140_000, 4.0, 0.49 if cost else None),
    )
    return Snapshot(
        collected_at=now,
        identity=Identity(
            nickname="麦麦",
            alias_names=("小麦",),
            platforms=("qq", "email"),
            account="123456789" if account else None,
            local_time=now,
            timezone="Asia/Shanghai",
        ),
        runtime=Runtime(
            host_version="1.3.1",
            sdk_version="2.8.2",
            plugin_version="0.1.0",
            online_since=now - timedelta(days=3, hours=4, minutes=22),
            plugins=tuple(PluginInfo(pid, version) for pid, version in SAMPLE_PLUGINS),
            plugin_count=len(SAMPLE_PLUGINS),
            tool_count=31,
            model_tasks=("replyer", "planner", "utils", "vlm", "voice"),
        ),
        usage=Usage(
            window_days=7,
            models=models,
            total_requests=1774,
            total_tokens=2_410_000,
            total_cost=4.87 if cost else None,
            total_messages=3906,
        ),
        hardware=Hardware(
            os="Debian GNU/Linux 12 (bookworm)",
            kernel="6.8.12-pve",
            arch="x86_64",
            cpu="AMD Ryzen 9 7950X 16-Core Processor",
            cpu_cores=32,
            mem_used=12_025_908_428,
            mem_total=67_216_478_208,
            disk_used=229_780_750_336,
            disk_total=1_006_093_877_248,
            python="3.12.7",
            uptime_s=12 * 86400 + 3 * 3600,
            virt="Docker/容器",
        )
        if hardware
        else None,
    )
