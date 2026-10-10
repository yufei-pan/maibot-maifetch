from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from fakes import FakeCtx, make_settings

import maifetch.collect as collect_module
from maifetch.collect import STATS_ROW_CAP, collect_snapshot
from maifetch.snapshot import Hardware

NOW = datetime(2026, 10, 1, 14, 24).astimezone()


def _collect(ctx: FakeCtx, overrides: dict | None = None, tmp: Path = Path(".")):
    return asyncio.run(collect_snapshot(ctx, make_settings(overrides), plugin_version="0.1.0", plugin_dir=tmp, now=NOW))


def test_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIBOT_HOST_VERSION", "1.3.1")
    ctx = FakeCtx()
    snap = _collect(ctx)
    assert snap.failed_sources == ()
    assert snap.identity.nickname == "麦麦"
    assert snap.identity.alias_names == ("小麦",)
    assert snap.identity.platforms == ("qq", "email")
    assert snap.identity.account is None
    assert snap.identity.local_time == NOW
    assert snap.runtime.host_version == "1.3.1"
    assert snap.runtime.sdk_version == "2.8.2"
    assert snap.runtime.plugin_version == "0.1.0"
    assert [p.plugin_id for p in snap.runtime.plugins or ()] == ["com.0-hz.maibook", "com.0-hz.maifetch"]
    assert snap.runtime.plugin_count == 2
    assert snap.runtime.tool_count == 2
    assert snap.runtime.model_tasks == ("replyer", "planner", "utils", "vlm", "voice")
    assert snap.runtime.online_since == datetime(2026, 9, 28, 10, 2).astimezone()
    assert [m.model_name for m in snap.usage.models] == ["deepseek-v3.2", "qwen3-235b", "glm-4.6v"]
    assert snap.usage.total_requests == 1774
    assert snap.usage.total_tokens == 2_410_000
    assert snap.usage.total_cost == pytest.approx(4.87)
    assert snap.usage.total_messages == 3906
    assert snap.usage.totals_capped is False and snap.usage.messages_capped is False
    assert isinstance(snap.hardware, Hardware)  # 硬件信息默认开启
    asked = [kwargs.get("key") for name, kwargs in ctx.calls if name == "config.get"]
    assert "bot.qq_account" not in asked


def test_show_account_fetches_account() -> None:
    snap = _collect(FakeCtx(), {"visibility": {"show_account": True}})
    assert snap.identity.account == "123456789"


def test_top_models_limit() -> None:
    snap = _collect(FakeCtx(), {"usage": {"top_models": 1}})
    assert [m.model_name for m in snap.usage.models] == ["deepseek-v3.2"]
    assert snap.usage.total_requests == 1774
    assert snap.usage.model_count == 3


def test_stats_requested_with_cap_and_window() -> None:
    ctx = FakeCtx()
    _collect(ctx, {"usage": {"window_days": 14}})
    calls = dict(ctx.calls)
    assert calls["statistics.local.models"] == {"days": 14, "limit": STATS_ROW_CAP}
    assert calls["statistics.local.message_trend"]["top_chats"] == STATS_ROW_CAP


def test_models_failure_dict_marks_failed() -> None:
    ctx = FakeCtx({"statistics.local.models": {"success": False, "error": "db locked"}})
    snap = _collect(ctx)
    assert "models" in snap.failed_sources
    assert snap.usage.total_requests is None
    assert snap.usage.models == ()
    assert snap.usage.total_messages == 3906


def test_exception_marks_failed() -> None:
    snap = _collect(FakeCtx({"component.get_all_plugins": RuntimeError("rpc closed")}))
    assert snap.failed_sources == ("plugins",)
    assert snap.runtime.plugin_count is None


def test_timeout_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect_module, "SOURCE_TIMEOUT_S", 0.05)
    snap = _collect(FakeCtx(delay={"statistics.local.message_trend": 1.0}))
    assert snap.failed_sources == ("messages",)
    assert snap.usage.total_messages is None


def test_capped_totals() -> None:
    rows = [{"model_name": f"m{i}", "request_count": 1, "total_tokens": 1} for i in range(STATS_ROW_CAP)]
    series = {"values_by_key": {f"c{i}": [1.0] for i in range(STATS_ROW_CAP)}, "total": 50.0}
    snap = _collect(
        FakeCtx({"statistics.local.models": lambda **_: rows, "statistics.local.message_trend": lambda **_: series})
    )
    assert snap.usage.totals_capped is True
    assert snap.usage.messages_capped is True


def test_chat_labels_never_reach_snapshot() -> None:
    assert "秘密群" not in repr(_collect(FakeCtx()))


def test_no_online_rows_is_not_a_failure() -> None:
    snap = _collect(FakeCtx({"database.get": lambda **_: None}))
    assert snap.runtime.online_since is None
    assert "online" not in snap.failed_sources


def test_hardware_only_when_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(_path: Path) -> Hardware:
        raise AssertionError("hardware must not be collected when disabled")

    monkeypatch.setattr(collect_module, "collect_hardware", boom)
    assert _collect(FakeCtx(), {"hardware": {"enabled": False}}, tmp_path).hardware is None

    monkeypatch.setattr(collect_module, "collect_hardware", lambda _path: Hardware(os="TestOS"))
    snap = _collect(FakeCtx(), {"hardware": {"enabled": True}}, tmp_path)
    assert snap.hardware == Hardware(os="TestOS")


def test_identity_failure_keeps_local_time() -> None:
    snap = _collect(FakeCtx({"config.get": {"success": False, "error": "x"}}))
    assert "identity" in snap.failed_sources
    assert snap.identity.nickname is None
    assert snap.identity.local_time == NOW


def test_platform_account_entries_never_leak() -> None:
    """bot.platforms 的格式是 platform:账号；账号 ID 不得出现在任何输出面。"""
    from maifetch.card import build_card_html, build_data_json, build_fragments, build_scalars
    from maifetch.text import format_injection, format_tool_text, format_user_text

    values = {
        "bot.nickname": "麦麦",
        "bot.platform": "qq",
        "bot.platforms": ["telegram:7712345678", "QQ:3141592653", "napcat:123456:extra", "email"],
    }
    ctx = FakeCtx({"config.get": lambda key, default=None: values.get(key, default)})
    snap = _collect(ctx)
    assert snap.identity.platforms == ("qq", "telegram", "napcat", "email")
    surfaces = "\n".join(
        [
            format_injection(snap),
            format_tool_text(snap),
            format_user_text(snap),
            *build_scalars(snap).values(),
            *build_fragments(snap).values(),
            build_data_json(snap),
            build_card_html(snap, '<div id="card">{platforms}</div>'),
        ]
    )
    for secret in ("7712345678", "3141592653", "123456"):
        assert secret not in surfaces, secret


def test_cost_ranking_from_same_rows() -> None:
    rows = [
        {"model_name": "cheap-busy", "request_count": 900, "total_tokens": 9_000, "total_cost": 0.10},
        {"model_name": "pricey", "request_count": 10, "total_tokens": 1_000, "total_cost": 2.50},
        {"model_name": "free", "request_count": 500, "total_tokens": 5_000, "total_cost": 0.0},
        {"model_name": "unknown-cost", "request_count": 5, "total_tokens": 50},
    ]
    snap = _collect(FakeCtx({"statistics.local.models": lambda **_: rows}), {"usage": {"top_models": 5}})
    assert [m.model_name for m in snap.usage.models_by_cost] == ["pricey", "cheap-busy"]
    assert snap.usage.costed_model_count == 2
    assert snap.usage.models[0].model_name == "cheap-busy"


def test_currency_symbol_comes_from_settings() -> None:
    assert _collect(FakeCtx()).usage.currency_symbol == "¥"
    snap = _collect(FakeCtx(), {"usage": {"currency_symbol": "自定义", "custom_currency_symbol": "₿"}})
    assert snap.usage.currency_symbol == "₿"
