import argparse

from onix_fondeo.loader import (
    config_from_preset,
    list_presets,
    load_all_configs,
    load_preset,
    load_trades,
    validate_preset_is_runnable,
)
from onix_fondeo.metrics import calculate_business_metrics
from onix_fondeo.report import export_results
from onix_fondeo.simulator import simulate_funding


def main():
    print("Starting Onix Fondeo Lab...")
    args = parse_args()

    if args.list_presets:
        print_presets()
        return

    trades = load_trades(args.trades)
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

    exported_files = export_results(results, metrics=metrics, presets=presets)

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
        "--list-presets",
        action="store_true",
        help="List available presets and exit.",
    )
    parser.add_argument(
        "--trades",
        default="data/input/sample_trades.csv",
        help="Trades CSV path.",
    )
    return parser.parse_args()


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
