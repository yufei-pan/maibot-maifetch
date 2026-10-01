"""自身信息快照的数据结构。字段为 None 表示「未知」或「已按可见性隐藏」。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Identity:
    nickname: str | None = None
    alias_names: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    account: str | None = None
    local_time: datetime | None = None
    timezone: str | None = None


@dataclass(frozen=True)
class PluginInfo:
    plugin_id: str
    version: str = ""


@dataclass(frozen=True)
class Runtime:
    host_version: str | None = None
    sdk_version: str | None = None
    plugin_version: str = ""
    online_since: datetime | None = None
    plugins: tuple[PluginInfo, ...] | None = None
    plugin_count: int | None = None
    tool_count: int | None = None
    model_tasks: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ModelUsage:
    model_name: str
    requests: int = 0
    tokens: int = 0
    avg_latency_s: float | None = None
    cost: float | None = None


@dataclass(frozen=True)
class Usage:
    window_days: int = 7
    models: tuple[ModelUsage, ...] = ()  # 只是调用次数最多的前 top_models 个
    model_count: int | None = None  # 统计窗口内有调用记录的模型总数（合计覆盖全部这些模型）
    models_by_cost: tuple[ModelUsage, ...] = ()  # 花费最高的前 top_models 个（只含花费 > 0 的模型）
    costed_model_count: int | None = None  # 有花费记录的模型数
    show_request_ranking: bool = True  # 是否展示调用次数排行（配置开关）
    show_cost_ranking: bool = True  # 是否展示花费排行（配置开关且允许显示花费）
    total_requests: int | None = None
    total_tokens: int | None = None
    total_cost: float | None = None
    totals_capped: bool = False
    total_messages: int | None = None
    messages_capped: bool = False


@dataclass(frozen=True)
class Hardware:
    os: str | None = None
    kernel: str | None = None
    arch: str | None = None
    cpu: str | None = None
    cpu_cores: int | None = None
    mem_used: int | None = None
    mem_total: int | None = None
    disk_used: int | None = None
    disk_total: int | None = None
    python: str | None = None
    uptime_s: float | None = None
    virt: str | None = None


@dataclass(frozen=True)
class Snapshot:
    collected_at: datetime
    identity: Identity = field(default_factory=Identity)
    runtime: Runtime = field(default_factory=Runtime)
    usage: Usage = field(default_factory=Usage)
    hardware: Hardware | None = None
    failed_sources: tuple[str, ...] = ()

    def uptime_seconds(self) -> float | None:
        """本次在线时长（秒）；未知返回 None，时钟偏差导致的负数按 0 处理。"""

        since = self.runtime.online_since
        if since is None:
            return None
        return max(0.0, (self.collected_at - since).total_seconds())


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def snapshot_to_dict(snapshot: Snapshot) -> dict[str, Any]:
    """转成可 JSON 序列化的字典（时间转 ISO 字符串、元组转列表）。"""

    return _jsonable(asdict(snapshot))
