from __future__ import annotations

from itertools import product
from typing import Any

import pandas as pd

from onix_fondeo.backtester import backtest_strategy
from onix_fondeo.loader import (
    config_from_preset,
    validate_preset_is_runnable,
)
from onix_fondeo.metrics import calculate_business_metrics
from onix_fondeo.simulator import simulate_funding
from onix_fondeo.strategies.stochastic_level import StochasticLevelStrategy
from onix_fondeo.strategy_metrics import calculate_strategy_metrics


def build_stochastic_parameter_grid() -> list[dict[str, Any]]:
    grid_values = {
        "stoch_k_period": [7, 14],
        "stoch_d_period": [3],
        "oversold": [20, 30],
        "overbought": [70, 80],
        "signal_mode": ["cross", "zone"],
        "use_d_confirmation": [False, True],
        "min_k_d_gap": [0, 2],
        "cooldown_bars": [0, 5],
        "stop_loss_points": [20, 30],
        "take_profit_points": [30, 45],
    }

    keys = list(grid_values)
    return [
        dict(zip(keys, values))
        for values in product(*(grid_values[key] for key in keys))
    ]


def run_stochastic_optimization(
    ohlc: pd.DataFrame,
    presets: list[dict],
    base_args: dict[str, Any] | None = None,
    max_runs: int | None = None,
) -> list[dict[str, Any]]:
    base_args = base_args or {}
    runnable_presets = [
        preset for preset in presets if validate_preset_is_runnable(preset)[0]
    ]
    parameter_grid = build_stochastic_parameter_grid()
    if max_runs is not None:
        parameter_grid = parameter_grid[:max_runs]

    rows = []
    for run_index, params in enumerate(parameter_grid, start=1):
        strategy = StochasticLevelStrategy(
            k_period=params["stoch_k_period"],
            d_period=params["stoch_d_period"],
            oversold_level=params["oversold"],
            overbought_level=params["overbought"],
            signal_mode=params["signal_mode"],
            use_d_confirmation=params["use_d_confirmation"],
            min_k_d_gap=params["min_k_d_gap"],
            cooldown_bars=params["cooldown_bars"],
        )
        trades = backtest_strategy(
            ohlc=ohlc,
            strategy=strategy,
            symbol=base_args.get("symbol", "NQ"),
            quantity=base_args.get("quantity", 1),
            point_value=base_args.get("point_value", 20.0),
            stop_loss_points=params["stop_loss_points"],
            take_profit_points=params["take_profit_points"],
            max_holding_minutes=base_args.get("max_holding_minutes", 60),
            commission_per_side=base_args.get("commission_per_side", 0.0),
            same_bar_exit_policy=base_args.get(
                "same_bar_exit_policy",
                "conservative",
            ),
            force_close_time=base_args.get("force_close_time"),
        )
        strategy_metrics = calculate_strategy_metrics(trades)

        for preset in runnable_presets:
            config = config_from_preset(preset)
            results = simulate_funding(trades, config)
            funding_metrics = calculate_business_metrics(results, config)
            rows.append(
                _optimization_row(
                    run_id=run_index,
                    preset=preset,
                    params=params,
                    strategy_metrics=strategy_metrics,
                    funding_metrics=funding_metrics,
                )
            )

    return rows


def _optimization_row(
    run_id: int,
    preset: dict,
    params: dict[str, Any],
    strategy_metrics: dict[str, Any],
    funding_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "preset_id": preset["preset_id"],
        "company": preset["company"],
        "plan": preset.get("plan"),
        "account_name": preset.get("account_name"),
        "account_size": preset.get("account_size"),
        "strategy": "stochastic",
        "stoch_k_period": params["stoch_k_period"],
        "stoch_d_period": params["stoch_d_period"],
        "oversold": params["oversold"],
        "overbought": params["overbought"],
        "signal_mode": params["signal_mode"],
        "use_d_confirmation": params["use_d_confirmation"],
        "min_k_d_gap": params["min_k_d_gap"],
        "cooldown_bars": params["cooldown_bars"],
        "stop_loss_points": params["stop_loss_points"],
        "take_profit_points": params["take_profit_points"],
        "total_trades": strategy_metrics["total_trades"],
        "win_rate": strategy_metrics["win_rate"],
        "net_pnl": strategy_metrics["net_pnl"],
        "profit_factor": strategy_metrics["profit_factor"],
        "average_trade": strategy_metrics["average_trade"],
        "max_consecutive_wins": strategy_metrics["max_consecutive_wins"],
        "max_consecutive_losses": strategy_metrics["max_consecutive_losses"],
        "total_evaluations": funding_metrics["total_evaluations"],
        "passed_evaluations": funding_metrics["passed_evaluations"],
        "pass_rate": funding_metrics["pass_rate"],
        "funded_with_payout": funding_metrics["funded_with_payout"],
        "payout_rate_on_evaluations": funding_metrics[
            "payout_rate_on_evaluations"
        ],
        "total_evaluation_cost": funding_metrics["total_evaluation_cost"],
        "total_net_payout": funding_metrics["total_net_payout"],
        "net_business_pnl": funding_metrics["net_business_pnl"],
        "roi": funding_metrics["roi"],
        "expected_value_per_evaluation": funding_metrics[
            "expected_value_per_evaluation"
        ],
        "total_payouts": funding_metrics["total_payouts"],
    }
