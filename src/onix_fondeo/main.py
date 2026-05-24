import argparse
from pathlib import Path

from onix_fondeo.backtester import backtest_strategy
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
from onix_fondeo.report import export_comparison_results, export_results
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

    trades, strategy_metrics = load_or_generate_trades(args)

    if args.compare:
        run_comparison(args.compare, trades)
        return

    config = load_config(args.preset)

    if config is None:
        return

    results = simulate_funding(trades, config)
    metrics = calculate_business_metrics(results, config)
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
    )

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
    parser.add_argument("--symbol", default="NQ", help="Trading symbol.")
    parser.add_argument("--quantity", type=float, default=1, help="Trade quantity.")
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
        "--same-bar-exit-policy",
        default="conservative",
        help="Policy when SL and TP are touched in the same bar.",
    )
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
    trades = backtest_strategy(
        ohlc=ohlc,
        strategy=strategy,
        symbol=args.symbol,
        quantity=args.quantity,
        point_value=args.point_value,
        stop_loss_points=args.stop_loss_points,
        take_profit_points=args.take_profit_points,
        max_holding_minutes=args.max_holding_minutes,
        commission_per_side=args.commission_per_side,
        same_bar_exit_policy=args.same_bar_exit_policy,
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


def _format_metric(value: float) -> str:
    if value == float("inf"):
        return "inf"
    return f"{value:.2f}"


def run_comparison(preset_ids: list[str], trades: object) -> None:
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
        comparison_rows.append(_comparison_row(preset, metrics))

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
) -> dict:
    metadata = preset.get("metadata", {})
    return {
        "preset_id": preset["preset_id"],
        "company": preset["company"],
        "plan": preset.get("plan"),
        "account_name": preset.get("account_name"),
        "account_size": preset.get("account_size"),
        "straight_to_funded": bool(metadata.get("straight_to_funded", False)),
        **metrics,
    }


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
