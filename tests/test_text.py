from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from maifetch.sample import sample_snapshot
from maifetch.snapshot import Snapshot
from maifetch.text import (
    INJECTION_TAG,
    REPLY_HINT,
    format_injection,
    format_tool_text,
    format_user_text,
    normalize_section,
    parse_bool,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("是", True),
        ("1", True),
        (1, True),
        ("false", False),
        ("0", False),
        ("否", False),
        ("", False),
        (None, False),
    ],
)
def test_parse_bool(value: object, expected: bool) -> None:
    assert parse_bool(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "all"),
        ("", "all"),
        ("ALL", "all"),
        ("全部", "all"),
        ("模型", "models"),
        ("用量", "usage"),
        ("token", "usage"),
        ("插件", "plugins"),
        ("版本", "runtime"),
        ("身份", "identity"),
        ("硬件", "hardware"),
    ],
)
def test_normalize_section(value: object, expected: str) -> None:
    key, note = normalize_section(value)
    assert key == expected
    assert note is None


def test_unknown_section_falls_back_with_note() -> None:
    key, note = normalize_section("weather")
    assert key == "all"
    assert note is not None and "weather" in note


def test_tool_text_all_blocks_and_hint() -> None:
    text = format_tool_text(sample_snapshot(), "all")
    for tag in (
        "【身份】",
        "【运行】",
        "【插件】",
        "【模型任务】",
        "【模型用量·近 7 天】",
        "【合计·近 7 天（全部模型）】",
        "【硬件】",
    ):
        assert tag in text
    assert "昵称：麦麦（别名：小麦）" in text
    assert "MaiBot 1.3.1 · 插件 SDK 2.8.2 · maifetch 0.1.0" in text
    assert "本次在线 3 天 4 小时（自 09-28 10:02）" in text
    assert "12 个已加载、31 个工具：com.0-hz.corpus-callosum@1.3.4" in text
    assert "deepseek-v3.2 1,284 次/1.86M tok/2.1s" in text
    assert "【合计·近 7 天（全部模型）】1,774 次请求、2.41M tokens、3,906 条消息" in text
    assert text.splitlines()[-1] == REPLY_HINT


def test_tool_text_section_filter() -> None:
    text = format_tool_text(sample_snapshot(), "模型")
    assert "【模型任务】" in text and "【模型用量·近 7 天】" in text
    assert "【身份】" not in text and "【合计" not in text


def test_tool_text_hardware_disabled_message() -> None:
    text = format_tool_text(sample_snapshot(hardware=False), "hardware")
    assert "【硬件】运维未开启硬件信息" in text


def test_tool_text_reports_failed_sources_and_unknowns() -> None:
    snap = Snapshot(collected_at=sample_snapshot().collected_at, failed_sources=("models", "plugins"))
    text = format_tool_text(snap)
    assert "（数据源未响应：models、plugins）" in text
    assert "【插件】未知" in text
    assert "【模型用量·近 7 天】未知" in text


def test_capped_totals_show_plus() -> None:
    snap = sample_snapshot()
    snap = replace(snap, usage=replace(snap.usage, totals_capped=True, messages_capped=True))
    assert "1,774+ 次请求、2.41M+ tokens、3,906+ 条消息" in format_tool_text(snap)


def test_cost_shown_only_when_present() -> None:
    assert "¥" not in format_tool_text(sample_snapshot())
    assert "花费 ¥4.87" in format_tool_text(sample_snapshot(cost=True))


def test_user_text_has_no_planner_hint() -> None:
    text = format_user_text(sample_snapshot())
    assert REPLY_HINT not in text
    assert "【身份】" in text


def test_injection_content() -> None:
    text = format_injection(sample_snapshot())
    assert text.startswith(INJECTION_TAG)
    assert "你是「麦麦」" in text
    assert "运行在 MaiBot 1.3.1（插件 SDK 2.8.2）" in text
    assert "接入平台：qq、email" in text
    assert "近 7 天主要使用的模型：deepseek-v3.2、qwen3-235b、glm-4.6v" in text
    assert "已加载 12 个插件、31 个工具" in text
    assert "maifetch 工具" in text
    assert "2.41M" not in text and "1,774" not in text


def test_injection_is_stable_across_counters_and_times() -> None:
    a = sample_snapshot()
    later = a.collected_at + timedelta(hours=2)
    b = replace(
        a,
        collected_at=later,
        identity=replace(a.identity, local_time=later),
        runtime=replace(a.runtime, online_since=a.runtime.online_since - timedelta(days=1)),
        usage=replace(
            a.usage,
            total_requests=5000,
            total_tokens=9_999_999,
            total_messages=10,
            models=tuple(replace(m, requests=m.requests + 10, tokens=m.tokens * 2) for m in a.usage.models),
        ),
    )
    assert format_injection(a) == format_injection(b)


def test_injection_drops_unknown_pieces() -> None:
    text = format_injection(Snapshot(collected_at=sample_snapshot().collected_at))
    assert text.startswith(INJECTION_TAG)
    assert "未知" not in text
    assert "maifetch 工具" in text


def test_unknown_platforms_are_omitted() -> None:
    snap = sample_snapshot()
    snap = replace(snap, identity=replace(snap.identity, platforms=()))
    text = format_tool_text(snap, "identity")
    assert "平台" not in text
    assert "昵称：麦麦" in text


def test_models_block_says_all_models_listed() -> None:
    assert "【模型用量·近 7 天】全部 3 个模型：deepseek-v3.2" in format_tool_text(sample_snapshot(), "models")


def test_models_block_says_only_top_k_of_total() -> None:
    snap = sample_snapshot()
    snap = replace(snap, usage=replace(snap.usage, model_count=12))
    text = format_tool_text(snap, "usage")
    assert "【模型用量·近 7 天】调用次数最多的前 3 个（共 12 个模型，其余未列出）：deepseek-v3.2" in text
    assert "【合计·近 7 天（全部模型）】1,774 次请求" in text


def test_models_block_capped_model_count() -> None:
    snap = sample_snapshot()
    snap = replace(snap, usage=replace(snap.usage, model_count=50, totals_capped=True))
    assert "（共 50+ 个模型，其余未列出）" in format_tool_text(snap, "models")


def test_cost_ranking_block() -> None:
    text = format_tool_text(sample_snapshot(cost=True), "usage")
    assert "【花费排行·近 7 天】全部 3 个有花费的模型：qwen3-235b ¥3.42/402 次/410.0K tok；deepseek-v3.2 ¥0.96" in text
    lines = text.splitlines()
    assert lines.index(next(x for x in lines if x.startswith("【模型用量"))) < lines.index(
        next(x for x in lines if x.startswith("【花费排行"))
    )


def test_cost_ranking_top_k_scope() -> None:
    snap = sample_snapshot(cost=True)
    snap = replace(snap, usage=replace(snap.usage, costed_model_count=9))
    assert "【花费排行·近 7 天】花费最高的前 3 个（共 9 个有花费的模型，其余未列出）：" in format_tool_text(
        snap, "usage"
    )


def test_rankings_can_be_turned_off() -> None:
    snap = sample_snapshot(cost=True)
    snap = replace(snap, usage=replace(snap.usage, show_request_ranking=False, show_cost_ranking=False))
    text = format_tool_text(snap, "all")
    assert "【模型用量" not in text and "【花费排行" not in text
    assert "【合计·近 7 天（全部模型）】1,774 次请求" in text


def test_cost_alias_and_hidden_by_default_sample() -> None:
    assert normalize_section("花费") == ("usage", None)
    assert "【花费排行" not in format_tool_text(sample_snapshot(), "usage")
