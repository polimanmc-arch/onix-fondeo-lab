from pathlib import Path

import pandas as pd
import pytest

from onix_fondeo.market_data import (
    convert_ninjatrader_export_to_csv,
    load_ninjatrader_export,
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


def test_load_ohlc_data_shifts_datetime_for_utc_offset(tmp_path: Path):
    file_path = tmp_path / "ohlc.csv"
    pd.DataFrame(
        [
            {
                "DateTime": "2026-05-20 14:00:00",
                "Open": 100,
                "High": 101,
                "Low": 99,
                "Close": 100,
            },
        ]
    ).to_csv(file_path, index=False)

    utc_minus_five = load_ohlc_data(str(file_path), timezone="UTC-5")
    utc_minus_four = load_ohlc_data(str(file_path), timezone="UTC-4")
    unshifted = load_ohlc_data(str(file_path), timezone=None)

    assert utc_minus_five.iloc[0]["DateTime"] == pd.Timestamp("2026-05-20 09:00:00")
    assert utc_minus_four.iloc[0]["DateTime"] == pd.Timestamp("2026-05-20 10:00:00")
    assert unshifted.iloc[0]["DateTime"] == pd.Timestamp("2026-05-20 14:00:00")


def test_load_ohlc_data_keeps_rows_from_different_times_of_day(tmp_path: Path):
    file_path = tmp_path / "full_session.csv"
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
                "DateTime": "2026-05-20 16:35:00",
                "Open": 101,
                "High": 102,
                "Low": 100,
                "Close": 101,
            },
            {
                "DateTime": "2026-05-20 18:00:00",
                "Open": 102,
                "High": 103,
                "Low": 101,
                "Close": 102,
            },
        ]
    ).to_csv(file_path, index=False)

    ohlc = load_ohlc_data(str(file_path))

    assert len(ohlc) == 3
    assert [value.strftime("%H:%M") for value in ohlc["DateTime"]] == [
        "09:30",
        "16:35",
        "18:00",
    ]


def test_load_ninjatrader_export_parses_raw_format_and_adds_symbol(tmp_path: Path):
    raw_path = tmp_path / "ninja_export.txt"
    raw_path.write_text(
        "\n".join(
            [
                "20260312 040500;24946.5;24954.5;24946.5;24954.5;6",
                "20260312 040400;24945.25;24949.25;24945.25;24949.25;7",
            ]
        ),
        encoding="utf-8",
    )

    ohlc = load_ninjatrader_export(str(raw_path), symbol="NQ")

    assert list(ohlc.columns) == [
        "DateTime",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Symbol",
    ]
    assert ohlc.iloc[0]["DateTime"] == pd.Timestamp("2026-03-12 04:04:00")
    assert ohlc.iloc[0]["Open"] == 24945.25
    assert ohlc.iloc[0]["Symbol"] == "NQ"


def test_convert_ninjatrader_export_to_csv_writes_standard_format(tmp_path: Path):
    raw_path = tmp_path / "ninja_export.txt"
    output_path = tmp_path / "converted" / "NQ_1m.csv"
    raw_path.write_text(
        "20260312 040400;24945.25;24949.25;24945.25;24949.25;7",
        encoding="utf-8",
    )

    convert_ninjatrader_export_to_csv(
        str(raw_path),
        str(output_path),
        symbol="NQ",
    )

    converted = pd.read_csv(output_path)

    assert list(converted.columns) == [
        "DateTime",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Symbol",
    ]
    assert converted.iloc[0]["DateTime"] == "2026-03-12 04:04:00"
    assert converted.iloc[0]["Symbol"] == "NQ"


def test_load_ninjatrader_export_rejects_malformed_rows(tmp_path: Path):
    raw_path = tmp_path / "bad_export.txt"
    raw_path.write_text(
        "20260312 040400;24945.25;24949.25;24945.25;24949.25",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Malformed NinjaTrader export rows"):
        load_ninjatrader_export(str(raw_path), symbol="NQ")


def test_load_ninjatrader_export_rejects_invalid_ohlc_rows(tmp_path: Path):
    raw_path = tmp_path / "bad_ohlc.txt"
    raw_path.write_text(
        "20260312 040400;24945.25;24944.25;24945.25;24949.25;7",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid OHLC rows found"):
        load_ninjatrader_export(str(raw_path), symbol="NQ")
