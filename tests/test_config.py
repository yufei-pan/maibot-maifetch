from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomllib
from maibot_sdk.config import generate_plugin_config_schema

from maifetch.config import (
    BUNDLED_TEMPLATES,
    CURRENCY_CHOICES,
    CURRENT_CONFIG_VERSION,
    CUSTOM_CURRENCY,
    DEFAULT_TEMPLATE,
    MAX_CUSTOM_CURRENCY_LENGTH,
    MaiFetchConfig,
    build_settings,
    ensure_shipped_config_present,
    normalize_config_dict,
)

PLUGIN_DIR = Path(__file__).resolve().parent.parent


def test_defaults_match_spec() -> None:
    cfg = MaiFetchConfig()
    assert cfg.plugin.enabled is True
    assert cfg.visibility.show_account is False
    assert cfg.visibility.show_plugin_list is True
    assert cfg.visibility.show_cost is True
    assert (cfg.usage.window_days, cfg.usage.top_models) == (7, 5)
    assert (cfg.injection.enabled, cfg.injection.refresh_minutes) == (True, 10)
    assert (cfg.command.aliases, cfg.command.cooldown_seconds) == ([], 30)
    assert cfg.card.template == DEFAULT_TEMPLATE
    assert (cfg.card.scale, cfg.card.format, cfg.card.render_timeout_ms) == (1.0, "webp", 20000)
    assert cfg.hardware.enabled is True
    assert cfg.hardware.show_cpu is True


def test_hardware_texts_warn_without_showoff_wording() -> None:
    from maifetch.config import HardwareSectionConfig

    assert HardwareSectionConfig.__ui_label__ == "硬件信息"
    description = HardwareSectionConfig.model_fields["enabled"].description or ""
    assert "群聊" in description and "关闭" in description
    shipped = (PLUGIN_DIR / "config.default.toml").read_text(encoding="utf-8")
    for text in (HardwareSectionConfig.__ui_label__, description, shipped):
        assert "炫耀" not in text


def test_normalize_empty_gives_defaults_without_notes() -> None:
    normalized, notes = normalize_config_dict({})
    assert notes == []
    assert normalized == MaiFetchConfig().model_dump(mode="python")


def test_normalize_clamps_and_recovers_numbers() -> None:
    normalized, notes = normalize_config_dict(
        {
            "usage": {"window_days": 400, "top_models": "3"},
            "card": {"scale": "abc", "render_timeout_ms": 10},
            "command": {"cooldown_seconds": -5},
        }
    )
    assert normalized["usage"]["window_days"] == 90
    assert normalized["usage"]["top_models"] == 3
    assert normalized["card"]["scale"] == 1.0
    assert normalized["card"]["render_timeout_ms"] == 1000
    assert normalized["command"]["cooldown_seconds"] == 0
    joined = "；".join(notes)
    assert "usage.window_days" in joined
    assert "card.scale" in joined


def test_normalize_blank_webui_values() -> None:
    normalized, _ = normalize_config_dict({"usage": {"window_days": ""}, "card": {"template": "  ", "format": "GIF"}})
    assert normalized["usage"]["window_days"] == 7
    assert normalized["card"]["template"] == DEFAULT_TEMPLATE
    assert normalized["card"]["format"] == "webp"


def test_normalize_aliases_are_literal_and_deduplicated() -> None:
    normalized, _ = normalize_config_dict({"command": {"aliases": [" /状态 ", "/状态", "", "/maifetch", "麦麦状态"]}})
    assert normalized["command"]["aliases"] == ["/状态", "麦麦状态"]


def test_normalize_accepts_single_alias_string() -> None:
    normalized, _ = normalize_config_dict({"command": {"aliases": "/状态"}})
    assert normalized["command"]["aliases"] == ["/状态"]


def test_normalize_stamps_version() -> None:
    normalized, notes = normalize_config_dict({"plugin": {"config_version": "0.0.1"}})
    assert normalized["plugin"]["config_version"] == CURRENT_CONFIG_VERSION
    assert any("config_version" in note for note in notes)


def test_build_settings_flattens() -> None:
    settings = build_settings(
        MaiFetchConfig.model_validate(
            {"hardware": {"enabled": True, "show_disk": False}, "command": {"aliases": ["/状态"]}}
        )
    )
    assert settings.hardware.enabled is True
    assert settings.hardware.disk is False
    assert settings.hardware.cpu is True
    assert settings.aliases == ("/状态",)
    assert settings.image_format == "webp"
    assert settings.visibility.show_plugin_list is True


def test_build_settings_clamps_unnormalized_model() -> None:
    cfg = MaiFetchConfig.model_validate({"usage": {"window_days": 1000}})
    assert build_settings(cfg).window_days == 90


def test_bundled_template_names() -> None:
    assert BUNDLED_TEMPLATES == ("dashboard", "terminal", "sheet")


def test_ensure_shipped_config_present(tmp_path: Path) -> None:
    (tmp_path / "config.default.toml").write_text("[plugin]\nenabled = true\n", encoding="utf-8")
    assert ensure_shipped_config_present(tmp_path) is True
    assert (tmp_path / "config.toml").read_text(encoding="utf-8").startswith("[plugin]")
    assert ensure_shipped_config_present(tmp_path) is False


def test_shipped_default_toml_matches_model() -> None:
    data = tomllib.loads((PLUGIN_DIR / "config.default.toml").read_text(encoding="utf-8"))
    normalized, notes = normalize_config_dict(data)
    assert notes == []
    assert normalized == MaiFetchConfig().model_dump(mode="python")


def test_manifest_matches_spec() -> None:
    manifest = json.loads((PLUGIN_DIR / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 2
    assert manifest["id"] == "com.0-hz.maifetch"
    assert manifest["version"] == "0.1.0"
    assert manifest["host_application"] == {"min_version": "1.3.1", "max_version": "1.99.99"}
    assert manifest["sdk"] == {"min_version": "2.8.2", "max_version": "2.99.99"}
    assert set(manifest["capabilities"]) == {
        "config.get",
        "database.get",
        "component.get_all_plugins",
        "llm.get_available_models",
        "statistics.local.models",
        "statistics.local.message_trend",
        "render.html2png",
        "send.text",
        "send.image",
    }


def test_ranking_toggles_default_on_and_flatten() -> None:
    cfg = MaiFetchConfig()
    assert cfg.usage.show_by_requests is True
    assert cfg.usage.show_by_cost is True
    settings = build_settings(MaiFetchConfig.model_validate({"usage": {"show_by_cost": False}}))
    assert settings.show_by_requests is True
    assert settings.show_by_cost is False


def test_currency_defaults_and_webui_schema() -> None:
    cfg = MaiFetchConfig()
    assert (cfg.usage.currency_symbol, cfg.usage.custom_currency_symbol) == ("¥", "")
    fields = generate_plugin_config_schema(MaiFetchConfig)["sections"]["usage"]["fields"]
    assert fields["currency_symbol"]["ui_type"] == "select"
    assert fields["currency_symbol"]["choices"] == list(CURRENCY_CHOICES)
    assert {"¥", "$", "€", "£", CUSTOM_CURRENCY} <= set(CURRENCY_CHOICES)
    # 自定义符号只在 config.toml 里写，WebUI 不显示
    assert fields["custom_currency_symbol"]["hidden"] is True


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        ({}, "¥"),
        ({"currency_symbol": "$"}, "$"),
        ({"currency_symbol": CUSTOM_CURRENCY, "custom_currency_symbol": " ₿ "}, "₿"),
        ({"currency_symbol": CUSTOM_CURRENCY}, "¥"),
        ({"currency_symbol": "€", "custom_currency_symbol": "₿"}, "€"),
    ],
)
def test_build_settings_resolves_currency_symbol(usage: dict, expected: str) -> None:
    assert build_settings(MaiFetchConfig.model_validate({"usage": usage})).currency_symbol == expected


def test_normalize_listed_currency_needs_no_notes() -> None:
    normalized, notes = normalize_config_dict({"usage": {"currency_symbol": "€"}})
    assert notes == []
    assert normalized["usage"]["currency_symbol"] == "€"


def test_normalize_turns_unlisted_symbol_into_custom() -> None:
    normalized, notes = normalize_config_dict({"usage": {"currency_symbol": " ₿ "}})
    assert normalized["usage"]["currency_symbol"] == CUSTOM_CURRENCY
    assert normalized["usage"]["custom_currency_symbol"] == "₿"
    assert any("usage.currency_symbol" in note for note in notes)
    # 再规范化一次不应再有变更（否则每次加载都会改写配置）
    again, again_notes = normalize_config_dict(normalized)
    assert again_notes == []
    assert again == normalized


def test_normalize_accepts_english_custom_keyword() -> None:
    normalized, _ = normalize_config_dict({"usage": {"currency_symbol": "Custom", "custom_currency_symbol": "₿"}})
    assert normalized["usage"]["currency_symbol"] == CUSTOM_CURRENCY
    assert normalized["usage"]["custom_currency_symbol"] == "₿"


def test_normalize_blank_currency_and_cleans_custom() -> None:
    normalized, notes = normalize_config_dict({"usage": {"currency_symbol": " ", "custom_currency_symbol": " 元\n "}})
    assert normalized["usage"]["currency_symbol"] == "¥"
    assert normalized["usage"]["custom_currency_symbol"] == "元"
    assert any("usage.currency_symbol" in note for note in notes)


def test_normalize_truncates_long_custom_symbol() -> None:
    normalized, notes = normalize_config_dict(
        {"usage": {"currency_symbol": CUSTOM_CURRENCY, "custom_currency_symbol": "X" * 20}}
    )
    assert normalized["usage"]["custom_currency_symbol"] == "X" * MAX_CUSTOM_CURRENCY_LENGTH
    assert any("usage.custom_currency_symbol" in note for note in notes)
