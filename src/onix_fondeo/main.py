from onix_fondeo.loader import (
    list_presets,
    load_all_configs,
    load_trades,
    validate_preset_is_runnable,
)
from onix_fondeo.metrics import calculate_business_metrics
from onix_fondeo.report import export_results
from onix_fondeo.simulator import simulate_funding


def main():
    print("Starting Onix Fondeo Lab...")

    trades = load_trades()
    config = load_all_configs()
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


if __name__ == "__main__":
    main()
