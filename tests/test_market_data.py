from pathlib import Path

import pandas as pd
import pytest

from onix_fondeo.market_data import (
    load_ohlc_data,
    normalize_ohlc_columns,
    validate_ohlc_dataframe,
)


def test_load_ohlc_data_sorts_parses_and_adds_symbol(tmp_path: Path):
    file_path = tmp_path / "ohlc.csv"
    pd.DataFrame(
        [
            {
                "DateTime": "2026-05-20 09:31:00",
                "Open": "101",
                "High": "102",
                "Low": "100",
                "Close": "101.5",
            },
            {
                "DateTime": "2026-05-20 09:30:00",
                "Open": "100",
                "High": "101",
                "Low": "99",
                "Close": "100.5",
            },
        ]
    ).to_csv(file_path, index=False)

    ohlc = load_ohlc_data(str(file_path), symbol="NQ")

    assert list(ohlc["Symbol"]) == ["NQ", "NQ"]
    assert ohlc.iloc[0]["DateTime"] == pd.Timestamp("2026-05-20 09:30:00")
    assert ohlc.iloc[0]["Open"] == 100


def test_validate_ohlc_dataframe_rejects_missing_columns():
    df = pd.DataFrame({"DateTime": ["2026-05-20 09:30:00"], "Open": [100]})

    with pytest.raises(ValueError, match="Missing required OHLC columns"):
        validate_ohlc_dataframe(df)


def test_validate_ohlc_dataframe_rejects_invalid_numeric_values():
    df = pd.DataFrame(
        {
            "DateTime": ["2026-05-20 09:30:00"],
            "Open": ["bad"],
            "High": [101],
            "Low": [99],
            "Close": [100],
        }
    )

    with pytest.raises(ValueError, match="Invalid numeric values"):
        validate_ohlc_dataframe(df)


def test_normalize_ohlc_columns_supports_common_aliases():
    df = pd.DataFrame(
        {
            " Time ": ["2026-05-20 09:30:00"],
            "O": [100],
            "H": [101],
            "L": [99],
            "C": [100.5],
            "Vol": [1000],
            "Extra": ["kept"],
        }
    )

    normalized = normalize_ohlc_columns(df)

    assert {"DateTime", "Open", "High", "Low", "Close", "Volume"}.issubset(
        normalized.columns
    )
    assert "Extra" in normalized.columns


def test_load_ohlc_data_drops_duplicate_datetimes_when_enabled(tmp_path: Path):
    file_path = tmp_path / "duplicates.csv"
    pd.DataFrame(
        [
            {
                "Time": "2026-05-20 09:30:00",
                "O": 100,
                "H": 101,
                "L": 99,
                "C": 100,
            },
            {
                "Time": "2026-05-20 09:30:00",
                "O": 101,
                "H": 102,
                "L": 100,
                "C": 101,
            },
        ]
    ).to_csv(file_path, index=False)

    ohlc = load_ohlc_data(str(file_path), drop_duplicate_datetimes=True)

    assert len(ohlc) == 1
    assert ohlc.iloc[0]["Open"] == 101


def test_load_ohlc_data_preserves_duplicate_datetimes_when_disabled(tmp_path: Path):
    file_path = tmp_path / "duplicates.csv"
    pd.DataFrame(
        [
            {
                "DateTime": "2026-05-20 09:30:00",
                "Open": 100,
                "High": 101,
                "Low": 99,
                "Close": 100,
            },
            {
                "DateTime": "2026-05-20 09:30:00",
                "Open": 101,
                "High": 102,
                "Low": 100,
                "Close": 101,
            },
        ]
    ).to_csv(file_path, index=False)

    ohlc = load_ohlc_data(str(file_path), drop_duplicate_datetimes=False)

    assert len(ohlc) == 2


def test_validate_ohlc_dataframe_rejects_invalid_ohlc_rows():
    df = pd.DataFrame(
        {
            "DateTime": ["2026-05-20 09:30:00"],
            "Open": [100],
            "High": [99],
            "Low": [98],
            "Close": [100],
        }
    )

    with pytest.raises(ValueError, match="Invalid OHLC rows found: 1"):
        validate_ohlc_dataframe(df)


def test_load_ohlc_data_stores_timezone_attr(tmp_path: Path):
    file_path = tmp_path / "ohlc.csv"
    pd.DataFrame(
        [
            {
                "Date": "2026-05-20 09:30:00",
                "Open": 100,
                "High": 101,
                "Low": 99,
                "Last": 100,
            },
        ]
    ).to_csv(file_path, index=False)

    ohlc = load_ohlc_data(str(file_path), symbol="NQ", timezone="America/New_York")

    assert ohlc.attrs["timezone"] == "America/New_York"
    assert ohlc.iloc[0]["Symbol"] == "NQ"
