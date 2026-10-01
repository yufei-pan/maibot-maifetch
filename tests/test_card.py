from __future__ import annotations

import json
from dataclasses import replace

from maifetch.card import (
    MAX_PLUGIN_CHIPS,
    PLACEHOLDER_KEYS,
    SCALAR_KEYS,
    build_card_html,
    build_data_json,
    build_fragments,
    build_scalars,
    fill_template,
    short_plugin_name,
)
from maifetch.sample import sample_snapshot
from maifetch.snapshot import Snapshot


def test_scalar_keys_complete() -> None:
    assert set(build_scalars(sample_snapshot())) == set(SCALAR_KEYS)


def test_scalars_for_sample() -> None:
    scalars = build_scalars(sample_snapshot())
    assert scalars["nickname"] == "麦麦"
    assert scalars["nickname_initial"] == "麦"
    assert scalars["uptime_short"] == "3d 4h"
    assert scalars["uptime"] == "3 天 4 小时"
    assert scalars["top_model"] == "deepseek-v3.2"
    assert scalars["top_model_more"] == "(+2)"
    assert scalars["total_tokens"] == "2.41M"
    assert scalars["total_cost"] == ""
    assert scalars["account"] == ""
    assert scalars["hw_cpu"] == "AMD Ryzen 9 7950X 16-Core Processor (32)"
    assert scalars["hw_memory"] == "11.2 GiB / 62.6 GiB"


def test_unknown_vs_hidden_scalars() -> None:
    scalars = build_scalars(Snapshot(collected_at=sample_snapshot().collected_at))
    assert scalars["host_version"] == "未知"
    assert scalars["total_requests"] == "未知"
    assert scalars["account"] == ""
    assert scalars["total_cost"] == ""
    assert scalars["hw_os"] == ""
    assert scalars["nickname_initial"] == "麦"


def test_tiles_swap_cost_for_requests() -> None:
    hidden = build_fragments(sample_snapshot())["tiles_html"]
    assert "请求 · 7 天" in hidden and "花费" not in hidden
    shown = build_fragments(sample_snapshot(cost=True))["tiles_html"]
    assert "花费 · 7 天" in shown and "¥4.87" in shown
    assert hidden.count('class="mf-tile"') == 4


def test_plugin_chips_overflow() -> None:
    chips = build_fragments(sample_snapshot())["plugin_list_html"]
    assert chips.count('class="mf-chip"') == MAX_PLUGIN_CHIPS
    assert '<span class="mf-chip mf-more">+4</span>' in chips
    assert ">corpus-callosum<" in chips


def test_plugin_list_hidden() -> None:
    snap = sample_snapshot()
    hidden = replace(snap, runtime=replace(snap.runtime, plugins=None))
    fragments = build_fragments(hidden)
    assert fragments["plugin_list_html"] == ""
    assert "插件列表" not in fragments["runtime_rows_html"]


def test_model_rows() -> None:
    rows = build_fragments(sample_snapshot())["model_rows_html"]
    assert rows.count('class="mf-model-row"') == 3
    assert 'style="width:100%"' in rows
    assert "mf-model-cost" not in rows
    assert "mf-model-cost" in build_fragments(sample_snapshot(cost=True))["model_rows_html"]


def test_hardware_fragments_empty_when_off() -> None:
    fragments = build_fragments(sample_snapshot(hardware=False))
    assert fragments["hardware_block_html"] == ""
    assert fragments["hardware_lines_html"] == ""
    assert fragments["hardware_table_html"] == ""
    on = build_fragments(sample_snapshot())
    assert "Debian GNU/Linux 12 (bookworm) x86_64" in on["hardware_lines_html"]
    assert '<span class="mf-k">内存</span>' in on["hardware_block_html"]
    assert on["hardware_table_html"].startswith('<div class="sec">硬件</div><table>')


def test_logo_fragment() -> None:
    assert build_fragments(sample_snapshot())["maimai_logo_svg"].startswith("<svg")


def test_capped_scalars() -> None:
    snap = sample_snapshot()
    capped_snap = replace(snap, usage=replace(snap.usage, totals_capped=True))
    assert build_scalars(capped_snap)["total_requests"] == "1,774+"


def test_hostile_values_are_escaped_and_not_reexpanded() -> None:
    snap = sample_snapshot()
    evil = replace(snap, identity=replace(snap.identity, nickname="<script>alert(1)</script>{plugin_version}-->"))
    html = build_card_html(evil, '<div id="card">{nickname}|{plugin_version}</div>')
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;{plugin_version}--&gt;|0.1.0" in html


def test_hostile_values_in_data_json() -> None:
    snap = sample_snapshot()
    evil = replace(snap, identity=replace(snap.identity, nickname="</script><b>-->"))
    data_json = build_data_json(evil)
    assert "<" not in data_json and ">" not in data_json
    assert json.loads(data_json)["identity"]["nickname"] == "</script><b>-->"


def test_fill_template_single_pass_and_leaves_unknown() -> None:
    out = fill_template("a{color:red} {unknown_key} {x}", {"x": "{x}"})
    assert out == "a{color:red} {unknown_key} {x}"


def test_build_card_html_document() -> None:
    html = build_card_html(sample_snapshot(), '<div id="card">{nickname}</div>', "<style>/*fonts*/</style>")
    assert html.startswith('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>/*fonts*/</style>')
    assert '<div id="card">麦麦</div>' in html


def test_placeholder_keys_include_everything() -> None:
    assert "data_json" in PLACEHOLDER_KEYS
    assert set(build_fragments(sample_snapshot())) <= PLACEHOLDER_KEYS
    assert set(SCALAR_KEYS) <= PLACEHOLDER_KEYS


def test_short_plugin_name() -> None:
    assert short_plugin_name("com.0-hz.fetch-url") == "fetch-url"
    assert short_plugin_name("plain") == "plain"


def test_empty_platforms_scalar_is_blank() -> None:
    snap = sample_snapshot()
    snap = replace(snap, identity=replace(snap.identity, platforms=()))
    assert build_scalars(snap)["platforms"] == ""
    assert "平台" not in build_fragments(snap)["identity_rows_html"]


def test_model_scope_scalar() -> None:
    snap = sample_snapshot()
    assert build_scalars(snap)["model_scope"] == "共 3 个"
    assert build_scalars(replace(snap, usage=replace(snap.usage, model_count=12)))["model_scope"] == "前 3 / 共 12"
    capped_usage = replace(snap.usage, model_count=50, totals_capped=True)
    assert build_scalars(replace(snap, usage=capped_usage))["model_scope"] == "前 3 / 共 50+"
    assert build_scalars(replace(snap, usage=replace(snap.usage, model_count=None)))["model_scope"] == ""


def test_top_model_more_counts_all_models() -> None:
    snap = sample_snapshot()
    assert build_scalars(replace(snap, usage=replace(snap.usage, model_count=12)))["top_model_more"] == "(+11)"
    capped_usage = replace(snap.usage, model_count=50, totals_capped=True)
    assert build_scalars(replace(snap, usage=capped_usage))["top_model_more"] == "(+49+)"


def test_cost_block_fragment() -> None:
    fragments = build_fragments(sample_snapshot(cost=True))
    block = fragments["cost_block_html"]
    assert block.startswith('<div class="box mf-cost">')
    assert "花费排行 · 近 7 天" in block and "共 3 个" in block
    assert block.count('class="mf-cost-row"') == 3
    assert block.index("qwen3-235b") < block.index("deepseek-v3.2")
    assert 'style="width:100%"' in block
    table = fragments["cost_table_html"]
    assert table.startswith('<div class="sec">花费排行 · 近 7 天')
    assert "<td>qwen3-235b</td><td>¥3.42 · 402 次 · 410.0K tok</td>" in table


def test_cost_fragments_empty_when_hidden() -> None:
    fragments = build_fragments(sample_snapshot())
    assert fragments["cost_block_html"] == ""
    assert fragments["cost_table_html"] == ""
    assert build_scalars(sample_snapshot())["top_cost_model"] == ""


def test_top_cost_model_scalar() -> None:
    assert build_scalars(sample_snapshot(cost=True))["top_cost_model"] == "qwen3-235b ¥3.42"


def test_request_ranking_off_clears_its_fragments() -> None:
    snap = sample_snapshot()
    snap = replace(snap, usage=replace(snap.usage, show_request_ranking=False))
    assert build_fragments(snap)["model_rows_html"] == ""
    assert build_scalars(snap)["model_scope"] == ""
    assert "<td>合计</td>" in build_fragments(snap)["model_table_rows_html"]
    assert "deepseek-v3.2" not in build_fragments(snap)["model_table_rows_html"]
