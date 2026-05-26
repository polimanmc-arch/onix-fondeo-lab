from __future__ import annotations

import pandas as pd
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import build_trade_diagnostics


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
