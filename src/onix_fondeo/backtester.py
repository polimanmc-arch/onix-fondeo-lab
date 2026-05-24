from __future__ import annotations

from typing import Any

import pandas as pd


TRADE_COLUMNS = [
    "TradeID",
    "EntryTime",
    "ExitTime",
    "Symbol",
    "Direction",
    "Quantity",
    "EntryPrice",
    "ExitPrice",
    "GrossPnL",
    "Commission",
    "NetPnL",
    "ExitReason",
    "StrategyName",
]


def backtest_strategy(
    ohlc: pd.DataFrame,
    strategy: Any,
    symbol: str = "NQ",
    quantity: float = 1,
    point_value: float = 20.0,
    stop_loss_points: float = 30.0,
    take_profit_points: float = 45.0,
    max_holding_minutes: int = 60,
    commission_per_side: float = 0.0,
    same_bar_exit_policy: str = "conservative",
) -> pd.DataFrame:
    data = ohlc.sort_values("DateTime").reset_index(drop=True)
    signals = sorted(strategy.generate_signals(data), key=lambda signal: signal.signal_time)

    trades = []
    next_available_index = 0

    for signal in signals:
        signal_index = _find_signal_index(data, signal.signal_time)
        if signal_index is None or signal_index < next_available_index:
            continue

        entry_index = signal_index + 1
        if entry_index >= len(data):
            continue

        trade = _simulate_trade(
            data=data,
            signal=signal,
            entry_index=entry_index,
            trade_id=len(trades) + 1,
            symbol=symbol,
            quantity=quantity,
            point_value=point_value,
            stop_loss_points=stop_loss_points,
            take_profit_points=take_profit_points,
            max_holding_minutes=max_holding_minutes,
            commission_per_side=commission_per_side,
            same_bar_exit_policy=same_bar_exit_policy,
            strategy_name=getattr(strategy, "name", strategy.__class__.__name__),
        )
        trades.append(trade["row"])
        next_available_index = trade["exit_index"] + 1

    return pd.DataFrame(trades, columns=TRADE_COLUMNS)


def _find_signal_index(data: pd.DataFrame, signal_time: Any) -> int | None:
    matches = data.index[data["DateTime"] == signal_time].tolist()
    if not matches:
        return None
    return int(matches[0])


def _simulate_trade(
    data: pd.DataFrame,
    signal: Any,
    entry_index: int,
    trade_id: int,
    symbol: str,
    quantity: float,
    point_value: float,
    stop_loss_points: float,
    take_profit_points: float,
    max_holding_minutes: int,
    commission_per_side: float,
    same_bar_exit_policy: str,
    strategy_name: str,
) -> dict[str, Any]:
    entry_bar = data.iloc[entry_index]
    entry_time = entry_bar["DateTime"]
    entry_price = float(entry_bar["Open"])
    direction = signal.direction

    if direction == "Long":
        stop_price = entry_price - stop_loss_points
        target_price = entry_price + take_profit_points
    else:
        stop_price = entry_price + stop_loss_points
        target_price = entry_price - take_profit_points

    exit_index = entry_index
    exit_price = float(entry_bar["Close"])
    exit_reason = "END_OF_DATA"
    deadline = pd.Timestamp(entry_time) + pd.Timedelta(minutes=max_holding_minutes)

    for index in range(entry_index, len(data)):
        bar = data.iloc[index]
        exit_index = index
        exit_time = bar["DateTime"]
        stop_hit, target_hit = _check_exit_touches(
            direction=direction,
            high=float(bar["High"]),
            low=float(bar["Low"]),
            stop_price=stop_price,
            target_price=target_price,
        )

        if stop_hit and target_hit and same_bar_exit_policy == "conservative":
            exit_price = stop_price
            exit_reason = "SL"
            break
        if stop_hit:
            exit_price = stop_price
            exit_reason = "SL"
            break
        if target_hit:
            exit_price = target_price
            exit_reason = "TP"
            break
        if pd.Timestamp(exit_time) >= deadline:
            exit_price = float(bar["Close"])
            exit_reason = "TIME"
            break

        exit_price = float(bar["Close"])

    exit_time = data.iloc[exit_index]["DateTime"]
    gross_pnl = _calculate_gross_pnl(
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        point_value=point_value,
        quantity=quantity,
    )
    commission = commission_per_side * 2 * quantity
    net_pnl = gross_pnl - commission

    return {
        "exit_index": exit_index,
        "row": {
            "TradeID": trade_id,
            "EntryTime": entry_time,
            "ExitTime": exit_time,
            "Symbol": symbol,
            "Direction": direction,
            "Quantity": quantity,
            "EntryPrice": entry_price,
            "ExitPrice": exit_price,
            "GrossPnL": gross_pnl,
            "Commission": commission,
            "NetPnL": net_pnl,
            "ExitReason": exit_reason,
            "StrategyName": strategy_name,
        },
    }


def _check_exit_touches(
    direction: str,
    high: float,
    low: float,
    stop_price: float,
    target_price: float,
) -> tuple[bool, bool]:
    if direction == "Long":
        return low <= stop_price, high >= target_price
    return high >= stop_price, low <= target_price


def _calculate_gross_pnl(
    direction: str,
    entry_price: float,
    exit_price: float,
    point_value: float,
    quantity: float,
) -> float:
    if direction == "Long":
        return (exit_price - entry_price) * point_value * quantity
    return (entry_price - exit_price) * point_value * quantity
