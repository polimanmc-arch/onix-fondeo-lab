import argparse
from pathlib import Path

from onix_fondeo.backtester import (
    backtest_strategy,
    backtest_strategy_for_phase_profiles,
)
from onix_fondeo.bankroll import calculate_bankroll_curve
from onix_fondeo.loader import (
    config_from_preset,
    list_presets,
    load_all_configs,
    load_preset,
    load_trades,
    validate_preset_is_runnable,
)
from onix_fondeo.market_data import load_ohlc_data
from onix_fondeo.metrics import calculate_business_metrics
from onix_fondeo.optimizer import filter_ohlc_by_date, run_stochastic_optimization
from onix_fondeo.report import (
    export_comparison_results,
    export_optimization_results,
    export_results,
)
from onix_fondeo.risk_of_ruin import (
    estimate_required_bankroll,
    export_risk_of_ruin_results,
    extract_account_net_outcomes,
    run_monte_carlo_ruin_simulation,
)
from onix_fondeo.simulator import simulate_funding
from onix_fondeo.strategy_metrics import (
    calculate_strategy_metrics,
    export_strategy_metrics,
)
from onix_fondeo.strategies.random_entry import RandomEntryStrategy
from onix_fondeo.strategies.stochastic_level import StochasticLevelStrategy


def main():
    print("Starting Onix Fondeo Lab...")
    args = parse_args()

    if args.list_presets:
        print_presets()
        return

    if args.optimize_strategy == "stochastic":
        run_stochastic_optimization_mode(args)
        return

    trades, strategy_metrics = load_or_generate_trades(args)

    if args.compare:
        run_comparison(args.compare, trades, bankroll=args.bankroll)
        return

    config = load_config(args.preset)

    if config is None:
        return

    results = simulate_funding(trades, config)
    metrics = calculate_business_metrics(results, config)
    bankroll_result = _calculate_bankroll_result(args.bankroll, results, config)
    risk_result, required_bankroll_result, risk_files = _run_risk_of_ruin_if_requested(
        args,
        results,
        config,
    )
    presets = []
    for preset in list_presets():
        is_runnable, missing_fields = validate_preset_is_runnable(preset)
        preset_info = dict(preset)
        preset_info["is_runnable"] = is_runnable
        preset_info["missing_fields"] = missing_fields
        presets.append(preset_info)

    exported_files = export_results(
        results,
        metrics=metrics,
        presets=presets,
        strategy_metrics=strategy_metrics,
        bankroll_result=bankroll_result,
        risk_of_ruin_result=risk_result,
        required_bankroll_result=required_bankroll_result,
    )
    exported_files.update(risk_files)

    print("\nSimulation summary:")
    print(f"Total accounts: {len(results['accounts'])}")
    print(f"Total trade log rows: {len(results['trade_log'])}")
    print(f"Total payouts: {len(results['payouts'])}")
    print(f"Total business events: {len(results['business_events'])}")

    print("\nAccount summary:")
    for account in results["accounts"]:
        print(
            f"Account {account.account_id} | "
            f"{account.phase} | "
            f"{account.status} | "
            f"PnL: {account.pnl:.2f} | "
            f"Trades: {account.trades_count} | "
            f"Reason: {account.result_reason}"
        )

    print("\nPayout summary:")
    for payout in results["payouts"]:
        print(
            f"Account {payout.account_id} | "
            f"Gross: {payout.gross_payout:.2f} | "
            f"Net: {payout.net_payout:.2f}"
        )

    print("\nBusiness metrics:")
    print(f"Total evaluations: {metrics['total_evaluations']}")
    print(f"Passed evaluations: {metrics['passed_evaluations']}")
    print(f"Failed evaluations: {metrics['failed_evaluations']}")
    print(f"Pass rate: {metrics['pass_rate']:.2%}")
    print(
        "Payout rate on evaluations: "
        f"{metrics['payout_rate_on_evaluations']:.2%}"
    )
    print(f"Total evaluation cost: {metrics['total_evaluation_cost']:.2f}")
    print(f"Total net payout: {metrics['total_net_payout']:.2f}")
    print(f"Net business PnL: {metrics['net_business_pnl']:.2f}")
    print(f"ROI: {metrics['roi']:.2%}")
    print(
        "Expected value per evaluation: "
        f"{metrics['expected_value_per_evaluation']:.2f}"
    )

    print("\nExported files:")
    for name, path in exported_files.items():
        print(f"{name}: {path}")

    if "html_report" in exported_files:
        print(f"\nHTML report: {exported_files['html_report']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Onix Fondeo Lab simulations.")
    parser.add_argument(
        "--preset",
        help="Preset ID to use for the simulation.",
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        metavar="PRESET_ID",
        help="Compare multiple runnable presets using the same trades CSV.",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets and exit.",
    )
    parser.add_argument(
        "--trades",
        default="data/input/sample_trades.csv",
        help="Trades CSV path.",
    )
    parser.add_argument(
        "--market-data",
        help="OHLC CSV path. If provided, trades are generated from market data.",
    )
    parser.add_argument(
        "--strategy",
        choices=["random", "stochastic"],
        help="Strategy to use with --market-data. Defaults to random.",
    )
    parser.add_argument(
        "--optimize-strategy",
        choices=["stochastic"],
        help="Run strategy optimization mode.",
    )
    parser.add_argument(
        "--max-optimization-runs",
        type=int,
        help="Limit the number of strategy parameter sets in optimization mode.",
    )
    parser.add_argument(
        "--optimization-grid",
        choices=["fast", "default", "full"],
        default="fast",
        help="Optimization grid size. Defaults to fast.",
    )
    parser.add_argument(
        "--optimization-start-date",
        help="Optional optimization start date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--optimization-end-date",
        help="Optional optimization end date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--optimization-workers",
        type=int,
        default=1,
        help="Number of parallel optimization workers. Defaults to 1.",
    )
    parser.add_argument(
        "--optimization-min-trades",
        type=int,
        default=0,
        help="Minimum trades required for optimization report rankings.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        help="Initial business bankroll for path-based bankroll tracking.",
    )
    parser.add_argument(
        "--monte-carlo-runs",
        type=int,
        default=0,
        help="Monte Carlo risk-of-ruin runs. Requires --bankroll.",
    )
    parser.add_argument(
        "--monte-carlo-max-accounts",
        type=int,
        default=100,
        help="Maximum sampled accounts per Monte Carlo path.",
    )
    parser.add_argument(
        "--monte-carlo-seed",
        type=int,
        default=42,
        help="Monte Carlo random seed.",
    )
    parser.add_argument(
        "--target-ruin-probability",
        type=float,
        default=0.05,
        help="Target ruin probability for required bankroll estimate.",
    )
    parser.add_argument("--symbol", default="NQ", help="Trading symbol.")
    parser.add_argument("--quantity", type=float, default=1, help="Trade quantity.")
    parser.add_argument(
        "--contracts",
        type=float,
        help="Number of contracts. Overrides --quantity when provided.",
    )
    parser.add_argument(
        "--point-value",
        type=float,
        default=20.0,
        help="Dollar value per point.",
    )
    parser.add_argument(
        "--stop-loss-points",
        type=float,
        default=30.0,
        help="Stop loss in points.",
    )
    parser.add_argument(
        "--take-profit-points",
        type=float,
        default=45.0,
        help="Take profit in points.",
    )
    parser.add_argument(
        "--max-holding-minutes",
        type=int,
        default=60,
        help="Maximum trade holding time in minutes.",
    )
    parser.add_argument(
        "--commission-per-side",
        type=float,
        default=0.0,
        help="Commission per side per contract.",
    )
    parser.add_argument(
        "--slippage-points",
        type=float,
        default=0.0,
        help="Slippage in points per side.",
    )
    parser.add_argument(
        "--spread-points",
        type=float,
        default=0.0,
        help="Spread cost approximation in points.",
    )
    parser.add_argument(
        "--same-bar-exit-policy",
        default="conservative",
        help="Policy when SL and TP are touched in the same bar.",
    )
    parser.add_argument(
        "--force-close-time",
        help='Optional time-of-day force close, for example "15:55".',
    )
    parser.add_argument(
        "--use-phase-profiles",
        action="store_true",
        help="Generate separate EVALUATION and FUNDED trade streams.",
    )
    parser.add_argument("--evaluation-contracts", type=float)
    parser.add_argument("--evaluation-stop-loss-points", type=float)
    parser.add_argument("--evaluation-take-profit-points", type=float)
    parser.add_argument("--evaluation-max-holding-minutes", type=int)
    parser.add_argument("--evaluation-commission-per-side", type=float)
    parser.add_argument("--evaluation-slippage-points", type=float)
    parser.add_argument("--evaluation-spread-points", type=float)
    parser.add_argument("--evaluation-force-close-time")
    parser.add_argument("--funded-contracts", type=float)
    parser.add_argument("--funded-stop-loss-points", type=float)
    parser.add_argument("--funded-take-profit-points", type=float)
    parser.add_argument("--funded-max-holding-minutes", type=int)
    parser.add_argument("--funded-commission-per-side", type=float)
    parser.add_argument("--funded-slippage-points", type=float)
    parser.add_argument("--funded-spread-points", type=float)
    parser.add_argument("--funded-force-close-time")
    parser.add_argument(
        "--random-probability",
        type=float,
        default=0.005,
        help="Random strategy signal probability per bar.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random strategy seed.",
    )
    parser.add_argument(
        "--stoch-k-period",
        type=int,
        default=14,
        help="Stochastic %%K period.",
    )
    parser.add_argument(
        "--stoch-d-period",
        type=int,
        default=3,
        help="Stochastic %%D period.",
    )
    parser.add_argument(
        "--stoch-oversold",
        type=float,
        default=20,
        help="Stochastic oversold level.",
    )
    parser.add_argument(
        "--stoch-overbought",
        type=float,
        default=80,
        help="Stochastic overbought level.",
    )
    parser.add_argument(
        "--stoch-signal-mode",
        choices=["cross", "zone"],
        default="cross",
        help="Stochastic signal mode.",
    )
    parser.add_argument(
        "--stoch-use-d-confirmation",
        action="store_true",
        help="Require stochastic %%K/%%D confirmation.",
    )
    parser.add_argument(
        "--stoch-min-k-d-gap",
        type=float,
        default=0.0,
        help="Minimum %%K/%%D gap when D confirmation is enabled.",
    )
    parser.add_argument(
        "--stoch-cooldown-bars",
        type=int,
        default=0,
        help="Bars to skip after each stochastic signal.",
    )
    parser.add_argument(
        "--strategy-start-time",
        help='Optional strategy start time, for example "09:30".',
    )
    parser.add_argument(
        "--strategy-end-time",
        help='Optional strategy end time, for example "15:30".',
    )
    return parser.parse_args()


def run_stochastic_optimization_mode(args: argparse.Namespace) -> None:
    if not args.market_data:
        print("\n--market-data is required for strategy optimization.")
        return
    if not args.preset and not args.compare:
        print("\nStrategy optimization requires --preset or --compare.")
        return

    presets = _load_runnable_presets_for_request(args)
    if not presets:
        print("\nNo runnable presets available for optimization.")
        return

    ohlc = load_ohlc_data(args.market_data, symbol=args.symbol)
    ohlc = filter_ohlc_by_date(
        ohlc,
        start_date=args.optimization_start_date,
        end_date=args.optimization_end_date,
    )
    if args.optimization_start_date or args.optimization_end_date:
        print(
            "\nOptimization date filter: "
            f"{args.optimization_start_date or 'start'} to "
            f"{args.optimization_end_date or 'end'}"
        )
        print(f"Optimization OHLC rows: {len(ohlc)}")

    rows = run_stochastic_optimization(
        ohlc=ohlc,
        presets=presets,
        base_args={
            "symbol": args.symbol,
            "quantity": args.quantity,
            "contracts": args.contracts,
            "point_value": args.point_value,
            "commission_per_side": args.commission_per_side,
            "slippage_points": args.slippage_points,
            "spread_points": args.spread_points,
            "max_holding_minutes": args.max_holding_minutes,
            "same_bar_exit_policy": args.same_bar_exit_policy,
            "force_close_time": args.force_close_time,
            "initial_bankroll": args.bankroll,
        },
        max_runs=args.max_optimization_runs,
        grid_name=args.optimization_grid,
        workers=args.optimization_workers,
    )
    exported_files = export_optimization_results(
        rows,
        min_trades=args.optimization_min_trades,
    )
    top_rows = sorted(
        rows,
        key=lambda row: row.get("net_business_pnl", 0) or 0,
        reverse=True,
    )

    print("\nOptimization completed.")
    print(f"Rows: {len(rows)}")
    if top_rows:
        best = top_rows[0]
        print("\nBest by Net Business PnL:")
        print(
            f"{best['preset_id']} | run {best['run_id']} | "
            f"{best['net_business_pnl']:.2f} | ROI {best['roi']:.2%}"
        )

    print("\nExported files:")
    print(f"- {exported_files['optimization_results']}")
    print(f"- {exported_files['optimization_report']}")


def _load_runnable_presets_for_request(args: argparse.Namespace) -> list[dict]:
    preset_ids = args.compare if args.compare else [args.preset]
    presets = []

    for preset_id in preset_ids:
        try:
            preset = load_preset(preset_id)
        except ValueError as error:
            print(f"\nSkipping preset: {preset_id}")
            print(error)
            continue

        is_runnable, missing_fields = validate_preset_is_runnable(preset)
        if not is_runnable:
            print(f"\nSkipping preset: {preset_id}")
            print("Preset is not runnable")
            print("Missing fields:")
            for field_name in missing_fields:
                print(f"- {field_name}")
            continue

        presets.append(preset)

    return presets


def build_strategy_from_args(args: argparse.Namespace):
    strategy_name = args.strategy or "random"

    if strategy_name == "random":
        return RandomEntryStrategy(
            probability=args.random_probability,
            seed=args.random_seed,
            start_time=args.strategy_start_time,
            end_time=args.strategy_end_time,
        )

    if strategy_name == "stochastic":
        return StochasticLevelStrategy(
            k_period=args.stoch_k_period,
            d_period=args.stoch_d_period,
            oversold_level=args.stoch_oversold,
            overbought_level=args.stoch_overbought,
            start_time=args.strategy_start_time,
            end_time=args.strategy_end_time,
            signal_mode=args.stoch_signal_mode,
            use_d_confirmation=args.stoch_use_d_confirmation,
            min_k_d_gap=args.stoch_min_k_d_gap,
            cooldown_bars=args.stoch_cooldown_bars,
        )

    raise ValueError(f"Unsupported strategy: {strategy_name}")


def load_or_generate_trades(args: argparse.Namespace):
    if not args.market_data:
        return load_trades(args.trades), None

    ohlc = load_ohlc_data(args.market_data, symbol=args.symbol)
    strategy = build_strategy_from_args(args)
    if args.use_phase_profiles:
        trades = backtest_strategy_for_phase_profiles(
            ohlc=ohlc,
            strategy=strategy,
            symbol=args.symbol,
            point_value=args.point_value,
            evaluation_profile=_phase_profile_from_args(args, "evaluation"),
            funded_profile=_phase_profile_from_args(args, "funded"),
            same_bar_exit_policy=args.same_bar_exit_policy,
        )
    else:
        trades = backtest_strategy(
            ohlc=ohlc,
            strategy=strategy,
            symbol=args.symbol,
            quantity=args.quantity,
            contracts=args.contracts,
            point_value=args.point_value,
            stop_loss_points=args.stop_loss_points,
            take_profit_points=args.take_profit_points,
            max_holding_minutes=args.max_holding_minutes,
            commission_per_side=args.commission_per_side,
            slippage_points=args.slippage_points,
            spread_points=args.spread_points,
            same_bar_exit_policy=args.same_bar_exit_policy,
            force_close_time=args.force_close_time,
        )

    output_dir = Path("data/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_trades_path = output_dir / "generated_trades.csv"
    trades.to_csv(generated_trades_path, index=False)

    print("\nGenerated trades from OHLC data")
    print(f"Strategy: {getattr(strategy, 'name', strategy.__class__.__name__)}")
    print(f"Generated trades: {len(trades)}")
    print(f"Generated trades CSV: {generated_trades_path}")
    if trades.empty:
        print("No trades were generated by the selected strategy.")

    strategy_metrics = calculate_strategy_metrics(trades)
    strategy_metrics_path = export_strategy_metrics(strategy_metrics)
    print("\nStrategy trades:")
    print(f"Total trades: {strategy_metrics['total_trades']}")
    print(f"Win rate: {strategy_metrics['win_rate']:.2%}")
    print(f"Net PnL: {strategy_metrics['net_pnl']:.2f}")
    print(f"Profit factor: {_format_metric(strategy_metrics['profit_factor'])}")
    print(f"Strategy metrics JSON: {strategy_metrics_path}")

    return trades, strategy_metrics


def _phase_profile_from_args(args: argparse.Namespace, phase: str) -> dict:
    return {
        "quantity": args.quantity,
        "contracts": _phase_value(args, phase, "contracts", args.contracts),
        "stop_loss_points": _phase_value(
            args,
            phase,
            "stop_loss_points",
            args.stop_loss_points,
        ),
        "take_profit_points": _phase_value(
            args,
            phase,
            "take_profit_points",
            args.take_profit_points,
        ),
        "max_holding_minutes": _phase_value(
            args,
            phase,
            "max_holding_minutes",
            args.max_holding_minutes,
        ),
        "commission_per_side": _phase_value(
            args,
            phase,
            "commission_per_side",
            args.commission_per_side,
        ),
        "slippage_points": _phase_value(
            args,
            phase,
            "slippage_points",
            args.slippage_points,
        ),
        "spread_points": _phase_value(
            args,
            phase,
            "spread_points",
            args.spread_points,
        ),
        "force_close_time": _phase_value(
            args,
            phase,
            "force_close_time",
            args.force_close_time,
        ),
    }


def _phase_value(
    args: argparse.Namespace,
    phase: str,
    field_name: str,
    fallback: object,
) -> object:
    value = getattr(args, f"{phase}_{field_name}")
    return fallback if value is None else value


def _format_metric(value: float) -> str:
    if value == float("inf"):
        return "inf"
    return f"{value:.2f}"


def run_comparison(preset_ids: list[str], trades: object, bankroll: float | None = None) -> None:
    comparison_rows = []
    skipped_presets = []

    for preset_id in preset_ids:
        try:
            preset = load_preset(preset_id)
        except ValueError as error:
            print(f"\nSkipping preset: {preset_id}")
            print(error)
            skipped_presets.append(preset_id)
            continue

        is_runnable, missing_fields = validate_preset_is_runnable(preset)
        if not is_runnable:
            print(f"\nSkipping preset: {preset_id}")
            print("Preset is not runnable")
            print("Missing fields:")
            for field_name in missing_fields:
                print(f"- {field_name}")
            skipped_presets.append(preset_id)
            continue

        config = config_from_preset(preset)
        results = simulate_funding(trades, config)
        metrics = calculate_business_metrics(results, config)
        bankroll_result = _calculate_bankroll_result(bankroll, results, config)
        comparison_rows.append(_comparison_row(preset, metrics, bankroll_result))

    if not comparison_rows:
        print("\nNo runnable presets available for comparison.")
        return

    exported_files = export_comparison_results(comparison_rows)
    top_rows = sorted(
        comparison_rows,
        key=lambda row: row["net_business_pnl"],
        reverse=True,
    )

    print("\nComparison completed.")
    print(f"Runnable presets compared: {len(comparison_rows)}")
    print(f"Skipped presets: {len(skipped_presets)}")

    print("\nTop by Net Business PnL:")
    for index, row in enumerate(top_rows[:3], start=1):
        print(
            f"{index}. {row['preset_id']} | "
            f"{row['net_business_pnl']:.2f} | "
            f"{row['roi']:.2%}"
        )

    print("\nExported:")
    print(f"- {exported_files['comparison_summary']}")
    print(f"- {exported_files['comparison_report']}")


def _comparison_row(
    preset: dict,
    metrics: dict,
    bankroll_result: dict | None = None,
) -> dict:
    metadata = preset.get("metadata", {})
    row = {
        "preset_id": preset["preset_id"],
        "company": preset["company"],
        "plan": preset.get("plan"),
        "account_name": preset.get("account_name"),
        "account_size": preset.get("account_size"),
        "straight_to_funded": bool(metadata.get("straight_to_funded", False)),
        **metrics,
    }
    if bankroll_result is not None:
        row.update(_bankroll_comparison_fields(bankroll_result))
    return row


def _calculate_bankroll_result(
    initial_bankroll: float | None,
    results: dict,
    config: dict,
) -> dict | None:
    if initial_bankroll is None:
        return None
    return calculate_bankroll_curve(
        results["business_events"],
        initial_bankroll=initial_bankroll,
        account_cost=_account_cost_from_config(config),
    )


def _account_cost_from_config(config: dict) -> float | None:
    evaluation = config.get("evaluation", {})
    funded = config.get("funded", {})
    if evaluation.get("enabled", True):
        return evaluation.get("evaluation_cost")
    return funded.get("account_cost") or evaluation.get("evaluation_cost")


def _bankroll_comparison_fields(bankroll_result: dict) -> dict:
    bankroll_metrics = bankroll_result["metrics"]
    return {
        "initial_bankroll": bankroll_metrics["initial_bankroll"],
        "final_bankroll": bankroll_metrics["final_bankroll"],
        "lowest_bankroll": bankroll_metrics["lowest_bankroll"],
        "bankroll_ruined": bankroll_metrics["bankroll_ruined"],
        "max_bankroll_drawdown": bankroll_metrics["max_bankroll_drawdown"],
        "bankroll_return": bankroll_metrics["bankroll_return"],
        "accounts_affordable_remaining": bankroll_metrics[
            "accounts_affordable_remaining"
        ],
    }


def _run_risk_of_ruin_if_requested(
    args: argparse.Namespace,
    results: dict,
    config: dict,
) -> tuple[dict | None, dict | None, dict]:
    if args.monte_carlo_runs <= 0 or args.bankroll is None:
        return None, None, {}

    account_outcomes = extract_account_net_outcomes(results)
    account_cost = _account_cost_from_config(config)
    risk_result = run_monte_carlo_ruin_simulation(
        account_outcomes=account_outcomes,
        initial_bankroll=args.bankroll,
        account_cost=account_cost,
        runs=args.monte_carlo_runs,
        max_accounts=args.monte_carlo_max_accounts,
        seed=args.monte_carlo_seed,
    )
    required_bankroll_result = estimate_required_bankroll(
        account_outcomes=account_outcomes,
        target_ruin_probability=args.target_ruin_probability,
        account_cost=account_cost,
        runs=max(1, min(args.monte_carlo_runs, 5000)),
        max_accounts=args.monte_carlo_max_accounts,
        seed=args.monte_carlo_seed,
    )
    exported_files = export_risk_of_ruin_results(
        risk_result,
        required_bankroll_result=required_bankroll_result,
    )

    print("\nRisk of ruin:")
    print(f"Monte Carlo runs: {risk_result['metrics']['runs']}")
    print(f"Ruin probability: {risk_result['metrics']['ruin_probability']:.2%}")
    print(
        "Recommended bankroll: "
        f"{required_bankroll_result.get('recommended_bankroll')}"
    )

    return risk_result, required_bankroll_result, exported_files


def load_config(preset_id: str | None) -> dict | None:
    if preset_id is None:
        print("\nUsing default config files.")
        return load_all_configs()

    preset = load_preset(preset_id)
    is_runnable, missing_fields = validate_preset_is_runnable(preset)
    if not is_runnable:
        print("\nPreset is not runnable")
        print("Missing fields:")
        for field_name in missing_fields:
            print(f"- {field_name}")
        return None

    print(f"\nSelected preset: {preset['company']} - {preset['account_name']}")
    print(f"Plan: {preset.get('plan')}")
    print(f"Account size: {preset.get('account_size')}")
    print(f"Source verified: {preset.get('is_official')}")
    print(f"Rules verified: {preset.get('rules_verified')}")
    return config_from_preset(preset)


def print_presets() -> None:
    presets = []
    for preset in list_presets():
        is_runnable, _ = validate_preset_is_runnable(preset)
        presets.append((preset, is_runnable))

    if not presets:
        print("\nNo presets found.")
        return

    print("\nAvailable presets:")
    print(
        f"{'preset_id':<38} {'company':<20} {'plan':<24} "
        f"{'account_name':<28} {'size':>8} {'verified':<9} {'runnable':<8}"
    )
    print("-" * 143)
    for preset, is_runnable in presets:
        print(
            f"{preset.get('preset_id', ''):<38} "
            f"{preset.get('company', ''):<20} "
            f"{preset.get('plan', ''):<24} "
            f"{preset.get('account_name', ''):<28} "
            f"{preset.get('account_size', ''):>8} "
            f"{str(preset.get('rules_verified', False)):<9} "
            f"{'Yes' if is_runnable else 'No':<8}"
        )


if __name__ == "__main__":
    main()
