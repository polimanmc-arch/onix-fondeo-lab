import json

import onix_fondeo.strategy_presets as strategy_presets
from onix_fondeo.strategy_presets import (
    delete_strategy_preset,
    list_strategy_presets,
    load_strategy_preset,
    save_strategy_preset,
)


def test_save_strategy_preset_writes_correct_json(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_presets, "STRATEGY_PRESETS_DIR", tmp_path)
    fields = _strategy_preset_fields()

    output_path = save_strategy_preset("My Setup", fields)

    assert output_path == tmp_path / "my_setup.json"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["name"] == "My Setup"
    assert saved["fields"]["cfg_strategy_name"] == "stochastic"
    assert saved["fields"]["cfg_stoch_signal_mode"] == "d_cross"


def test_list_strategy_presets_returns_saved_presets(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_presets, "STRATEGY_PRESETS_DIR", tmp_path)
    save_strategy_preset("My Setup", _strategy_preset_fields())

    presets = list_strategy_presets()

    assert len(presets) == 1
    assert presets[0]["name"] == "My Setup"
    assert presets[0]["_filename"] == "my_setup.json"


def test_load_strategy_preset_returns_correct_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_presets, "STRATEGY_PRESETS_DIR", tmp_path)
    save_strategy_preset("My Setup", _strategy_preset_fields())

    data = load_strategy_preset("my_setup.json")

    assert data["fields"]["cfg_contracts"] == 1.0
    assert data["fields"]["cfg_stop_loss_points"] == 70.0


def test_delete_strategy_preset_removes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_presets, "STRATEGY_PRESETS_DIR", tmp_path)
    output_path = save_strategy_preset("My Setup", _strategy_preset_fields())

    delete_strategy_preset("my_setup.json")

    assert not output_path.exists()


def _strategy_preset_fields() -> dict:
    return {
        "cfg_strategy_name": "stochastic",
        "cfg_stoch_period_k": 20,
        "cfg_stoch_period_d": 5,
        "cfg_stoch_smooth": 5,
        "cfg_stoch_oversold": 20,
        "cfg_stoch_overbought": 80,
        "cfg_stoch_signal_mode": "d_cross",
        "cfg_session_1_enabled": True,
        "cfg_session_1_start": "09:45",
        "cfg_session_1_end": "12:00",
        "cfg_session_2_enabled": False,
        "cfg_session_3_enabled": False,
        "cfg_force_close_enabled": True,
        "cfg_force_close_time": "16:00",
        "cfg_contracts": 1.0,
        "cfg_stop_loss_points": 70.0,
        "cfg_take_profit_points": 140.0,
        "cfg_max_holding_minutes": 120,
        "cfg_commission_per_side": 2.0,
        "cfg_slippage_points": 0.0,
        "cfg_spread_points": 0.0,
    }
