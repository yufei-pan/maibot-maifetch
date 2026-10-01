from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fakes import tiny_png

from maifetch.render import (
    bundled_template_path,
    font_face_css,
    load_template,
    png_to_webp,
    resolve_template_path,
)

PLUGIN_DIR = Path(__file__).resolve().parent.parent


def test_bundled_template_path(tmp_path: Path) -> None:
    assert bundled_template_path(tmp_path, "terminal") == tmp_path / "assets" / "terminal.html"
    with pytest.raises(ValueError):
        bundled_template_path(tmp_path, "../../etc/passwd")


def test_resolve_template_path(tmp_path: Path) -> None:
    assert resolve_template_path(tmp_path, "assets/sheet.html") == tmp_path / "assets" / "sheet.html"
    absolute = tmp_path / "custom.html"
    assert resolve_template_path(Path("/nowhere"), str(absolute)) == absolute
    assert resolve_template_path(tmp_path, "") == tmp_path / "assets" / "dashboard.html"


def test_load_template_reads_configured(tmp_path: Path) -> None:
    (tmp_path / "mine.html").write_text("<div id='card'>mine</div>", encoding="utf-8")
    assert load_template(tmp_path, "mine.html", None, logging.getLogger("t")) == "<div id='card'>mine</div>"


def test_load_template_falls_back(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "dashboard.html").write_text("DEFAULT", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert load_template(tmp_path, "missing/nope.html", None, logging.getLogger("t")) == "DEFAULT"
    assert "模板读取失败" in caplog.text


def test_load_template_bundled_name_wins(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "terminal.html").write_text("TERM", encoding="utf-8")
    assert load_template(tmp_path, "custom.html", "terminal", logging.getLogger("t")) == "TERM"


def test_font_face_css_from_dir(tmp_path: Path) -> None:
    (tmp_path / "NotoSansSC-400.woff2").write_bytes(b"fake-font")
    css = font_face_css(tmp_path)
    assert css.startswith("<style>@font-face{font-family:'Noto Sans SC';font-weight:400")
    assert "data:font/woff2;base64,ZmFrZS1mb250" in css
    assert font_face_css(tmp_path) is css


def test_font_face_css_empty_dir(tmp_path: Path) -> None:
    assert font_face_css(tmp_path / "missing") == ""


def test_bundled_fonts_present() -> None:
    css = font_face_css(PLUGIN_DIR / "assets" / "fonts")
    assert "font-family:'Noto Sans SC';font-weight:700" in css
    assert "font-family:'JetBrains Mono'" in css
    assert (PLUGIN_DIR / "assets" / "fonts" / "OFL-NotoSansSC.txt").is_file()
    assert (PLUGIN_DIR / "assets" / "fonts" / "OFL-JetBrainsMono.txt").is_file()


def test_png_to_webp() -> None:
    webp = png_to_webp(tiny_png())
    assert webp is not None
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP"
    assert png_to_webp(b"not a png") is None
