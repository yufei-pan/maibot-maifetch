from __future__ import annotations

import re

from maifetch.logo import MAIMAI_GRID, MAIMAI_PALETTE, maimai_svg


def test_grid_shape_and_palette() -> None:
    assert len(MAIMAI_GRID) == 14
    assert {len(row) for row in MAIMAI_GRID} == {20}
    used = {cell for row in MAIMAI_GRID for cell in row} - {"."}
    assert used <= set(MAIMAI_PALETTE)
    assert sum(row.count("p") for row in MAIMAI_GRID) == 5  # two pupils + 3-pixel beak


def test_svg_structure() -> None:
    svg = maimai_svg()
    assert svg.startswith('<svg viewBox="0 0 20 14" width="120" height="84"')
    assert 'shape-rendering="crispEdges"' in svg
    colors = set(re.findall(r'fill="(#[0-9a-f]{6})"', svg))
    assert colors == {"#ef8d24", "#fcfdfc", "#2f130a", "#86e541"}
    assert maimai_svg(cell=3).startswith('<svg viewBox="0 0 20 14" width="60" height="42"')


def test_svg_covers_every_pixel_once() -> None:
    covered = 0
    for match in re.finditer(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="1"', maimai_svg()):
        covered += int(match.group(3))
    assert covered == sum(len(row) - row.count(".") for row in MAIMAI_GRID)
