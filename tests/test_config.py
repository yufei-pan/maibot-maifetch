from __future__ import annotations

import json
import tomllib
from pathlib import Path

from maifetch.config import (
    BUNDLED_TEMPLATES,
    CURRENT_CONFIG_VERSION,
    DEFAULT_TEMPLATE,
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
    assert cfg.visibility.show_cost is False
    assert (cfg.usage.window_days, cfg.usage.top_models) == (7, 5)
    assert (cfg.injection.enabled, cfg.injection.refresh_minutes) == (True, 10)
    assert (cfg.command.aliases, cfg.command.cooldown_seconds) == ([], 30)
    assert cfg.card.template == DEFAULT_TEMPLATE
    assert (cfg.card.scale, cfg.card.format, cfg.card.render_timeout_ms) == (1.0, "webp", 20000)
    assert cfg.hardware.enabled is False
    assert cfg.hardware.show_cpu is True


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
    normalized, _ = normalize_config_dict(
        {"usage": {"window_days": ""}, "card": {"template": "  ", "format": "GIF"}}
    )
    assert normalized["usage"]["window_days"] == 7
    assert normalized["card"]["template"] == DEFAULT_TEMPLATE
    assert normalized["card"]["format"] == "webp"


def test_normalize_aliases_are_literal_and_deduplicated() -> None:
    normalized, _ = normalize_config_dict(
        {"command": {"aliases": [" /状态 ", "/状态", "", "/maifetch", "麦麦状态"]}}
    )
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
