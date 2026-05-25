from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_OHLC_COLUMNS = ["DateTime", "Open", "High", "Low", "Close"]
OHLC_COLUMN_ALIASES = {
    "Time": "DateTime",
    "Date": "DateTime",
    "Datetime": "DateTime",
    "Timestamp": "DateTime",
    "O": "Open",
    "H": "High",
    "L": "Low",
    "C": "Close",
    "Last": "Close",
    "Vol": "Volume",
}


def load_ohlc_data(
    file_path: str,
    symbol: Optional[str] = None,
    drop_duplicate_datetimes: bool = True,
    timezone: Optional[str] = None,
) -> pd.DataFrame:
    full_path = Path(file_path)
    if not full_path.is_absolute():
        full_path = PROJECT_ROOT / file_path

    ohlc = normalize_ohlc_columns(pd.read_csv(full_path))
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

    if drop_duplicate_datetimes:
        ohlc = ohlc.drop_duplicates(subset=["DateTime"], keep="last")

    ohlc = ohlc.sort_values("DateTime").reset_index(drop=True)
    if timezone is not None:
        ohlc.attrs["timezone"] = timezone

    return ohlc


def normalize_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    stripped_columns = {column: str(column).strip() for column in normalized.columns}
    normalized = normalized.rename(columns=stripped_columns)
    normalized = normalized.rename(columns=OHLC_COLUMN_ALIASES)
    return normalized


def validate_ohlc_dataframe(df: pd.DataFrame) -> None:
    df = normalize_ohlc_columns(df)
    missing_columns = [
        column for column in REQUIRED_OHLC_COLUMNS if column not in df.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required OHLC columns: {missing}")

    parsed_datetime = pd.to_datetime(df["DateTime"], errors="coerce")
    if parsed_datetime.isna().any():
        raise ValueError("Invalid DateTime values found in OHLC data")

    numeric_columns = {}
    for column in ["Open", "High", "Low", "Close"]:
        numeric_values = pd.to_numeric(df[column], errors="coerce")
        if numeric_values.isna().any():
            raise ValueError(f"Invalid numeric values found in column: {column}")
        numeric_columns[column] = numeric_values

    if "Volume" in df.columns:
        volume_values = pd.to_numeric(df["Volume"], errors="coerce")
        if volume_values.isna().any():
            raise ValueError("Invalid numeric values found in column: Volume")

    max_open_close = pd.concat(
        [numeric_columns["Open"], numeric_columns["Close"]],
        axis=1,
    ).max(axis=1)
    min_open_close = pd.concat(
        [numeric_columns["Open"], numeric_columns["Close"]],
        axis=1,
    ).min(axis=1)
    invalid_ohlc_rows = (
        (numeric_columns["High"] < max_open_close)
        | (numeric_columns["Low"] > min_open_close)
    )
    invalid_count = int(invalid_ohlc_rows.sum())
    if invalid_count:
        raise ValueError(f"Invalid OHLC rows found: {invalid_count}")
