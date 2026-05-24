from argparse import Namespace
from pathlib import Path

import pandas as pd

from onix_fondeo.main import build_strategy_from_args, load_or_generate_trades
from onix_fondeo.strategies.random_entry import RandomEntryStrategy
from onix_fondeo.strategies.stochastic_level import StochasticLevelStrategy


def test_build_strategy_from_args_defaults_to_random():
    strategy = build_strategy_from_args(_args(strategy=None))

    assert isinstance(strategy, RandomEntryStrategy)


def test_build_strategy_from_args_builds_stochastic_strategy():
    strategy = build_strategy_from_args(_args(strategy="stochastic"))

    assert isinstance(strategy, StochasticLevelStrategy)
    assert strategy.k_period == 14
    assert strategy.oversold_level == 20


def test_load_or_generate_trades_uses_market_data(tmp_path: Path):
    market_data_path = tmp_path / "ohlc.csv"
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
                "DateTime": "2026-05-20 09:31:00",
                "Open": 100,
                "High": 106,
                "Low": 99,
                "Close": 105,
            },
        ]
    ).to_csv(market_data_path, index=False)

    args = _args(
        market_data=str(market_data_path),
        strategy="random",
        random_probability=1.0,
    )

    trades, strategy_metrics = load_or_generate_trades(args)

    assert len(trades) == 1
    assert strategy_metrics["total_trades"] == 1
    assert {"TradeID", "EntryTime", "ExitTime", "NetPnL"}.issubset(trades.columns)
    assert Path("data/output/generated_trades.csv").exists()


def _args(**overrides) -> Namespace:
    values = {
        "market_data": None,
        "trades": "data/input/sample_trades.csv",
        "strategy": None,
        "symbol": "NQ",
        "quantity": 1,
        "point_value": 20.0,
        "stop_loss_points": 30.0,
        "take_profit_points": 45.0,
        "max_holding_minutes": 60,
        "commission_per_side": 0.0,
        "same_bar_exit_policy": "conservative",
        "random_probability": 0.005,
        "random_seed": 42,
        "stoch_k_period": 14,
        "stoch_d_period": 3,
        "stoch_oversold": 20,
        "stoch_overbought": 80,
        "strategy_start_time": None,
        "strategy_end_time": None,
    }
    values.update(overrides)
    return Namespace(**values)
