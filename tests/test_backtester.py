import pandas as pd

from onix_fondeo.backtester import TRADE_COLUMNS, backtest_strategy
from onix_fondeo.strategies.base import StrategySignal


class FixedSignalStrategy:
    name = "Fixed Signal"

    def __init__(self, direction: str = "Long") -> None:
        self.direction = direction

    def generate_signals(self, ohlc: pd.DataFrame) -> list[StrategySignal]:
        return [
            StrategySignal(
                signal_time=ohlc.iloc[0]["DateTime"],
                direction=self.direction,
                reason="Test signal",
            )
        ]


def test_backtester_returns_required_trade_columns():
    trades = backtest_strategy(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        stop_loss_points=5,
        take_profit_points=5,
    )

    assert list(trades.columns) == TRADE_COLUMNS
    assert {"TradeID", "EntryTime", "ExitTime", "NetPnL"}.issubset(trades.columns)


def test_backtester_handles_long_take_profit():
    trades = backtest_strategy(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=5,
        take_profit_points=5,
    )

    trade = trades.iloc[0]

    assert trade["ExitReason"] == "TP"
    assert trade["EntryPrice"] == 100
    assert trade["ExitPrice"] == 105
    assert trade["NetPnL"] == 100


def test_backtester_handles_long_stop_loss():
    trades = backtest_strategy(
        _ohlc_for_long_sl(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=5,
        take_profit_points=5,
    )

    trade = trades.iloc[0]

    assert trade["ExitReason"] == "SL"
    assert trade["ExitPrice"] == 95
    assert trade["NetPnL"] == -100


def test_backtester_conservative_same_bar_policy_assumes_stop_first():
    trades = backtest_strategy(
        _ohlc_for_same_bar_tp_and_sl(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=5,
        take_profit_points=5,
        same_bar_exit_policy="conservative",
    )

    trade = trades.iloc[0]

    assert trade["ExitReason"] == "SL"
    assert trade["ExitPrice"] == 95


def _base_ohlc(high_second_bar: float, low_second_bar: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "DateTime": pd.Timestamp("2026-05-20 09:30:00"),
                "Open": 100,
                "High": 101,
                "Low": 99,
                "Close": 100,
            },
            {
                "DateTime": pd.Timestamp("2026-05-20 09:31:00"),
                "Open": 100,
                "High": high_second_bar,
                "Low": low_second_bar,
                "Close": 100,
            },
        ]
    )


def _ohlc_for_long_tp() -> pd.DataFrame:
    return _base_ohlc(high_second_bar=106, low_second_bar=99)


def _ohlc_for_long_sl() -> pd.DataFrame:
    return _base_ohlc(high_second_bar=101, low_second_bar=94)


def _ohlc_for_same_bar_tp_and_sl() -> pd.DataFrame:
    return _base_ohlc(high_second_bar=106, low_second_bar=94)
