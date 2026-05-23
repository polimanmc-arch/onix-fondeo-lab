from onix_fondeo.loader import load_all_configs, load_trades
from onix_fondeo.report import export_results
from onix_fondeo.simulator import simulate_funding


def main():
    print("Starting Onix Fondeo Lab...")

    trades = load_trades()
    config = load_all_configs()
    results = simulate_funding(trades, config)
    exported_files = export_results(results)

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

    print("\nExported files:")
    for name, path in exported_files.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
