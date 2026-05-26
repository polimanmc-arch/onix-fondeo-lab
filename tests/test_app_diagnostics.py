from __future__ import annotations

import pandas as pd
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import (
    build_trade_diagnostics,
    compute_stochastic_for_chart,
    filter_trades_for_explorer,
    filter_trades_for_chart,
    prepare_trade_pnl_chart_data,
)


def test_build_trade_diagnostics_calculates_overtrading_metrics():
    trades = pd.DataFrame(
        [
            {
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "NetPnL": 100,
                "GrossPnL": 110,
                "TotalCost": 10,
                "ExitReason": "TP",
            },
            {
                "EntryTime": "2024-01-02 10:00:00",
                "ExitTime": "2024-01-02 10:20:00",
                "NetPnL": -50,
                "GrossPnL": -40,
                "TotalCost": 10,
                "ExitReason": "SL",
            },
            {
                "EntryTime": "2024-01-03 09:30:00",
                "ExitTime": "2024-01-03 09:45:00",
                "NetPnL": 25,
                "GrossPnL": 30,
                "TotalCost": 5,
                "ExitReason": "TIME",
            },
        ]
    )

    diagnostics = build_trade_diagnostics(trades)

    assert diagnostics["overtrading"]["total_trades"] == 3
    assert diagnostics["overtrading"]["unique_trading_days"] == 2
    assert diagnostics["overtrading"]["average_trades_per_day"] == 1.5
    assert diagnostics["overtrading"]["max_trades_in_one_day"] == 2
    assert diagnostics["overtrading"]["median_holding_minutes"] == 15


def test_build_trade_diagnostics_handles_missing_cost_columns():
    trades = pd.DataFrame(
        [
            {
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "NetPnL": 100,
            }
        ]
    )

    diagnostics = build_trade_diagnostics(trades)

    assert diagnostics["costs"]["total_cost"] == 0
    assert diagnostics["costs"]["total_commission"] == 0
    assert diagnostics["costs"]["net_pnl"] == 100


def test_build_trade_diagnostics_exit_reason_table():
    trades = pd.DataFrame(
        [
            {"ExitTime": "2024-01-02 09:40:00", "NetPnL": 100, "ExitReason": "TP"},
            {"ExitTime": "2024-01-02 09:41:00", "NetPnL": 50, "ExitReason": "TP"},
            {"ExitTime": "2024-01-02 09:42:00", "NetPnL": -25, "ExitReason": "SL"},
        ]
    )

    table = build_trade_diagnostics(trades)["exit_reason_table"]
    tp_row = table[table["ExitReason"] == "TP"].iloc[0]

    assert tp_row["Trades"] == 2
    assert tp_row["NetPnL"] == 150
    assert tp_row["AverageNetPnL"] == 75


def test_prepare_trade_pnl_chart_data_adds_cumulative_pnl():
    trades = pd.DataFrame(
        [
            {"TradeID": 10, "NetPnL": 100},
            {"TradeID": 11, "NetPnL": -25},
            {"TradeID": 12, "NetPnL": 50},
        ]
    )

    data = prepare_trade_pnl_chart_data(trades)

    assert data["TradeIndex"].tolist() == [10, 11, 12]
    assert data["CumulativeNetPnL"].tolist() == [100, 75, 125]


def test_filter_trades_for_chart_filters_by_date_and_direction():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "Direction": "Long",
            },
            {
                "TradeID": 2,
                "EntryTime": "2024-01-02 10:30:00",
                "ExitTime": "2024-01-02 10:40:00",
                "Direction": "Short",
            },
            {
                "TradeID": 3,
                "EntryTime": "2024-01-03 09:30:00",
                "ExitTime": "2024-01-03 09:40:00",
                "Direction": "Long",
            },
        ]
    )

    filtered = filter_trades_for_chart(
        trades,
        start_dt=pd.Timestamp("2024-01-02 09:00:00"),
        end_dt=pd.Timestamp("2024-01-02 11:00:00"),
        direction_filter="Long only",
        max_trades=100,
    )

    assert filtered["TradeID"].tolist() == [1]


def test_filter_trades_for_explorer_applies_filters():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "Direction": "Long",
                "NetPnL": 100,
                "ExitReason": "TP",
                "PhaseProfile": "EVALUATION",
            },
            {
                "TradeID": 2,
                "EntryTime": "2024-01-02 10:30:00",
                "ExitTime": "2024-01-02 10:40:00",
                "Direction": "Short",
                "NetPnL": -25,
                "ExitReason": "SL",
                "PhaseProfile": "FUNDED",
            },
        ]
    )

    filtered = filter_trades_for_explorer(
        trades,
        {
            "direction": "Long",
            "exit_reason": "TP",
            "phase_profile": "EVALUATION",
            "entry_date": "2024-01-02",
            "minimum_net_pnl": 0,
            "maximum_net_pnl": 200,
        },
    )

    assert filtered["TradeID"].tolist() == [1]


def test_compute_stochastic_for_chart_returns_k_and_d():
    ohlc = pd.DataFrame(
        {
            "DateTime": pd.date_range("2024-01-02 09:30:00", periods=6, freq="min"),
            "Open": [10, 20, 30, 40, 50, 60],
            "High": [100] * 6,
            "Low": [0] * 6,
            "Close": [10, 20, 30, 40, 50, 60],
        }
    )

    stochastic = compute_stochastic_for_chart(
        ohlc,
        {"period_k": 3, "period_d": 2, "smooth": 2},
    )

    assert {"DateTime", "K", "D"}.issubset(stochastic.columns)
    assert stochastic["K"].notna().any()
    assert stochastic["D"].notna().any()
