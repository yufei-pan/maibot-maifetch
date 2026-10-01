from __future__ import annotations

import re

import pytest

from maifetch.registration import (
    COMMAND_COMPONENT_NAME,
    TOOL_NAME,
    build_command_pattern,
    parse_command_arg,
    patch_components,
    tool_description,
)


def test_tool_description_mentions_window() -> None:
    assert "近 14 天" in tool_description(14)
    assert tool_description(7).startswith("【maifetch·自身信息】")


@pytest.mark.parametrize(
    ("text", "arg"),
    [("/maifetch", None), ("/maifetch 文字", "文字"), ("/maifetch  terminal ", "terminal"), ("/状态 sheet", "sheet")],
)
def test_command_pattern_matches(text: str, arg: str | None) -> None:
    match = re.compile(build_command_pattern(["/状态"])).search(text)
    assert match is not None
    assert match.groupdict().get("arg") == arg


@pytest.mark.parametrize("text", ["/maifetchx", "hey /maifetch", "/maifetch a b", "/状态", "maifetch"])
def test_command_pattern_rejects(text: str) -> None:
    assert re.compile(build_command_pattern([])).search(text) is None


def test_alias_is_escaped() -> None:
    pattern = re.compile(build_command_pattern(["/s.t"]))
    assert pattern.search("/s.t") is not None
    assert pattern.search("/sxt") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ("card", None)),
        ("", ("card", None)),
        ("文字", ("text", None)),
        ("TEXT", ("text", None)),
        ("Terminal", ("card", "terminal")),
        ("sheet", ("card", "sheet")),
        ("帮助", ("help", None)),
        ("../../etc/passwd", ("help", None)),
    ],
)
def test_parse_command_arg(raw: str | None, expected: tuple[str, str | None]) -> None:
    assert parse_command_arg(raw) == expected


def test_patch_components() -> None:
    components = [
        {"name": TOOL_NAME, "type": "TOOL", "metadata": {"description": "old", "brief_description": "old"}},
        {"name": COMMAND_COMPONENT_NAME, "type": "COMMAND", "metadata": {"command_pattern": "^/maifetch"}},
        {"name": "other", "type": "HOOK_HANDLER", "metadata": {"description": "keep"}},
    ]
    patch_components(components, window_days=30, aliases=["/状态"])
    assert "近 30 天" in components[0]["metadata"]["description"]
    assert components[0]["metadata"]["brief_description"] == components[0]["metadata"]["description"]
    assert re.compile(components[1]["metadata"]["command_pattern"]).search("/状态") is not None
    assert components[2]["metadata"]["description"] == "keep"
