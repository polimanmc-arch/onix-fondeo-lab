from pathlib import Path

import pandas as pd
import pytest

from onix_fondeo.market_data import load_ohlc_data, validate_ohlc_dataframe


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
