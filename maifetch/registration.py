"""组件注册期的动态内容：工具描述（含统计窗口）、命令正则（含别名）与命令参数解析。

@Tool / @Command 的元数据在导入时就固定了；插件在 get_components() 里用当前配置修补它们
（Host 先注入配置、再调用 get_components、最后 on_load）。别名与窗口变更需重载插件生效。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from maifetch.config import BUNDLED_TEMPLATES, COMMAND_TRIGGER

TOOL_NAME = "maifetch"
COMMAND_COMPONENT_NAME = "maifetch_card"

SECTION_PARAM_DESCRIPTION = (
    "要查看的部分：all=全部（默认）、identity=身份、runtime=运行与版本、plugins=插件与工具、"
    "models=模型任务与用量、usage=用量统计、hardware=硬件（需运维开启）。也接受中文：全部/身份/版本/插件/模型/用量/硬件。"
)
SEND_CARD_PARAM_DESCRIPTION = "为 true 时同时把状态卡片图片发到当前聊天（同一聊天有冷却时间）。默认 false。"
HELP_TEXT = (
    "maifetch（麦麦状态）用法：\n"
    "/maifetch — 发送状态卡片\n"
    "/maifetch 文字 — 发送文字版\n"
    "/maifetch dashboard | terminal | sheet — 用指定内置模板出图"
)
_TEXT_ARGS = frozenset({"文字", "文本", "text", "txt"})


def tool_description(window_days: int) -> str:
    return (
        "【maifetch·自身信息】查询麦麦自身的运行信息：版本、接入平台、已加载插件与工具、已配置模型任务、"
        f"近 {window_days} 天模型用量、本次在线时长（运维开启时含硬件信息）。"
        "用户问到你是什么模型/什么版本/装了什么插件/能不能做某事/跑了多久/用了多少 token 时调用，不要凭印象回答。"
        "send_card=true 时直接把状态卡片图发到当前聊天。"
    )


def build_command_pattern(aliases: Sequence[str]) -> str:
    triggers = [COMMAND_TRIGGER, *[alias for alias in aliases if alias and alias != COMMAND_TRIGGER]]
    alternatives = "|".join(re.escape(trigger) for trigger in triggers)
    return rf"^(?:{alternatives})(?:\s+(?P<arg>\S+))?\s*$"


def parse_command_arg(raw: Any) -> tuple[str, str | None]:
    """返回 (动作, 内置模板名)。动作：card / text / help；无法识别的参数一律给用法说明。"""

    arg = str(raw or "").strip()
    if not arg:
        return "card", None
    lowered = arg.lower()
    if lowered in _TEXT_ARGS:
        return "text", None
    if lowered in BUNDLED_TEMPLATES:
        return "card", lowered
    return "help", None


def patch_components(components: list[dict[str, Any]], *, window_days: int, aliases: Sequence[str]) -> None:
    for component in components:
        metadata = component.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if component.get("name") == TOOL_NAME:
            description = tool_description(window_days)
            metadata["description"] = description
            metadata["brief_description"] = description
        elif component.get("name") == COMMAND_COMPONENT_NAME:
            metadata["command_pattern"] = build_command_pattern(aliases)
