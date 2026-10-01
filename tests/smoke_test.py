"""离线冒烟测试：不依赖 MaiBot Host。

运行方式（在插件根目录）：
    PYTHONPATH=../maibot-plugin-sdk python3 tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
for _path in (PLUGIN_DIR, PLUGIN_DIR.parent / "maibot-plugin-sdk", PLUGIN_DIR / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import plugin as maifetch_plugin  # noqa: E402
from fakes import FakeCtx  # noqa: E402


def test_manifest_and_version() -> None:
    manifest = json.loads((PLUGIN_DIR / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "com.0-hz.maifetch"
    assert maifetch_plugin.PLUGIN_VERSION == manifest["version"]
    print("ok: manifest")


def test_end_to_end() -> None:
    async def scenario() -> None:
        ctx = FakeCtx()
        instance = maifetch_plugin.MaiFetchPlugin()
        instance.set_plugin_config({"hardware": {"enabled": True}})
        instance._set_context(ctx)
        await instance.on_load()
        await instance._refresh_once()
        hook = await instance.on_planner_before_request(
            items=[{"item_type": "SystemMessageItem", "parts": [{"type": "text", "text": "sys"}]}],
            item_schema_version=1,
        )
        assert "modified_kwargs" in hook
        tool = await instance.tool_maifetch(section="hardware", stream_id="s1")
        assert "【硬件】" in tool["content"]
        for name in ("dashboard", "terminal", "sheet"):
            instance._cooldown.set_seconds(0)
            result = await instance.cmd_maifetch(stream_id="s1", matched_groups={"arg": name})
            assert result == (True, "已发送状态卡片", 2), (name, result)
        await instance.on_unload()
        assert len(ctx.sent_images) == 3

    asyncio.run(scenario())
    print("ok: end to end (hook, tool, 3 templates)")


if __name__ == "__main__":
    test_manifest_and_version()
    test_end_to_end()
    print("smoke test passed")
