from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_PRESETS_DIR = PROJECT_ROOT / "config" / "strategy_presets"


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


def save_strategy_preset(name: str, config: dict[str, Any]) -> Path:
    """Slugify name and write a strategy preset JSON file."""
    STRATEGY_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    preset = dict(config)
    preset["name"] = name
    output_path = STRATEGY_PRESETS_DIR / f"{slugify_strategy_preset_name(name)}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(preset, file, indent=2, default=str)
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
