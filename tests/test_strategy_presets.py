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
    config = _strategy_preset_config()

    output_path = save_strategy_preset("My Setup", config)

    assert output_path == tmp_path / "my_setup.json"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["name"] == "My Setup"
    assert saved["strategy_name"] == "stochastic"
    assert saved["strategy_params"]["signal_mode"] == "d_cross"


def test_list_strategy_presets_returns_saved_presets(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_presets, "STRATEGY_PRESETS_DIR", tmp_path)
    save_strategy_preset("My Setup", _strategy_preset_config())

    presets = list_strategy_presets()

    assert len(presets) == 1
    assert presets[0]["name"] == "My Setup"
    assert presets[0]["_filename"] == "my_setup.json"


def test_load_strategy_preset_returns_correct_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_presets, "STRATEGY_PRESETS_DIR", tmp_path)
    save_strategy_preset("My Setup", _strategy_preset_config())

    preset = load_strategy_preset("my_setup.json")

    assert preset["contracts"] == 1.0
    assert preset["stop_loss_points"] == 70.0


def test_delete_strategy_preset_removes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_presets, "STRATEGY_PRESETS_DIR", tmp_path)
    output_path = save_strategy_preset("My Setup", _strategy_preset_config())

    delete_strategy_preset("my_setup.json")

    assert not output_path.exists()


def _strategy_preset_config():
    return {
        "name": "My Setup",
        "strategy_name": "stochastic",
        "strategy_params": {
            "period_k": 20,
            "period_d": 5,
            "smooth": 5,
            "oversold": 20,
            "overbought": 80,
            "signal_mode": "d_cross",
        },
        "start_time": "09:45",
        "end_time": "16:00",
        "force_close_time": "16:00",
        "contracts": 1.0,
        "stop_loss_points": 70.0,
        "take_profit_points": 140.0,
        "max_holding_minutes": 120,
        "commission_per_side": 2.0,
        "slippage_points": 0.0,
        "spread_points": 0.0,
    }
