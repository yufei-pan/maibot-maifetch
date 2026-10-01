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
    for comment in re.findall(r"<!--(.*?)-->", _template(name), re.S):
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
