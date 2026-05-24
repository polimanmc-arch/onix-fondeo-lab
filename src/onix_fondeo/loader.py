import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_trades(file_path: str = "data/input/sample_trades.csv") -> pd.DataFrame:
    """
    Loads the trades CSV file.

    Expected columns:
    TradeID, EntryTime, ExitTime, Symbol, Direction, Quantity, NetPnL
    """
    full_path = PROJECT_ROOT / file_path

    if not full_path.exists():
        raise FileNotFoundError(f"Trades file not found: {full_path}")

    trades = pd.read_csv(full_path)

    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["ExitTime"] = pd.to_datetime(trades["ExitTime"])

    trades = trades.sort_values("ExitTime").reset_index(drop=True)

    return trades


def load_json_config(file_path: str) -> dict:
    """
    Loads a JSON config file.
    """
    full_path = PROJECT_ROOT / file_path

    if not full_path.exists():
        raise FileNotFoundError(f"Config file not found: {full_path}")

    with open(full_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_all_configs() -> dict:
    """
    Loads all project config files into one dictionary.
    """
    return {
        "evaluation": load_json_config("config/evaluation_rules.json"),
        "funded": load_json_config("config/funded_rules.json"),
        "simulation": load_json_config("config/simulation_settings.json"),
    }


def list_presets(presets_dir: str = "config/presets") -> list[dict]:
    """
    Loads all preset JSON files under the presets directory.
    """
    full_path = PROJECT_ROOT / presets_dir

    if not full_path.exists():
        return []

    presets = []
    for preset_file in full_path.rglob("*.json"):
        with open(preset_file, "r", encoding="utf-8") as file:
            presets.append(json.load(file))

    return sorted(
        presets,
        key=lambda preset: (
            preset.get("company", ""),
            preset.get("plan", ""),
            preset.get("account_size", 0),
        ),
    )


def load_preset(preset_id: str, presets_dir: str = "config/presets") -> dict:
    """
    Loads a preset by preset_id.
    """
    for preset in list_presets(presets_dir):
        if preset.get("preset_id") == preset_id:
            return preset

    raise ValueError(f"Preset not found: {preset_id}")


def config_from_preset(preset: dict) -> dict:
    """
    Converts a preset into the config shape used by the simulator.
    """
    return {
        "evaluation": preset["evaluation"],
        "funded": preset["funded"],
        "simulation": preset["simulation"],
    }


def validate_preset_is_runnable(preset: dict) -> tuple[bool, list[str]]:
    """
    Checks whether a preset has the required rule values to run the simulator.
    """
    missing_fields = []
    evaluation = preset.get("evaluation", {})
    funded = preset.get("funded", {})

    if evaluation.get("enabled", True):
        missing_fields.extend(
            _missing_required_fields(
                section_name="evaluation",
                section=evaluation,
                required_fields=[
                    "profit_target",
                    "max_drawdown",
                    "minimum_trading_days",
                    "consistency_enabled",
                ],
            )
        )
        if evaluation.get("consistency_enabled") is True:
            missing_fields.extend(
                _missing_required_fields(
                    section_name="evaluation",
                    section=evaluation,
                    required_fields=["consistency_percent"],
                )
            )

    if funded.get("enabled", True):
        missing_fields.extend(
            _missing_required_fields(
                section_name="funded",
                section=funded,
                required_fields=[
                    "max_drawdown",
                    "minimum_withdrawable_profit",
                    "payout_trigger_profit",
                    "profit_split",
                    "reset_after_payout",
                ],
            )
        )

    return len(missing_fields) == 0, missing_fields


def _missing_required_fields(
    section_name: str,
    section: dict,
    required_fields: list[str],
) -> list[str]:
    return [
        f"{section_name}.{field_name}"
        for field_name in required_fields
        if section.get(field_name) is None
    ]
