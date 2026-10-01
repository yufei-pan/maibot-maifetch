"""把自身信息摘要追加到规划器系统提示词（Item-first 载荷 schema v1，兼容旧 messages 载荷）。

只追加到第一条系统消息；找不到就什么都不做（不凭空造消息）。重复调用不会重复追加。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CONTEXT_ITEM_SCHEMA_VERSION = 1


def _part_texts(parts: list[Any]) -> str:
    return "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))


def inject_into_items(items: list[Any], text: str) -> tuple[list[Any], bool]:
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("item_type") != "SystemMessageItem":
            continue
        parts = item.get("parts")
        if not isinstance(parts, list) or text in _part_texts(parts):
            return items, False
        out = deepcopy(items)
        out[index]["parts"].append({"type": "text", "text": "\n\n" + text})
        return out, True
    return items, False


def inject_into_messages(messages: list[Any], text: str) -> tuple[list[Any], bool]:
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != "system":
            continue
        content = message.get("content")
        out = deepcopy(messages)
        if isinstance(content, str):
            if text in content:
                return messages, False
            out[index]["content"] = content + "\n\n" + text
            return out, True
        if isinstance(content, list):
            if text in _part_texts(content):
                return messages, False
            out[index]["content"].append({"type": "text", "text": "\n\n" + text})
            return out, True
        return messages, False
    return messages, False


def apply_injection(kwargs: dict[str, Any], text: str) -> bool:
    """按载荷形态注入；有改动时就地替换 kwargs 中的列表并返回 True。"""

    items = kwargs.get("items")
    if isinstance(items, list):
        if kwargs.get("item_schema_version") != CONTEXT_ITEM_SCHEMA_VERSION:
            return False
        new_items, changed = inject_into_items(items, text)
        if changed:
            kwargs["items"] = new_items
        return changed
    messages = kwargs.get("messages")
    if isinstance(messages, list):
        new_messages, changed = inject_into_messages(messages, text)
        if changed:
            kwargs["messages"] = new_messages
        return changed
    return False
