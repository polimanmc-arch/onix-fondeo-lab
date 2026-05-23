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
    .chart-card {{
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 16px;
      background: #ffffff;
    }}
    .chart-note {{
      margin: 8px 0 0;
      color: #64748b;
      font-size: 13px;
    }}
    .bar-list {{
      display: grid;
      gap: 12px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(150px, 220px) 1fr minmax(80px, auto);
      gap: 12px;
      align-items: center;
    }}
    .bar-label {{
      color: #334155;
      font-weight: 700;
    }}
    .bar-track {{
      height: 16px;
      overflow: hidden;
      border-radius: 999px;
      background: #e2e8f0;
    }}
    .bar-fill {{
      height: 100%;
      min-width: 2px;
      border-radius: 999px;
      background: #2563eb;
    }}
    .bar-value {{
      text-align: right;
      color: #334155;
      font-weight: 700;
    }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .status-card {{
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 14px 16px;
      background: #ffffff;
    }}
    .status-value {{
      margin-top: 6px;
      font-size: 26px;
      font-weight: 700;
    }}
    .equity-chart {{
      width: 100%;
      height: auto;
      display: block;
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
      <h2>Business Equity Curve</h2>
      <div class="chart-card">
        {render_svg_line_chart(build_equity_curve_points(results["business_events"]))}
        <p class="chart-note">Cumulative business PnL from evaluation costs and payouts.</p>
      </div>
    </section>

    <section>
      <h2>Cost vs Payout</h2>
      <div class="chart-card bar-list">
        {render_bar(
            "Evaluation Cost",
            metrics["total_evaluation_cost"],
            max(metrics["total_evaluation_cost"], metrics["total_net_payout"]),
            "negative",
        )}
        {render_bar(
            "Net Payout",
            metrics["total_net_payout"],
            max(metrics["total_evaluation_cost"], metrics["total_net_payout"]),
            "positive",
        )}
      </div>
    </section>

    <section>
      <h2>Evaluation Accounts Status</h2>
      <div class="status-grid">
        {_status_card_html("Passed", metrics["passed_evaluations"], "positive")}
        {_status_card_html("Failed", metrics["failed_evaluations"], "negative")}
        {_status_card_html("Active", metrics["active_evaluations"], "")}
      </div>
    </section>

    <section>
      <h2>Funded Accounts Status</h2>
      <div class="status-grid">
        {_status_card_html("Active", metrics["funded_active"], "positive")}
        {_status_card_html("Failed", metrics["funded_failed"], "negative")}
        {_status_card_html("With Payout", metrics["funded_with_payout"], "positive")}
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


def format_currency(value: float) -> str:
    return f"{value:,.2f}"


def format_percent(value: float) -> str:
    return f"{value:.2%}"


def build_equity_curve_points(
    business_events: list[dict[str, Any]],
) -> list[tuple[str, float]]:
    sorted_events = sorted(business_events, key=_business_event_sort_key)
    points = [("Start", 0.0)]
    cumulative_equity = 0.0

    for index, event in enumerate(sorted_events, start=1):
        cumulative_equity += float(event.get("amount", 0.0))
        event_time = event.get("time")
        label = "Initial" if event_time is None else str(event_time)
        points.append((f"{index}. {label}", cumulative_equity))

    return points


def render_bar(
    label: str,
    value: float,
    max_value: float,
    value_class: str = "",
) -> str:
    width = 0.0 if max_value == 0 else abs(value) / abs(max_value) * 100
    width = max(0.0, min(width, 100.0))
    class_attr = f" {value_class}" if value_class else ""

    return (
        '<div class="bar-row">'
        f'<div class="bar-label">{escape(label)}</div>'
        '<div class="bar-track">'
        f'<div class="bar-fill" style="width: {width:.2f}%;"></div>'
        "</div>"
        f'<div class="bar-value{class_attr}">{escape(format_currency(value))}</div>'
        "</div>"
    )


def render_svg_line_chart(points: list[tuple[str, float]]) -> str:
    if len(points) <= 1:
        return '<p class="empty">No business events to chart.</p>'

    width = 900
    height = 260
    padding_left = 56
    padding_right = 24
    padding_top = 24
    padding_bottom = 42
    chart_width = width - padding_left - padding_right
    chart_height = height - padding_top - padding_bottom

    values = [value for _, value in points]
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        min_value -= 1
        max_value += 1

    value_range = max_value - min_value

    def x_position(index: int) -> float:
        if len(points) == 1:
            return padding_left
        return padding_left + index / (len(points) - 1) * chart_width

    def y_position(value: float) -> float:
        return padding_top + (max_value - value) / value_range * chart_height

    polyline_points = " ".join(
        f"{x_position(index):.2f},{y_position(value):.2f}"
        for index, (_, value) in enumerate(points)
    )
    zero_y = y_position(0.0) if min_value <= 0 <= max_value else None

    circles = []
    for index, (label, value) in enumerate(points):
        css_class = _number_class(value)
        circles.append(
            (
                f'<circle cx="{x_position(index):.2f}" cy="{y_position(value):.2f}" '
                'r="4" fill="#2563eb">'
                f"<title>{escape(label)}: {escape(format_currency(value))}</title>"
                "</circle>"
                f'<text x="{x_position(index):.2f}" y="{height - 14}" '
                'text-anchor="middle" font-size="11" fill="#64748b">'
                f"{index}"
                "</text>"
                f'<text x="{x_position(index):.2f}" y="{y_position(value) - 8:.2f}" '
                'text-anchor="middle" font-size="11" '
                f'fill="{_svg_value_color(css_class)}">'
                f"{escape(format_currency(value))}"
                "</text>"
            )
        )

    zero_line = ""
    if zero_y is not None:
        zero_line = (
            f'<line x1="{padding_left}" y1="{zero_y:.2f}" '
            f'x2="{width - padding_right}" y2="{zero_y:.2f}" '
            'stroke="#94a3b8" stroke-dasharray="4 4" />'
        )

    return f"""
<svg class="equity-chart" viewBox="0 0 {width} {height}" role="img" aria-label="Business equity curve">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
  <line x1="{padding_left}" y1="{padding_top}" x2="{padding_left}" y2="{height - padding_bottom}" stroke="#cbd5e1" />
  <line x1="{padding_left}" y1="{height - padding_bottom}" x2="{width - padding_right}" y2="{height - padding_bottom}" stroke="#cbd5e1" />
  {zero_line}
  <text x="8" y="{padding_top + 4}" font-size="12" fill="#64748b">{escape(format_currency(max_value))}</text>
  <text x="8" y="{height - padding_bottom}" font-size="12" fill="#64748b">{escape(format_currency(min_value))}</text>
  <polyline points="{polyline_points}" fill="none" stroke="#2563eb" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />
  {''.join(circles)}
</svg>
"""


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
        return escape(format_percent(float(value)))
    if value_type == "money":
        return escape(format_currency(float(value)))
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


def _status_card_html(label: str, value: int, css_class: str) -> str:
    class_attr = f" {css_class}" if css_class else ""
    return (
        '<div class="status-card">'
        f'<div class="card-label">{escape(label)}</div>'
        f'<div class="status-value{class_attr}">{escape(str(value))}</div>'
        "</div>"
    )


def _business_event_sort_key(event: dict[str, Any]) -> tuple[int, str]:
    event_time = event.get("time")
    if event_time is None or pd.isna(event_time):
        return (0, "")
    return (1, str(event_time))


def _svg_value_color(css_class: str) -> str:
    if css_class == "positive":
        return "#047857"
    if css_class == "negative":
        return "#b91c1c"
    return "#334155"
