from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Any

import pytest
from fakes import FakeCtx

import plugin as maifetch_plugin
from maifetch.text import REPLY_HINT

SYSTEM_ITEMS = [
    {"item_type": "SystemMessageItem", "parts": [{"type": "text", "text": "系统提示"}]},
    {"item_type": "UserMessageItem", "parts": [{"type": "text", "text": "你是什么模型？"}]},
]


def make_plugin(ctx: FakeCtx | None = None, config: dict[str, Any] | None = None) -> maifetch_plugin.MaiFetchPlugin:
    instance = maifetch_plugin.MaiFetchPlugin()
    instance.set_plugin_config(config or {})
    instance._set_context(ctx or FakeCtx())
    return instance


def run(coro):
    return asyncio.run(coro)


def _component(components: list[dict], name: str) -> dict:
    return next(c for c in components if c["name"] == name)


def test_get_components_patches_description_and_pattern() -> None:
    instance = make_plugin(config={"usage": {"window_days": 14}, "command": {"aliases": ["/状态"]}})
    components = instance.get_components()
    tool = _component(components, "maifetch")
    assert "近 14 天" in tool["metadata"]["description"]
    command = _component(components, "maifetch_card")
    match = re.compile(command["metadata"]["command_pattern"]).search("/状态 terminal")
    assert match is not None and match.group("arg") == "terminal"
    assert any(c["metadata"].get("hook") == "maisaka.planner.before_request" for c in components)


def test_hook_injects_after_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIBOT_HOST_VERSION", "1.3.1")

    async def scenario() -> dict:
        instance = make_plugin()
        instance._refresh_settings()
        assert await instance._refresh_once() is True
        return await instance.on_planner_before_request(items=[dict(i) for i in SYSTEM_ITEMS], item_schema_version=1)

    result = run(scenario())
    assert result["action"] == "continue"
    injected = result["modified_kwargs"]["items"][0]["parts"][-1]["text"]
    assert "【maifetch·自身信息】你是「麦麦」，运行在 MaiBot 1.3.1" in injected


def test_hook_noop_without_cache() -> None:
    async def scenario() -> dict:
        instance = make_plugin()
        instance._refresh_settings()
        return await instance.on_planner_before_request(items=SYSTEM_ITEMS, item_schema_version=1)

    assert run(scenario()) == {"action": "continue"}


def test_hook_respects_disabled_injection() -> None:
    async def scenario() -> dict:
        instance = make_plugin(config={"injection": {"enabled": False}})
        instance._refresh_settings()
        instance._injection_text = "【maifetch·自身信息】x"
        return await instance.on_planner_before_request(items=SYSTEM_ITEMS, item_schema_version=1)

    assert run(scenario()) == {"action": "continue"}


def test_refresh_reports_failure_when_host_not_ready() -> None:
    down = {"success": False, "error": "Host 尚未就绪"}
    ctx = FakeCtx({name: down for name in FakeCtx().responses})

    async def scenario() -> tuple[bool, str]:
        instance = make_plugin(ctx)
        instance._refresh_settings()
        ok = await instance._refresh_once()
        return ok, instance._injection_text

    ok, text = run(scenario())
    assert ok is False
    assert text.startswith("【maifetch·自身信息】")


def test_refresh_keeps_good_cache_on_partial_failure() -> None:
    async def scenario() -> tuple[bool, str, str]:
        instance = make_plugin()
        instance._refresh_settings()
        await instance._refresh_once()
        good = instance._injection_text
        instance.ctx.responses["component.get_all_plugins"] = {"success": False, "error": "x"}
        ok = await instance._refresh_once()
        return ok, good, instance._injection_text

    ok, good, after = run(scenario())
    assert ok is True
    assert after == good


def test_next_delay() -> None:
    instance = make_plugin(config={"injection": {"refresh_minutes": 10}})
    instance._refresh_settings()
    assert instance._next_delay(True) == 600
    assert instance._next_delay(False) == maifetch_plugin.RETRY_SECONDS


def test_on_load_and_unload_manage_task() -> None:
    async def scenario() -> tuple[bool, bool]:
        instance = make_plugin()
        await instance.on_load()
        started = instance._refresh_task is not None
        await instance.on_unload()
        return started, instance._refresh_task is None

    assert run(scenario()) == (True, True)


def test_config_update_disabling_injection_clears_text() -> None:
    async def scenario() -> str:
        instance = make_plugin()
        await instance.on_load()
        instance._injection_text = "old"
        instance.set_plugin_config({"injection": {"enabled": False}})
        await instance.on_config_update("self", {}, "1.0.0")
        await instance.on_unload()
        return instance._injection_text

    assert run(scenario()) == ""


def test_tool_returns_text_and_hint() -> None:
    ctx = FakeCtx()
    result = run(make_plugin(ctx).tool_maifetch(section="all", stream_id="s1"))
    assert result["success"] is True
    assert "【身份】" in result["content"]
    assert result["content"].splitlines()[-1] == REPLY_HINT
    assert ctx.sent_images == []


def test_tool_send_card_false_string_does_not_send() -> None:
    ctx = FakeCtx()
    run(make_plugin(ctx).tool_maifetch(section="模型", send_card="false", stream_id="s1"))
    assert ctx.sent_images == []
    assert ctx.rendered_html == []


def test_tool_send_card_sends_webp_and_reports() -> None:
    ctx = FakeCtx()
    result = run(make_plugin(ctx).tool_maifetch(send_card="是", stream_id="s1"))
    assert result["content"].startswith("已发送状态卡片。")
    image_b64, stream = ctx.sent_images[0]
    assert stream == "s1"
    data = base64.b64decode(image_b64)
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    kwargs = ctx.render_kwargs[0]
    assert kwargs["selector"] == "#card"
    assert kwargs["device_scale_factor"] == 1.0
    assert kwargs["allow_network"] is False


def test_tool_send_card_cooldown() -> None:
    async def scenario() -> str:
        instance = make_plugin()
        await instance.tool_maifetch(send_card=True, stream_id="s1")
        second = await instance.tool_maifetch(send_card=True, stream_id="s1")
        return second["content"]

    assert run(scenario()).startswith("冷却中，")


def test_tool_send_card_without_stream() -> None:
    result = run(make_plugin().tool_maifetch(send_card=True))
    assert result["content"].startswith("当前没有可发送的聊天")


def test_command_card_and_intercept() -> None:
    ctx = FakeCtx()
    result = run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={}))
    assert result == (True, "已发送状态卡片", 2)
    assert len(ctx.sent_images) == 1
    assert 'class="tiles"' in ctx.rendered_html[0]


def test_command_text() -> None:
    ctx = FakeCtx()
    result = run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={"arg": "文字"}))
    assert result[0] is True and result[2] == 2
    assert "【身份】" in ctx.sent_texts[0][0]
    assert ctx.rendered_html == []


def test_command_bundled_template() -> None:
    ctx = FakeCtx()
    run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={"arg": "terminal"}))
    assert '<svg viewBox="0 0 20 14"' in ctx.rendered_html[0]


def test_command_help_for_unknown_arg() -> None:
    ctx = FakeCtx()
    result = run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={"arg": "../../x"}))
    assert result == (True, "已发送用法", 2)
    assert ctx.sent_texts[0][0].startswith("maifetch（麦麦状态）用法")


def test_command_cooldown() -> None:
    async def scenario() -> tuple:
        instance = make_plugin()
        await instance.cmd_maifetch(stream_id="s1", matched_groups={})
        return await instance.cmd_maifetch(stream_id="s1", matched_groups={})

    assert run(scenario()) == (False, "冷却中", 2)


def test_command_render_failure_falls_back_to_text() -> None:
    ctx = FakeCtx(render_result={"success": False, "error": "selector #card not found"})
    result = run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={}))
    assert result == (True, "图片渲染不可用，已发送文字版", 2)
    assert ctx.sent_texts[0][0].startswith("（图片渲染不可用，以下为文字版）")
    assert ctx.sent_images == []


def test_command_render_exception_falls_back_to_text() -> None:
    ctx = FakeCtx(render_result=RuntimeError("playwright missing"))
    result = run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={}))
    assert result[0] is True and "文字版" in result[1]


def test_command_missing_template_uses_dashboard(caplog: pytest.LogCaptureFixture) -> None:
    ctx = FakeCtx()
    with caplog.at_level(logging.WARNING):
        run(
            make_plugin(ctx, {"card": {"template": "nope/missing.html"}}).cmd_maifetch(
                stream_id="s1", matched_groups={}
            )
        )
    assert 'class="tiles"' in ctx.rendered_html[0]
    assert "模板读取失败" in caplog.text


def test_command_maybe_failed_send() -> None:
    ctx = FakeCtx(send_ok=False)
    assert run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={})) == (False, "状态卡片可能未送达", 2)


def test_png_config_skips_webp() -> None:
    ctx = FakeCtx()
    run(make_plugin(ctx, {"card": {"format": "png"}}).cmd_maifetch(stream_id="s1", matched_groups={}))
    assert base64.b64decode(ctx.sent_images[0][0])[:8] == b"\x89PNG\r\n\x1a\n"


def test_default_card_shows_cost_and_hardware() -> None:
    ctx = FakeCtx()
    run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={}))
    html = ctx.rendered_html[0]
    assert "花费 · 7 天" in html and "¥4.87" in html
    assert 'class="mf-hw"' in html


def test_hidden_cost_not_in_rendered_card() -> None:
    ctx = FakeCtx()
    run(make_plugin(ctx, {"visibility": {"show_cost": False}}).cmd_maifetch(stream_id="s1", matched_groups={}))
    assert "¥" not in ctx.rendered_html[0]
    assert "123456789" not in ctx.rendered_html[0]


def test_refresh_keeps_retrying_until_complete() -> None:
    down = {"success": False, "error": "Host 尚未就绪"}
    ctx = FakeCtx({name: down for name in FakeCtx().responses})

    async def scenario() -> list[float]:
        instance = make_plugin(ctx)
        instance._refresh_settings()
        delays = []
        for _ in range(2):
            delays.append(instance._next_delay(await instance._refresh_once()))
        ctx.responses.update(FakeCtx().responses)
        delays.append(instance._next_delay(await instance._refresh_once()))
        assert "你是「麦麦」" in instance._injection_text
        return delays

    assert run(scenario()) == [maifetch_plugin.RETRY_SECONDS, maifetch_plugin.RETRY_SECONDS, 600]


def test_warmup_follow_up_refresh_after_load() -> None:
    async def scenario() -> list[float]:
        instance = make_plugin()
        await instance.on_load()
        await instance._stop_refresher()
        ok = await instance._refresh_once()
        return [instance._next_delay(ok), instance._next_delay(ok)]

    assert run(scenario()) == [maifetch_plugin.WARMUP_SECONDS, 600]


def test_command_send_exception_reports_maybe_failed() -> None:
    ctx = FakeCtx(send_ok=RuntimeError("RPC 超时"))
    result = run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={}))
    assert result == (False, "状态卡片可能未送达", 2)


def test_tool_send_exception_keeps_text_answer() -> None:
    ctx = FakeCtx(send_ok=RuntimeError("RPC 超时"))
    result = run(make_plugin(ctx).tool_maifetch(send_card=True, stream_id="s1"))
    assert result["success"] is True
    assert result["content"].startswith("状态卡片可能未送达。")
    assert "【身份】" in result["content"]


def test_invalid_base64_render_result_still_sends() -> None:
    ctx = FakeCtx(render_result={"image_base64": "not base64!"})
    result = run(make_plugin(ctx).cmd_maifetch(stream_id="s1", matched_groups={}))
    assert result == (True, "已发送状态卡片", 2)
    assert ctx.sent_images[0][0] == "not base64!"


def test_hook_timeout_tolerates_slow_runner() -> None:
    components = make_plugin().get_components()
    hook = next(c for c in components if c["metadata"].get("hook") == "maisaka.planner.before_request")
    assert hook["metadata"]["timeout_ms"] >= 5000
