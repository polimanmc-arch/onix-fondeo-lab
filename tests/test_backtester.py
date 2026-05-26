import pandas as pd

from onix_fondeo.backtester import (
    TRADE_COLUMNS,
    backtest_strategy,
    backtest_strategy_for_phase_profiles,
)
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
    assert {
        "TradeID",
        "EntryTime",
        "ExitTime",
        "NetPnL",
        "SlippageCost",
        "SpreadCost",
        "TotalCost",
    }.issubset(trades.columns)


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


def test_backtester_force_close_time_closes_open_trade():
    trades = backtest_strategy(
        _ohlc_for_force_close(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=20,
        take_profit_points=20,
        max_holding_minutes=120,
        force_close_time="09:32",
    )

    trade = trades.iloc[0]

    assert trade["ExitReason"] == "FORCE_CLOSE"
    assert trade["ExitPrice"] == 102


def test_backtester_ignores_force_close_when_none():
    trades = backtest_strategy(
        _ohlc_for_force_close(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=20,
        take_profit_points=20,
        max_holding_minutes=1,
        force_close_time=None,
    )

    assert trades.iloc[0]["ExitReason"] == "TIME"


def test_backtester_stop_loss_takes_priority_on_force_close_bar():
    trades = backtest_strategy(
        _ohlc_for_force_close_sl_touch(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=5,
        take_profit_points=20,
        max_holding_minutes=120,
        force_close_time="09:32",
    )

    trade = trades.iloc[0]

    assert trade["ExitReason"] == "SL"
    assert trade["ExitPrice"] == 95


def test_backtester_net_pnl_includes_commission():
    trades = backtest_strategy(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=5,
        take_profit_points=5,
        commission_per_side=2,
    )

    trade = trades.iloc[0]

    assert trade["GrossPnL"] == 100
    assert trade["Commission"] == 4
    assert trade["NetPnL"] == 96


def test_backtester_net_pnl_includes_slippage_cost():
    trades = backtest_strategy(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=5,
        take_profit_points=5,
        slippage_points=0.25,
    )

    trade = trades.iloc[0]

    assert trade["SlippageCost"] == 10
    assert trade["NetPnL"] == 90


def test_backtester_net_pnl_includes_spread_cost():
    trades = backtest_strategy(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        point_value=20,
        stop_loss_points=5,
        take_profit_points=5,
        spread_points=0.25,
    )

    trade = trades.iloc[0]

    assert trade["SpreadCost"] == 5
    assert trade["NetPnL"] == 95


def test_backtester_contracts_override_quantity():
    trades = backtest_strategy(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        quantity=3,
        contracts=2,
        point_value=20,
        stop_loss_points=5,
        take_profit_points=5,
    )

    trade = trades.iloc[0]

    assert trade["Quantity"] == 2
    assert trade["GrossPnL"] == 200


def test_backtest_strategy_for_phase_profiles_tags_trades():
    trades = backtest_strategy_for_phase_profiles(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        point_value=20,
        evaluation_profile={
            "contracts": 2,
            "stop_loss_points": 5,
            "take_profit_points": 5,
        },
        funded_profile={
            "contracts": 1,
            "stop_loss_points": 5,
            "take_profit_points": 5,
        },
    )

    assert set(trades["PhaseProfile"]) == {"EVALUATION", "FUNDED"}
    assert set(trades["Quantity"]) == {1, 2}


def test_backtest_strategy_for_phase_profiles_reassigns_unique_trade_ids():
    trades = backtest_strategy_for_phase_profiles(
        _ohlc_for_long_tp(),
        FixedSignalStrategy("Long"),
        evaluation_profile={"stop_loss_points": 5, "take_profit_points": 5},
        funded_profile={"stop_loss_points": 5, "take_profit_points": 5},
    )

    assert list(trades["TradeID"]) == [1, 2]
    assert trades["TradeID"].is_unique


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


def _ohlc_for_force_close() -> pd.DataFrame:
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
                "High": 103,
                "Low": 99,
                "Close": 101,
            },
            {
                "DateTime": pd.Timestamp("2026-05-20 09:32:00"),
                "Open": 102,
                "High": 104,
                "Low": 101,
                "Close": 103,
            },
        ]
    )


def _ohlc_for_force_close_sl_touch() -> pd.DataFrame:
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
                "High": 103,
                "Low": 99,
                "Close": 101,
            },
            {
                "DateTime": pd.Timestamp("2026-05-20 09:32:00"),
                "Open": 102,
                "High": 104,
                "Low": 94,
                "Close": 96,
            },
        ]
    )
