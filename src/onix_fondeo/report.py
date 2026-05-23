from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from onix_fondeo.models import Account, Payout


ACCOUNT_COLUMNS = [
    "AccountID",
    "Phase",
    "Status",
    "FinalPnL",
    "HighWatermark",
    "TradingDays",
    "TradesCount",
    "StartedAt",
    "EndedAt",
    "ResultReason",
    "PayoutsCount",
    "TotalGrossPayout",
    "TotalNetPayout",
]

PAYOUT_COLUMNS = [
    "AccountID",
    "PayoutTime",
    "GrossPayout",
    "NetPayout",
]

TRADE_LOG_COLUMNS = [
    "AccountID",
    "Phase",
    "TradeID",
    "TradeTime",
    "OriginalPnL",
    "AppliedPnL",
    "AccountPnL",
    "StatusAfterTrade",
]

BUSINESS_EVENT_COLUMNS = [
    "time",
    "type",
    "amount",
    "account_id",
]


def accounts_to_dataframe(accounts: list[Account]) -> pd.DataFrame:
    rows = []

    for account in accounts:
        total_gross_payout = sum(payout.gross_payout for payout in account.payouts)
        total_net_payout = sum(payout.net_payout for payout in account.payouts)
        rows.append(
            {
                "AccountID": account.account_id,
                "Phase": account.phase,
                "Status": account.status,
                "FinalPnL": account.pnl,
                "HighWatermark": account.high_watermark,
                "TradingDays": len(account.trading_days),
                "TradesCount": account.trades_count,
                "StartedAt": account.started_at,
                "EndedAt": account.ended_at,
                "ResultReason": account.result_reason,
                "PayoutsCount": len(account.payouts),
                "TotalGrossPayout": total_gross_payout,
                "TotalNetPayout": total_net_payout,
            }
        )

    return pd.DataFrame(rows, columns=ACCOUNT_COLUMNS)


def payouts_to_dataframe(payouts: list[Payout]) -> pd.DataFrame:
    rows = [
        {
            "AccountID": payout.account_id,
            "PayoutTime": payout.payout_time,
            "GrossPayout": payout.gross_payout,
            "NetPayout": payout.net_payout,
        }
        for payout in payouts
    ]

    return pd.DataFrame(rows, columns=PAYOUT_COLUMNS)


def export_results(
    results: dict[str, Any],
    output_dir: str | Path = "data/output",
    metrics: dict[str, Any] | None = None,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_paths = {
        "account_summary": output_path / "account_summary.csv",
        "trade_log": output_path / "trade_log_simulated.csv",
        "payout_summary": output_path / "payout_summary.csv",
        "business_events": output_path / "business_events.csv",
    }

    accounts_to_dataframe(results["accounts"]).to_csv(
        file_paths["account_summary"],
        index=False,
    )
    pd.DataFrame(results["trade_log"], columns=TRADE_LOG_COLUMNS).to_csv(
        file_paths["trade_log"],
        index=False,
    )
    payouts_to_dataframe(results["payouts"]).to_csv(
        file_paths["payout_summary"],
        index=False,
    )
    pd.DataFrame(results["business_events"], columns=BUSINESS_EVENT_COLUMNS).to_csv(
        file_paths["business_events"],
        index=False,
    )

    if metrics is not None:
        file_paths["business_metrics"] = export_metrics(metrics, output_path)

    return file_paths


def export_metrics(
    metrics: dict[str, Any],
    output_dir: str | Path = "data/output",
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / "business_metrics.json"
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2, default=str)

    return file_path
