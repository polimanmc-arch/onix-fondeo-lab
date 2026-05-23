from __future__ import annotations

import json
from datetime import datetime
from html import escape
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
        file_paths["html_report"] = generate_html_report(results, metrics, output_path)

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


def generate_html_report(
    results: dict[str, Any],
    metrics: dict[str, Any],
    output_dir: str | Path = "data/output",
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / "report.html"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    accounts_df = accounts_to_dataframe(results["accounts"])
    payouts_df = payouts_to_dataframe(results["payouts"])
    business_events_df = pd.DataFrame(
        results["business_events"],
        columns=BUSINESS_EVENT_COLUMNS,
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Onix Fondeo Lab - Simulation Report</title>
  <style>
    body {{
      margin: 0;
      background: #ffffff;
      color: #172033;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 24px 48px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 30px;
      font-weight: 700;
    }}
    h2 {{
      margin: 32px 0 12px;
      font-size: 20px;
    }}
    .timestamp {{
      margin: 0 0 28px;
      color: #64748b;
      font-size: 14px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }}
    .card {{
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 14px 16px;
      background: #f8fafc;
    }}
    .card-label {{
      color: #64748b;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .card-value {{
      margin-top: 6px;
      font-size: 22px;
      font-weight: 700;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      border: 1px solid #e2e8f0;
      font-size: 14px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #e2e8f0;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f1f5f9;
      color: #334155;
      font-weight: 700;
    }}
    tr:nth-child(even) td {{
      background: #f8fafc;
    }}
    .positive {{
      color: #047857;
      font-weight: 700;
    }}
    .negative {{
      color: #b91c1c;
      font-weight: 700;
    }}
    .empty {{
      color: #64748b;
      padding: 14px 0;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Onix Fondeo Lab - Simulation Report</h1>
    <p class="timestamp">Generated: {escape(generated_at)}</p>

    <section>
      <h2>Business Metrics</h2>
      <div class="cards">
        {_metrics_cards_html(metrics)}
      </div>
    </section>

    <section>
      <h2>Accounts</h2>
      {_dataframe_table_html(
        accounts_df[
            [
                "AccountID",
                "Phase",
                "Status",
                "FinalPnL",
                "TradesCount",
                "ResultReason",
                "TotalNetPayout",
            ]
        ],
        numeric_columns={"FinalPnL", "TotalNetPayout"},
      )}
    </section>

    <section>
      <h2>Payouts</h2>
      {_dataframe_table_html(
        payouts_df[["AccountID", "PayoutTime", "GrossPayout", "NetPayout"]],
        numeric_columns={"GrossPayout", "NetPayout"},
      )}
    </section>

    <section>
      <h2>Business Events</h2>
      {_dataframe_table_html(
        business_events_df[["time", "type", "amount", "account_id"]],
        numeric_columns={"amount"},
      )}
    </section>
  </main>
</body>
</html>
"""

    file_path.write_text(html, encoding="utf-8")
    return file_path


def _metrics_cards_html(metrics: dict[str, Any]) -> str:
    metric_items = [
        ("Total Evaluations", metrics["total_evaluations"], "number"),
        ("Passed Evaluations", metrics["passed_evaluations"], "number"),
        ("Failed Evaluations", metrics["failed_evaluations"], "number"),
        ("Pass Rate", metrics["pass_rate"], "percent"),
        (
            "Payout Rate on Evaluations",
            metrics["payout_rate_on_evaluations"],
            "percent",
        ),
        ("Total Evaluation Cost", metrics["total_evaluation_cost"], "money"),
        ("Total Net Payout", metrics["total_net_payout"], "money"),
        ("Net Business PnL", metrics["net_business_pnl"], "money"),
        ("ROI", metrics["roi"], "percent"),
        (
            "Expected Value per Evaluation",
            metrics["expected_value_per_evaluation"],
            "money",
        ),
    ]

    cards = []
    for label, value, value_type in metric_items:
        cards.append(
            (
                '<div class="card">'
                f'<div class="card-label">{escape(label)}</div>'
                f'<div class="card-value {_number_class(value)}">'
                f"{_format_metric_value(value, value_type)}"
                "</div></div>"
            )
        )
    return "\n".join(cards)


def _dataframe_table_html(
    dataframe: pd.DataFrame,
    numeric_columns: set[str] | None = None,
) -> str:
    numeric_columns = numeric_columns or set()

    if dataframe.empty:
        return '<p class="empty">No records to display.</p>'

    header = "".join(f"<th>{escape(str(column))}</th>" for column in dataframe.columns)
    rows = []
    for _, row in dataframe.iterrows():
        cells = []
        for column in dataframe.columns:
            value = row[column]
            css_class = _number_class(value) if column in numeric_columns else ""
            class_attr = f' class="{css_class}"' if css_class else ""
            cells.append(f"<td{class_attr}>{escape(_format_cell_value(value))}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _format_metric_value(value: Any, value_type: str) -> str:
    if value_type == "percent":
        return escape(f"{float(value):.2%}")
    if value_type == "money":
        return escape(f"{float(value):,.2f}")
    return escape(str(value))


def _format_cell_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _number_class(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return ""
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return ""
