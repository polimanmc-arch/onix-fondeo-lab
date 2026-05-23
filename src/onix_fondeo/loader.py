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