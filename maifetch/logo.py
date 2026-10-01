"""呆萌像素麦麦（萨卡班甲鱼）：20×14 手绘像素，斗鸡眼大眼珠、小尖嘴、三瓣四叶草尾鳍、头顶嫩芽。

参考形象：MaiBot/depends-data/maimai-v2.png 顶部的完整萨卡班甲鱼麦麦。
"""

from __future__ import annotations

MAIMAI_GRID: tuple[str, ...] = (
    "...........gg.gg....",
    "............ggg.....",
    ".............g......",
    ".gg.......ooooooo...",
    ".ggg...oooooooooooo.",
    "..gggooooooEEEooEEEo",
    "...goooooooEEpoopEEo",
    "gg.ooooooooEEEooEEEo",
    "gggoooooooooooppooow",
    "gg.ooooooooooopwwww.",
    "....ooooowwwwwwwww..",
    "...ggwwwwwwwwwww....",
    ".ggg...wwwwww.......",
    ".gg.................",
)

MAIMAI_PALETTE: dict[str, str] = {
    "o": "#ef8d24",  # 身体
    "w": "#fcfdfc",  # 肚皮
    "E": "#fcfdfc",  # 眼白
    "p": "#2f130a",  # 瞳孔 / 嘴
    "g": "#86e541",  # 嫩芽 / 尾鳍
}


def maimai_svg(cell: int = 6) -> str:
    """生成内联 SVG（同色相邻像素合并为一个 rect）。"""

    width, height = len(MAIMAI_GRID[0]), len(MAIMAI_GRID)
    rects: list[str] = []
    for y, row in enumerate(MAIMAI_GRID):
        x = 0
        while x < width:
            color = MAIMAI_PALETTE.get(row[x])
            if color is None:
                x += 1
                continue
            end = x
            while end < width and MAIMAI_PALETTE.get(row[end]) == color:
                end += 1
            rects.append(f'<rect x="{x}" y="{y}" width="{end - x}" height="1" fill="{color}"/>')
            x = end
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width * cell}" height="{height * cell}" '
        'shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">' + "".join(rects) + "</svg>"
    )
