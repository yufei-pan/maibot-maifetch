"""把卡片 HTML 变成可发送图片的纯辅助：模板解析 / 读取、内置字体 CSS、PNG→无损 WebP。"""

from __future__ import annotations

import io
from base64 import b64encode
from pathlib import Path
from typing import Any

from maifetch.config import BUNDLED_TEMPLATES, DEFAULT_TEMPLATE

FONT_FILES: tuple[tuple[str, int, str], ...] = (
    ("Noto Sans SC", 400, "NotoSansSC-400.woff2"),
    ("Noto Sans SC", 700, "NotoSansSC-700.woff2"),
    ("JetBrains Mono", 400, "JetBrainsMono-Regular.woff2"),
)
_FONT_CSS_CACHE: dict[str, str] = {}


def bundled_template_path(plugin_dir: Path, name: str) -> Path:
    """内置模板路径；只接受白名单名称，聊天里的参数永远无法指向任意文件。"""

    if name not in BUNDLED_TEMPLATES:
        raise ValueError(f"未知的内置模板：{name}")
    return plugin_dir / "assets" / f"{name}.html"


def resolve_template_path(plugin_dir: Path, configured: str) -> Path:
    candidate = Path(configured or DEFAULT_TEMPLATE).expanduser()
    return candidate if candidate.is_absolute() else plugin_dir / candidate


def load_template(plugin_dir: Path, configured: str, bundled_name: str | None, logger: Any) -> str:
    path = (
        bundled_template_path(plugin_dir, bundled_name)
        if bundled_name
        else resolve_template_path(plugin_dir, configured)
    )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("maifetch 模板读取失败（%s），改用内置 dashboard：%s", path, exc)
        return (plugin_dir / DEFAULT_TEMPLATE).read_text(encoding="utf-8")


def font_face_css(font_dir: Path) -> str:
    """内置字体转 data URI 的 @font-face（渲染不联网）；按目录缓存，同一进程只读一次。"""

    key = str(font_dir)
    if key in _FONT_CSS_CACHE:
        return _FONT_CSS_CACHE[key]
    rules: list[str] = []
    for family, weight, filename in FONT_FILES:
        path = font_dir / filename
        if not path.is_file():
            continue
        encoded = b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;font-display:block;"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2');}}"
        )
    css = f"<style>{''.join(rules)}</style>" if rules else ""
    _FONT_CSS_CACHE[key] = css
    return css


def png_to_webp(png: bytes) -> bytes | None:
    """无损 WebP 重编码（聊天图片更小，减少 NapCat 回执超时误报）；Pillow 不可用或失败返回 None。"""

    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(png)) as image:
            image.load()
            buffer = io.BytesIO()
            image.save(buffer, format="WEBP", lossless=True, method=6)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 - 编码失败由调用方回退 PNG
        return None
