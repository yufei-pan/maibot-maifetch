from __future__ import annotations

import re
from pathlib import Path

import pytest

from maifetch.card import PLACEHOLDER_KEYS, build_card_html
from maifetch.sample import sample_snapshot

ASSETS = Path(__file__).resolve().parent.parent / "assets"
NAMES = ("dashboard", "terminal", "sheet")


def _template(name: str) -> str:
    return (ASSETS / f"{name}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_template_renders_completely(name: str) -> None:
    html = build_card_html(sample_snapshot(), _template(name))
    assert 'id="card"' in html
    leftovers = [key for key in re.findall(r"\{([a-z_]+)\}", html) if key in PLACEHOLDER_KEYS]
    assert leftovers == []
    assert "未知" not in html


@pytest.mark.parametrize("name", NAMES)
def test_header_comment_has_no_placeholders(name: str) -> None:
    for comment in re.findall(r"<!--(.*?)-->", _template(name), re.DOTALL):
        assert re.search(r"\{[a-z_]+\}", comment) is None


@pytest.mark.parametrize("name", NAMES)
def test_hardware_hidden_when_off(name: str) -> None:
    html = build_card_html(sample_snapshot(hardware=False), _template(name))
    assert "Ryzen" not in html and "Debian" not in html


def test_dashboard_specifics() -> None:
    html = build_card_html(sample_snapshot(), _template("dashboard"))
    assert "请求 · 7 天" in html
    assert 'class="mf-chip mf-more">+4<' in html
    assert "maifetch 0.1.0" in html


def test_terminal_specifics() -> None:
    html = build_card_html(sample_snapshot(), _template("terminal"))
    assert '<svg viewBox="0 0 20 14"' in html
    assert '<span class="k">Kernel</span>: 6.8.12-pve' in html
    assert "deepseek-v3.2 (+2)" in html


def test_sheet_specifics() -> None:
    html = build_card_html(sample_snapshot(cost=True), _template("sheet"))
    assert "<td>合计</td><td>1,774 次 · 2.41M tok · 消息 3,906 条 · ¥4.87</td>" in html
    assert '<div class="sec">硬件</div>' in html


@pytest.mark.parametrize("name", NAMES)
def test_templates_hide_empty_platforms(name: str) -> None:
    from dataclasses import replace

    snap = sample_snapshot()
    snap = replace(snap, identity=replace(snap.identity, platforms=()))
    html = build_card_html(snap, _template(name))
    assert "未知" not in html
    if name != "sheet":
        assert 'data-v=""' in html


@pytest.mark.parametrize("name", ["dashboard", "sheet"])
def test_model_section_shows_scope(name: str) -> None:
    from dataclasses import replace

    snap = sample_snapshot()
    snap = replace(snap, usage=replace(snap.usage, model_count=12))
    html = build_card_html(snap, _template(name))
    assert 'data-v="前 3 / 共 12"> · 前 3 / 共 12</span>' in html


@pytest.mark.parametrize("name", ["dashboard", "sheet"])
def test_model_scope_hidden_when_unknown(name: str) -> None:
    from dataclasses import replace

    snap = sample_snapshot()
    snap = replace(snap, usage=replace(snap.usage, model_count=None))
    html = build_card_html(snap, _template(name))
    assert 'class="ms" data-v=""' in html


def test_cost_sections_on_cards() -> None:
    snap = sample_snapshot(cost=True)
    assert 'class="box mf-cost"' in build_card_html(snap, _template("dashboard"))
    assert '<div class="sec">花费排行' in build_card_html(snap, _template("sheet"))
    terminal = build_card_html(snap, _template("terminal"))
    assert '<span class="k">Top cost</span>: qwen3-235b ¥3.42' in terminal


def test_cost_sections_absent_when_cost_hidden() -> None:
    snap = sample_snapshot()
    assert 'class="box mf-cost"' not in build_card_html(snap, _template("dashboard"))
    assert "花费排行" not in build_card_html(snap, _template("sheet"))
    assert 'data-v=""><span class="k">Top cost' in build_card_html(snap, _template("terminal"))


def test_dashboard_hides_model_box_when_request_ranking_off() -> None:
    from dataclasses import replace

    snap = sample_snapshot()
    snap = replace(snap, usage=replace(snap.usage, show_request_ranking=False))
    html = build_card_html(snap, _template("dashboard"))
    assert '<div class="rows"></div>' in html
    assert ".mf-models:has(.rows:empty)" in html
