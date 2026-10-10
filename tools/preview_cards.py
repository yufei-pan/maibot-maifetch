"""本地预览内置 / 自定义模板（开发用，不随插件运行）：用示例快照渲染 PNG。

用法（需要 Playwright + Chromium；本工作区可用 MaiBot 的 venv 与系统 Chrome）：
    PYTHONPATH=.:../maibot-plugin-sdk ../MaiBot/.venv/bin/python tools/preview_cards.py preview \
        --chrome /opt/google/chrome/chrome
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from maifetch.card import build_card_html  # noqa: E402
from maifetch.render import font_face_css  # noqa: E402
from maifetch.sample import sample_snapshot  # noqa: E402


async def _main(args: argparse.Namespace) -> None:
    from playwright.async_api import async_playwright

    snapshot = sample_snapshot(hardware=not args.no_hardware, cost=args.cost)
    templates = (
        [Path(args.template)]
        if args.template
        else [PLUGIN_DIR / "assets" / f"{name}.html" for name in ("dashboard", "terminal", "sheet")]
    )
    css = font_face_css(PLUGIN_DIR / "assets" / "fonts")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        launch_kwargs: dict = {"args": ["--no-sandbox"]}
        if args.chrome:
            launch_kwargs["executable_path"] = args.chrome
        browser = await playwright.chromium.launch(**launch_kwargs)
        page = await browser.new_page(viewport={"width": 800, "height": 600}, device_scale_factor=args.scale)
        for template in templates:
            html = build_card_html(snapshot, template.read_text(encoding="utf-8"), css)
            await page.set_content(html, wait_until="load")
            target = out_dir / f"{template.stem}.png"
            await page.locator("#card").screenshot(path=str(target), omit_background=True)
            print(target)
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="maifetch 模板预览")
    parser.add_argument("out_dir")
    parser.add_argument("--chrome", default="", help="Chromium/Chrome 可执行文件路径（可选）")
    parser.add_argument("--template", default="", help="只预览这个模板文件")
    parser.add_argument("--no-hardware", action="store_true", help="模拟硬件信息关闭")
    parser.add_argument("--cost", action="store_true", help="模拟显示花费")
    parser.add_argument("--scale", type=float, default=1.0)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
