from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def calculate_strategy_metrics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty or "NetPnL" not in trades.columns:
        return _empty_metrics()

    net_pnl = pd.to_numeric(trades["NetPnL"], errors="coerce").fillna(0.0)
    winning_trades = net_pnl[net_pnl > 0]
    losing_trades = net_pnl[net_pnl < 0]
    flat_trades = net_pnl[net_pnl == 0]
    gross_profit = float(winning_trades.sum())
    gross_loss = float(losing_trades.sum())
    total_commission = _sum_optional_column(trades, "Commission")
    total_slippage_cost = _sum_optional_column(trades, "SlippageCost")
    total_spread_cost = _sum_optional_column(trades, "SpreadCost")
    total_cost = (
        _sum_optional_column(trades, "TotalCost")
        if "TotalCost" in trades.columns
        else total_commission + total_slippage_cost + total_spread_cost
    )

    return {
        "total_trades": int(len(trades)),
        "winning_trades": int(len(winning_trades)),
        "losing_trades": int(len(losing_trades)),
        "flat_trades": int(len(flat_trades)),
        "win_rate": _safe_divide(len(winning_trades), len(trades)),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": float(net_pnl.sum()),
        "profit_factor": _profit_factor(gross_profit, gross_loss),
        "average_trade": float(net_pnl.mean()),
        "average_winner": _series_mean(winning_trades),
        "average_loser": _series_mean(losing_trades),
        "max_consecutive_wins": _max_consecutive(net_pnl, is_win=True),
        "max_consecutive_losses": _max_consecutive(net_pnl, is_win=False),
        "best_trade": float(net_pnl.max()),
        "worst_trade": float(net_pnl.min()),
        "tp_exits": _count_exit_reason(trades, "TP"),
        "sl_exits": _count_exit_reason(trades, "SL"),
        "time_exits": _count_exit_reason(trades, "TIME"),
        "end_of_data_exits": _count_exit_reason(trades, "END_OF_DATA"),
        "force_close_exits": _count_exit_reason(trades, "FORCE_CLOSE"),
        "average_holding_minutes": _average_holding_minutes(trades),
        "total_commission": total_commission,
        "total_slippage_cost": total_slippage_cost,
        "total_spread_cost": total_spread_cost,
        "total_cost": total_cost,
    }


def export_strategy_metrics(
    metrics: dict[str, Any],
    output_dir: str = "data/output",
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metrics_path = output_path / "strategy_metrics.json"

    with metrics_path.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2, default=str)

    return metrics_path


def _empty_metrics() -> dict[str, Any]:
    return {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "flat_trades": 0,
        "win_rate": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "profit_factor": 0.0,
        "average_trade": 0.0,
        "average_winner": 0.0,
        "average_loser": 0.0,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "best_trade": 0.0,
        "worst_trade": 0.0,
        "tp_exits": 0,
        "sl_exits": 0,
        "time_exits": 0,
        "end_of_data_exits": 0,
        "force_close_exits": 0,
        "average_holding_minutes": 0.0,
        "total_commission": 0.0,
        "total_slippage_cost": 0.0,
        "total_spread_cost": 0.0,
        "total_cost": 0.0,
    }


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_loss == 0:
        return 0.0 if gross_profit == 0 else float("inf")
    return gross_profit / abs(gross_loss)


def _series_mean(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(series.mean())


def _max_consecutive(net_pnl: pd.Series, is_win: bool) -> int:
    best_streak = 0
    current_streak = 0

    for value in net_pnl:
        matches = value > 0 if is_win else value < 0
        if matches:
            current_streak += 1
            best_streak = max(best_streak, current_streak)
        else:
            current_streak = 0

    return best_streak


def _count_exit_reason(trades: pd.DataFrame, exit_reason: str) -> int:
    if "ExitReason" not in trades.columns:
        return 0
    return int((trades["ExitReason"] == exit_reason).sum())


def _average_holding_minutes(trades: pd.DataFrame) -> float:
    if "EntryTime" not in trades.columns or "ExitTime" not in trades.columns:
        return 0.0

    entry_time = pd.to_datetime(trades["EntryTime"], errors="coerce")
    exit_time = pd.to_datetime(trades["ExitTime"], errors="coerce")
    holding_minutes = (exit_time - entry_time).dt.total_seconds() / 60
    holding_minutes = holding_minutes.dropna()

    if holding_minutes.empty:
        return 0.0
    return float(holding_minutes.mean())


def _sum_optional_column(trades: pd.DataFrame, column: str) -> float:
    if column not in trades.columns:
        return 0.0
    return float(pd.to_numeric(trades[column], errors="coerce").fillna(0.0).sum())
