"""隐藏字段不得出现在任何输出面（工具文字、用户文字、注入、标量、片段、data_json、整页 HTML）。"""

from __future__ import annotations

import pytest
from fakes import make_settings

from maifetch.card import PLACEHOLDER_KEYS, build_card_html, build_data_json, build_fragments, build_scalars
from maifetch.redact import apply_visibility
from maifetch.sample import sample_snapshot
from maifetch.text import format_injection, format_tool_text, format_user_text

ALL_PLACEHOLDERS_TEMPLATE = '<div id="card">' + "|".join("{" + key + "}" for key in sorted(PLACEHOLDER_KEYS)) + "</div>"


def _surfaces(overrides: dict) -> str:
    settings = make_settings(overrides)
    raw = sample_snapshot(hardware=True, cost=True, account=True)
    snap = apply_visibility(raw, settings.visibility, settings.hardware)
    parts = [
        format_tool_text(snap, "all"),
        format_tool_text(snap, "hardware"),
        format_user_text(snap),
        format_injection(snap),
        *build_scalars(snap).values(),
        *build_fragments(snap).values(),
        build_data_json(snap),
        build_card_html(snap, ALL_PLACEHOLDERS_TEMPLATE),
    ]
    return "\n".join(parts)


@pytest.mark.parametrize(
    ("overrides", "secrets"),
    [
        ({}, ["123456789"]),
        (
            {"visibility": {"show_cost": False}, "hardware": {"enabled": False}},
            ["123456789", "¥", "3.42", "4.87", "Ryzen", "Debian", "6.8.12-pve", "Docker"],
        ),
        ({"visibility": {"show_plugin_list": False}}, ["fetch-url", "corpus-callosum"]),
        ({"hardware": {"enabled": True, "show_cpu": False, "show_virt": False}}, ["Ryzen", "Docker"]),
    ],
)
def test_hidden_values_never_leak(overrides: dict, secrets: list[str]) -> None:
    text = _surfaces(overrides)
    for secret in secrets:
        assert secret not in text, secret


def test_visible_values_do_appear() -> None:
    text = _surfaces(
        {"visibility": {"show_account": True, "show_cost": True}, "hardware": {"enabled": True, "show_cpu": False}}
    )
    for expected in ("123456789", "¥4.87", "Debian", "fetch-url"):
        assert expected in text
