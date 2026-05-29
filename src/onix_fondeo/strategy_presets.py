from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_PRESETS_DIR = PROJECT_ROOT / "config" / "strategy_presets"

STRATEGY_PRESET_FIELDS = [
    # Market data
    "cfg_symbol",
    "cfg_point_value",
    "cfg_utc_offset",
    # Strategy
    "cfg_strategy_name",
    # Stochastic params
    "cfg_stoch_period_k",
    "cfg_stoch_period_d",
    "cfg_stoch_smooth",
    "cfg_stoch_oversold",
    "cfg_stoch_overbought",
    "cfg_stoch_signal_mode",
    "cfg_stoch_use_d_confirmation",
    "cfg_stoch_min_k_d_gap",
    "cfg_stoch_cooldown_bars",
    # Random params
    "cfg_random_probability",
    "cfg_random_seed",
    # Sessions
    "cfg_session_1_enabled",
    "cfg_session_1_start",
    "cfg_session_1_end",
    "cfg_session_2_enabled",
    "cfg_session_2_start",
    "cfg_session_2_end",
    "cfg_session_3_enabled",
    "cfg_session_3_start",
    "cfg_session_3_end",
    # Force close
    "cfg_force_close_enabled",
    "cfg_force_close_time",
    # Risk
    "cfg_contracts",
    "cfg_stop_loss_points",
    "cfg_take_profit_points",
    "cfg_max_holding_minutes",
    # Costs
    "cfg_commission_per_side",
    "cfg_slippage_points",
    "cfg_spread_points",
]


def list_strategy_presets() -> list[dict[str, Any]]:
    """Return strategy preset dictionaries from config/strategy_presets/*.json."""
    if not STRATEGY_PRESETS_DIR.exists():
        return []

    presets = []
    for path in sorted(STRATEGY_PRESETS_DIR.glob("*.json"), key=lambda item: item.name.lower()):
        preset = load_strategy_preset(path.name)
        preset["_filename"] = path.name
        presets.append(preset)
    return presets


def save_strategy_preset(name: str, fields: dict[str, Any]) -> Path:
    """Save a strategy preset using the {name, fields: {...}} format."""
    STRATEGY_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "fields": fields}
    output_path = STRATEGY_PRESETS_DIR / f"{slugify_strategy_preset_name(name)}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, default=str)
    return output_path


def load_strategy_preset(filename: str) -> dict[str, Any]:
    """Load and return a single strategy preset by filename."""
    path = STRATEGY_PRESETS_DIR / Path(filename).name
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def delete_strategy_preset(filename: str) -> None:
    """Delete a strategy preset by filename."""
    path = STRATEGY_PRESETS_DIR / Path(filename).name
    path.unlink(missing_ok=True)


def slugify_strategy_preset_name(name: str) -> str:
    cleaned = "".join(
        character.lower() if character.isalnum() else "_"
        for character in name.strip()
    )
    cleaned = "".join(character for character in cleaned if character.isalnum() or character == "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "strategy_preset"
