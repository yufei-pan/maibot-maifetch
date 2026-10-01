"""maifetch 配置：配置模型、归一化（补默认 / 数值钳制 / 格式清洗）与运行期设置快照。"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maibot_sdk import Field, PluginConfigBase

CURRENT_CONFIG_VERSION = "1.0.0"
SHIPPED_CONFIG_TEMPLATE_NAME = "config.default.toml"
DEFAULT_TEMPLATE = "assets/dashboard.html"
BUNDLED_TEMPLATES: tuple[str, ...] = ("dashboard", "terminal", "sheet")
VALID_IMAGE_FORMATS: tuple[str, ...] = ("webp", "png")
COMMAND_TRIGGER = "/maifetch"

# (配置节, 字段) → (最小值, 最大值)
NUMERIC_BOUNDS: dict[tuple[str, str], tuple[float, float]] = {
    ("usage", "window_days"): (1, 90),
    ("usage", "top_models"): (1, 10),
    ("injection", "refresh_minutes"): (1, 1440),
    ("command", "cooldown_seconds"): (0, 3600),
    ("card", "scale"): (0.5, 3.0),
    ("card", "render_timeout_ms"): (1000, 45000),
}


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default=CURRENT_CONFIG_VERSION, description="配置版本（插件自动维护，请勿手改）")


class VisibilitySectionConfig(PluginConfigBase):
    """可见性：同时作用于规划器工具、规划器提示词注入与状态卡片。"""

    __ui_label__ = "可见性"
    __ui_icon__ = "eye"
    __ui_order__ = 1

    show_account: bool = Field(default=False, description="显示机器人账号（bot.qq_account）。")
    show_plugin_list: bool = Field(default=True, description="显示已加载插件列表；关闭后仍显示插件数量。")
    show_cost: bool = Field(
        default=True,
        description="显示花费（按模型与合计）。开启后群聊中任何能触发工具或使用 /maifetch 的人都能看到。",
    )


class UsageSectionConfig(PluginConfigBase):
    """用量统计窗口。"""

    __ui_label__ = "用量统计"
    __ui_icon__ = "chart-bar"
    __ui_order__ = 2

    window_days: int = Field(default=7, description="统计最近多少天的用量（1–90）。")
    top_models: int = Field(default=5, description="列出用量最高的前几个模型（1–10）。")


class InjectionSectionConfig(PluginConfigBase):
    """规划器提示词注入。"""

    __ui_label__ = "规划器注入"
    __ui_icon__ = "brain"
    __ui_order__ = 3

    enabled: bool = Field(default=True, description="每次规划前把一段简短的自身信息追加到规划器系统提示词。")
    refresh_minutes: int = Field(default=10, description="后台刷新自身信息摘要的间隔（分钟，1–1440）。")


class CommandSectionConfig(PluginConfigBase):
    """/maifetch 命令。"""

    __ui_label__ = "命令"
    __ui_icon__ = "terminal"
    __ui_order__ = 4

    aliases: list[str] = Field(
        default_factory=list,
        description="/maifetch 之外的额外触发词，按原样匹配（需要斜杠请自己写上，如 /状态）。修改后需重载插件生效。",
    )
    cooldown_seconds: int = Field(default=30, description="同一聊天内发送状态卡片的冷却秒数（0 = 不限制）。")


class CardSectionConfig(PluginConfigBase):
    """状态卡片渲染。"""

    __ui_label__ = "状态卡片"
    __ui_icon__ = "image"
    __ui_order__ = 5

    template: str = Field(
        default=DEFAULT_TEMPLATE,
        description=(
            "卡片 HTML 模板路径：相对插件目录或绝对路径。内置 assets/dashboard.html（默认）、"
            "assets/terminal.html、assets/sheet.html。"
        ),
    )
    scale: float = Field(
        default=1.0,
        description="渲染像素比（0.5–3.0）。越大越清晰、图片越大；过大的图片经 NapCat 发送可能被误报失败。",
    )
    format: str = Field(default="webp", description="图片格式：webp（无损，体积小）或 png。")
    render_timeout_ms: int = Field(default=20000, description="单次渲染超时（毫秒，1000–45000）。")


class HardwareSectionConfig(PluginConfigBase):
    """本机硬件信息展示。"""

    __ui_label__ = "硬件信息"
    __ui_icon__ = "cpu"
    __ui_order__ = 6

    enabled: bool = Field(
        default=True,
        description=(
            "在工具回复与状态卡片中显示本机硬件信息（系统、内核、CPU、内存、磁盘、Python、开机时长、容器 / 虚拟机类型）。"
            "注意：开启后群聊中任何能使用 /maifetch 或触发工具的人都能看到这些机器信息，如不希望暴露请关闭；"
            "下面各项仅在开启时生效。无论如何都不采集主机名、IP、用户名、路径、序列号。"
        ),
    )
    show_os: bool = Field(default=True, description="操作系统名称与版本")
    show_kernel: bool = Field(default=True, description="内核版本")
    show_arch: bool = Field(default=True, description="CPU 架构")
    show_cpu: bool = Field(default=True, description="CPU 型号与逻辑核心数")
    show_memory: bool = Field(default=True, description="内存已用 / 总量")
    show_disk: bool = Field(default=True, description="MaiBot 所在磁盘的已用 / 总量")
    show_python: bool = Field(default=True, description="Python 版本")
    show_uptime: bool = Field(default=True, description="机器开机时长")
    show_virt: bool = Field(default=True, description="容器 / 虚拟机类型（Docker、WSL、KVM…）")


class MaiFetchConfig(PluginConfigBase):
    """插件根配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    visibility: VisibilitySectionConfig = Field(default_factory=VisibilitySectionConfig)
    usage: UsageSectionConfig = Field(default_factory=UsageSectionConfig)
    injection: InjectionSectionConfig = Field(default_factory=InjectionSectionConfig)
    command: CommandSectionConfig = Field(default_factory=CommandSectionConfig)
    card: CardSectionConfig = Field(default_factory=CardSectionConfig)
    hardware: HardwareSectionConfig = Field(default_factory=HardwareSectionConfig)


@dataclass(frozen=True)
class Visibility:
    """可见性开关快照。"""

    show_account: bool
    show_plugin_list: bool
    show_cost: bool


@dataclass(frozen=True)
class HardwareToggles:
    """硬件信息开关快照；enabled 为总开关。"""

    enabled: bool
    os: bool
    kernel: bool
    arch: bool
    cpu: bool
    memory: bool
    disk: bool
    python: bool
    uptime: bool
    virt: bool


@dataclass(frozen=True)
class Settings:
    """运行期设置快照（已规范化）。"""

    enabled: bool
    visibility: Visibility
    window_days: int
    top_models: int
    injection_enabled: bool
    refresh_minutes: int
    aliases: tuple[str, ...]
    cooldown_seconds: int
    template: str
    scale: float
    image_format: str
    render_timeout_ms: int
    hardware: HardwareToggles


def _coerce_number(value: Any, as_float: bool) -> float | int | None:
    """把 WebUI / TOML 写回的值转成数字；无法解析返回 None。"""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if as_float else round(number)


def normalize_config_dict(raw: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """补齐默认值、钳制数值、清洗格式 / 模板 / 别名，并写入当前配置版本。

    Returns:
        (规范化后的配置字典, 变更说明列表)。说明为空表示无需修正。
    """

    notes: list[str] = []
    defaults = MaiFetchConfig().model_dump(mode="python")
    source = dict(raw or {})
    merged: dict[str, Any] = {}
    for section, default_section in defaults.items():
        user_section = source.get(section)
        merged[section] = {**default_section, **(dict(user_section) if isinstance(user_section, Mapping) else {})}

    if merged["plugin"].get("config_version") != CURRENT_CONFIG_VERSION:
        merged["plugin"]["config_version"] = CURRENT_CONFIG_VERSION
        notes.append(f"config_version → {CURRENT_CONFIG_VERSION}")

    for (section, key), (low, high) in NUMERIC_BOUNDS.items():
        default = defaults[section][key]
        as_float = isinstance(default, float)
        number = _coerce_number(merged[section].get(key), as_float)
        if number is None:
            merged[section][key] = default
            notes.append(f"{section}.{key} 无效，已恢复默认 {default}")
            continue
        bounded = min(max(number, low), high)
        bounded = float(bounded) if as_float else int(bounded)
        if bounded != number:
            notes.append(f"{section}.{key} 超出范围 {low}–{high}，已调整为 {bounded}")
        merged[section][key] = bounded

    image_format = str(merged["card"].get("format") or "").strip().lower()
    if image_format not in VALID_IMAGE_FORMATS:
        notes.append(f"card.format 无效（{merged['card'].get('format')!r}），已改为 webp")
        image_format = "webp"
    merged["card"]["format"] = image_format

    template = str(merged["card"].get("template") or "").strip()
    if not template:
        template = DEFAULT_TEMPLATE
        notes.append("card.template 为空，已恢复默认模板")
    merged["card"]["template"] = template

    raw_aliases = merged["command"].get("aliases")
    if isinstance(raw_aliases, str):
        raw_aliases = [raw_aliases]
    aliases: list[str] = []
    for alias in raw_aliases if isinstance(raw_aliases, (list, tuple)) else []:
        text = str(alias).strip()
        if text and text != COMMAND_TRIGGER and text not in aliases:
            aliases.append(text)
    merged["command"]["aliases"] = aliases

    validated = MaiFetchConfig.model_validate(merged)
    return validated.model_dump(mode="python"), notes


def build_settings(config: MaiFetchConfig) -> Settings:
    """从强类型配置构建运行期设置；先再规范化一次，保证数值在范围内。"""

    normalized, _ = normalize_config_dict(config.model_dump(mode="python"))
    cfg = MaiFetchConfig.model_validate(normalized)
    hw = cfg.hardware
    return Settings(
        enabled=cfg.plugin.enabled,
        visibility=Visibility(
            show_account=cfg.visibility.show_account,
            show_plugin_list=cfg.visibility.show_plugin_list,
            show_cost=cfg.visibility.show_cost,
        ),
        window_days=cfg.usage.window_days,
        top_models=cfg.usage.top_models,
        injection_enabled=cfg.injection.enabled,
        refresh_minutes=cfg.injection.refresh_minutes,
        aliases=tuple(cfg.command.aliases),
        cooldown_seconds=cfg.command.cooldown_seconds,
        template=cfg.card.template,
        scale=cfg.card.scale,
        image_format=cfg.card.format,
        render_timeout_ms=cfg.card.render_timeout_ms,
        hardware=HardwareToggles(
            enabled=hw.enabled,
            os=hw.show_os,
            kernel=hw.show_kernel,
            arch=hw.show_arch,
            cpu=hw.show_cpu,
            memory=hw.show_memory,
            disk=hw.show_disk,
            python=hw.show_python,
            uptime=hw.show_uptime,
            virt=hw.show_virt,
        ),
    )


def ensure_shipped_config_present(plugin_dir: Path) -> bool:
    """若缺少运行期 config.toml，从 config.default.toml 复制一份（带注释）。

    必须在 create_plugin 阶段调用：Runner 在 on_load 之前读取配置，晚了会先写出无注释的默认值。
    """

    config_path = plugin_dir / "config.toml"
    template_path = plugin_dir / SHIPPED_CONFIG_TEMPLATE_NAME
    if config_path.exists() or not template_path.exists():
        return False
    shutil.copy2(template_path, config_path)
    return True
