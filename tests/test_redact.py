from __future__ import annotations

from dataclasses import replace

from maifetch.config import MaiFetchConfig, build_settings
from maifetch.redact import apply_visibility
from maifetch.sample import sample_snapshot


def _settings(overrides: dict):
    return build_settings(MaiFetchConfig.model_validate(overrides))


def _raw():
    return sample_snapshot(hardware=True, cost=True, account=True)


def test_defaults_hide_only_account() -> None:
    s = _settings({})
    out = apply_visibility(_raw(), s.visibility, s.hardware)
    assert out.identity.account is None
    assert out.usage.total_cost == 4.87
    assert out.hardware is not None and out.hardware.cpu is not None
    assert out.runtime.plugins is not None
    assert out.runtime.plugin_count == 12


def test_cost_and_hardware_can_be_turned_off() -> None:
    s = _settings({"visibility": {"show_cost": False}, "hardware": {"enabled": False}})
    out = apply_visibility(_raw(), s.visibility, s.hardware)
    assert out.usage.total_cost is None
    assert all(m.cost is None for m in out.usage.models)
    assert out.hardware is None


def test_everything_visible() -> None:
    s = _settings({"visibility": {"show_account": True, "show_cost": True}, "hardware": {"enabled": True}})
    out = apply_visibility(_raw(), s.visibility, s.hardware)
    assert out.identity.account == "123456789"
    assert out.usage.total_cost == 4.87
    assert out.hardware is not None and out.hardware.cpu is not None


def test_plugin_list_hidden_keeps_count() -> None:
    s = _settings({"visibility": {"show_plugin_list": False}})
    out = apply_visibility(_raw(), s.visibility, s.hardware)
    assert out.runtime.plugins is None
    assert out.runtime.plugin_count == 12


def test_individual_hardware_toggles() -> None:
    s = _settings({"hardware": {"enabled": True, "show_cpu": False, "show_memory": False, "show_virt": False}})
    out = apply_visibility(_raw(), s.visibility, s.hardware)
    hw = out.hardware
    assert hw is not None
    assert hw.cpu is None and hw.cpu_cores is None
    assert hw.mem_used is None and hw.mem_total is None
    assert hw.virt is None
    assert hw.os is not None and hw.disk_total is not None


def test_cost_ranking_hidden_with_cost() -> None:
    s = _settings({"visibility": {"show_cost": False}})
    out = apply_visibility(_raw(), s.visibility, s.hardware, show_by_requests=True, show_by_cost=True)
    assert out.usage.models_by_cost == ()
    assert out.usage.costed_model_count is None
    assert out.usage.show_cost_ranking is False


def test_ranking_toggles() -> None:
    s = _settings({})
    out = apply_visibility(_raw(), s.visibility, s.hardware, show_by_requests=False, show_by_cost=False)
    assert out.usage.show_request_ranking is False
    assert out.usage.show_cost_ranking is False
    assert out.usage.models_by_cost == ()
    assert len(out.usage.models) == 3  # 规划器注入仍需要主要模型名


def test_currency_symbol_hidden_with_cost() -> None:
    raw = _raw()
    raw = replace(raw, usage=replace(raw.usage, currency_symbol="₿"))
    shown = _settings({})
    assert apply_visibility(raw, shown.visibility, shown.hardware).usage.currency_symbol == "₿"
    hidden = _settings({"visibility": {"show_cost": False}})
    assert apply_visibility(raw, hidden.visibility, hidden.hardware).usage.currency_symbol == ""
