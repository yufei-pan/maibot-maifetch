from __future__ import annotations

from maifetch.inject import apply_injection, inject_into_items, inject_into_messages

TEXT = "【maifetch·自身信息】你是「麦麦」。"


def _items() -> list[dict]:
    return [
        {"item_type": "SystemMessageItem", "parts": [{"type": "text", "text": "系统提示"}]},
        {"item_type": "UserMessageItem", "parts": [{"type": "text", "text": "你好"}]},
    ]


def test_inject_into_first_system_item() -> None:
    original = _items()
    out, changed = inject_into_items(original, TEXT)
    assert changed is True
    assert out[0]["parts"][-1] == {"type": "text", "text": "\n\n" + TEXT}
    assert len(original[0]["parts"]) == 1  # 原列表不被修改
    assert out[1] == original[1]


def test_inject_items_without_system_is_noop() -> None:
    items = [{"item_type": "UserMessageItem", "parts": [{"type": "text", "text": "hi"}]}]
    out, changed = inject_into_items(items, TEXT)
    assert changed is False and out is items


def test_inject_items_is_idempotent() -> None:
    once, _ = inject_into_items(_items(), TEXT)
    twice, changed = inject_into_items(once, TEXT)
    assert changed is False
    assert twice is once


def test_inject_into_legacy_messages() -> None:
    out, changed = inject_into_messages([{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}], TEXT)
    assert changed is True and out[0]["content"] == "sys\n\n" + TEXT
    out, changed = inject_into_messages([{"role": "system", "content": [{"type": "text", "text": "sys"}]}], TEXT)
    assert changed is True and out[0]["content"][-1]["text"] == "\n\n" + TEXT
    _, changed = inject_into_messages([{"role": "user", "content": "u"}], TEXT)
    assert changed is False


def test_apply_injection_dispatch() -> None:
    kwargs = {"items": _items(), "item_schema_version": 1, "tool_definitions": []}
    assert apply_injection(kwargs, TEXT) is True
    assert TEXT in kwargs["items"][0]["parts"][-1]["text"]

    legacy = {"messages": [{"role": "system", "content": "sys"}]}
    assert apply_injection(legacy, TEXT) is True

    unknown_version = {"items": _items(), "item_schema_version": 2}
    assert apply_injection(unknown_version, TEXT) is False
    assert apply_injection({}, TEXT) is False
