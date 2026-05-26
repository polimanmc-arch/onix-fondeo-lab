from pathlib import Path

import pandas as pd

from onix_fondeo.strategy_metrics import (
    calculate_strategy_metrics,
    export_strategy_metrics,
)


def test_empty_trades_return_safe_zero_metrics():
    metrics = calculate_strategy_metrics(pd.DataFrame())

    assert metrics["total_trades"] == 0
    assert metrics["win_rate"] == 0.0
    assert metrics["net_pnl"] == 0.0
    assert metrics["average_holding_minutes"] == 0.0


def test_simple_trades_calculate_win_rate_correctly():
    trades = pd.DataFrame({"NetPnL": [100, -50, 0, 25]})

    metrics = calculate_strategy_metrics(trades)

    assert metrics["total_trades"] == 4
    assert metrics["winning_trades"] == 2
    assert metrics["losing_trades"] == 1
    assert metrics["flat_trades"] == 1
    assert metrics["win_rate"] == 0.5


def test_profit_factor_handles_zero_gross_loss():
    trades = pd.DataFrame({"NetPnL": [100, 50]})

    metrics = calculate_strategy_metrics(trades)

    assert metrics["gross_profit"] == 150
    assert metrics["gross_loss"] == 0
    assert metrics["profit_factor"] == float("inf")


def test_consecutive_wins_and_losses_are_calculated():
    trades = pd.DataFrame({"NetPnL": [100, 50, -10, -20, -30, 25]})

    metrics = calculate_strategy_metrics(trades)

    assert metrics["max_consecutive_wins"] == 2
    assert metrics["max_consecutive_losses"] == 3


def test_average_holding_time_uses_entry_and_exit_time():
    trades = pd.DataFrame(
        {
            "EntryTime": [
                "2026-05-20 09:30:00",
                "2026-05-20 10:00:00",
            ],
            "ExitTime": [
                "2026-05-20 09:45:00",
                "2026-05-20 10:30:00",
            ],
            "NetPnL": [100, -50],
            "ExitReason": ["TP", "SL"],
        }
    )

    metrics = calculate_strategy_metrics(trades)

    assert metrics["average_holding_minutes"] == 22.5
    assert metrics["tp_exits"] == 1
    assert metrics["sl_exits"] == 1


def test_strategy_metrics_count_force_close_exits():
    trades = pd.DataFrame(
        {
            "EntryTime": ["2026-05-20 09:30:00"],
            "ExitTime": ["2026-05-20 15:55:00"],
            "NetPnL": [25],
            "ExitReason": ["FORCE_CLOSE"],
        }
    )

    metrics = calculate_strategy_metrics(trades)

    assert metrics["force_close_exits"] == 1


def test_strategy_metrics_sum_trade_cost_columns():
    trades = pd.DataFrame(
        {
            "NetPnL": [90, -30],
            "Commission": [4, 4],
            "SlippageCost": [10, 10],
            "SpreadCost": [5, 5],
            "TotalCost": [19, 19],
        }
    )

    metrics = calculate_strategy_metrics(trades)

    assert metrics["total_commission"] == 8
    assert metrics["total_slippage_cost"] == 20
    assert metrics["total_spread_cost"] == 10
    assert metrics["total_cost"] == 38


def test_strategy_metrics_include_phase_profile_breakdown():
    trades = pd.DataFrame(
        {
            "NetPnL": [100, 50, -25],
            "PhaseProfile": ["EVALUATION", "FUNDED", "FUNDED"],
        }
    )

    metrics = calculate_strategy_metrics(trades)

    assert metrics["evaluation_total_trades"] == 1
    assert metrics["evaluation_net_pnl"] == 100
    assert metrics["funded_total_trades"] == 2
    assert metrics["funded_net_pnl"] == 25


def test_export_strategy_metrics_writes_json(tmp_path: Path):
    metrics = calculate_strategy_metrics(pd.DataFrame({"NetPnL": [100]}))

    output_path = export_strategy_metrics(metrics, output_dir=str(tmp_path))

    assert output_path == tmp_path / "strategy_metrics.json"
    assert output_path.exists()
