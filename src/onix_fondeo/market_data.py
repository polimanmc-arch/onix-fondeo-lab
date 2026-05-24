from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_OHLC_COLUMNS = ["DateTime", "Open", "High", "Low", "Close"]


def load_ohlc_data(file_path: str, symbol: Optional[str] = None) -> pd.DataFrame:
    full_path = Path(file_path)
    if not full_path.is_absolute():
        full_path = PROJECT_ROOT / file_path

    ohlc = pd.read_csv(full_path)
    validate_ohlc_dataframe(ohlc)

    ohlc = ohlc.copy()
    ohlc["DateTime"] = pd.to_datetime(ohlc["DateTime"])

    for column in ["Open", "High", "Low", "Close"]:
        ohlc[column] = pd.to_numeric(ohlc[column], errors="coerce")

    if "Volume" in ohlc.columns:
        ohlc["Volume"] = pd.to_numeric(ohlc["Volume"], errors="coerce")

    if "Symbol" not in ohlc.columns and symbol is not None:
        ohlc["Symbol"] = symbol

    validate_ohlc_dataframe(ohlc)
    return ohlc.sort_values("DateTime").reset_index(drop=True)


def validate_ohlc_dataframe(df: pd.DataFrame) -> None:
    missing_columns = [
        column for column in REQUIRED_OHLC_COLUMNS if column not in df.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required OHLC columns: {missing}")

    for column in ["Open", "High", "Low", "Close"]:
        numeric_values = pd.to_numeric(df[column], errors="coerce")
        if numeric_values.isna().any():
            raise ValueError(f"Invalid numeric values found in column: {column}")

    if "Volume" in df.columns:
        volume_values = pd.to_numeric(df["Volume"], errors="coerce")
        if volume_values.isna().any():
            raise ValueError("Invalid numeric values found in column: Volume")
