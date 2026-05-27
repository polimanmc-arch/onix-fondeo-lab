from __future__ import annotations

import pandas as pd
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import (
    app_comparison_row,
    build_trade_diagnostics,
    comparison_display_dataframe,
    comparison_rows_to_dataframe,
    compute_stochastic_for_chart,
    export_comparison_rows,
    filter_trades_for_explorer,
    filter_trades_for_chart,
    build_market_data_summary,
    build_account_event_timeline,
    build_preset_rules_summary,
    account_event_timeline_dataframe,
    format_account_event_timeline_dataframe,
    current_controls_snapshot,
    format_rule_value,
    load_app_setup,
    market_data_file_options,
    market_data_option_label,
    prepare_trade_pnl_chart_data,
    preset_option_label,
    preset_rules_rows,
    save_app_setup,
    slugify_setup_name,
    validate_market_data_file,
)


def test_build_trade_diagnostics_calculates_overtrading_metrics():
    trades = pd.DataFrame(
        [
            {
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "NetPnL": 100,
                "GrossPnL": 110,
                "TotalCost": 10,
                "ExitReason": "TP",
            },
            {
                "EntryTime": "2024-01-02 10:00:00",
                "ExitTime": "2024-01-02 10:20:00",
                "NetPnL": -50,
                "GrossPnL": -40,
                "TotalCost": 10,
                "ExitReason": "SL",
            },
            {
                "EntryTime": "2024-01-03 09:30:00",
                "ExitTime": "2024-01-03 09:45:00",
                "NetPnL": 25,
                "GrossPnL": 30,
                "TotalCost": 5,
                "ExitReason": "TIME",
            },
        ]
    )

    diagnostics = build_trade_diagnostics(trades)

    assert diagnostics["overtrading"]["total_trades"] == 3
    assert diagnostics["overtrading"]["unique_trading_days"] == 2
    assert diagnostics["overtrading"]["average_trades_per_day"] == 1.5
    assert diagnostics["overtrading"]["max_trades_in_one_day"] == 2
    assert diagnostics["overtrading"]["median_holding_minutes"] == 15


def test_build_trade_diagnostics_handles_missing_cost_columns():
    trades = pd.DataFrame(
        [
            {
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "NetPnL": 100,
            }
        ]
    )

    diagnostics = build_trade_diagnostics(trades)

    assert diagnostics["costs"]["total_cost"] == 0
    assert diagnostics["costs"]["total_commission"] == 0
    assert diagnostics["costs"]["net_pnl"] == 100


def test_build_trade_diagnostics_exit_reason_table():
    trades = pd.DataFrame(
        [
            {"ExitTime": "2024-01-02 09:40:00", "NetPnL": 100, "ExitReason": "TP"},
            {"ExitTime": "2024-01-02 09:41:00", "NetPnL": 50, "ExitReason": "TP"},
            {"ExitTime": "2024-01-02 09:42:00", "NetPnL": -25, "ExitReason": "SL"},
        ]
    )

    table = build_trade_diagnostics(trades)["exit_reason_table"]
    tp_row = table[table["ExitReason"] == "TP"].iloc[0]

    assert tp_row["Trades"] == 2
    assert tp_row["NetPnL"] == 150
    assert tp_row["AverageNetPnL"] == 75


def test_prepare_trade_pnl_chart_data_adds_cumulative_pnl():
    trades = pd.DataFrame(
        [
            {"TradeID": 10, "NetPnL": 100},
            {"TradeID": 11, "NetPnL": -25},
            {"TradeID": 12, "NetPnL": 50},
        ]
    )

    data = prepare_trade_pnl_chart_data(trades)

    assert data["TradeIndex"].tolist() == [10, 11, 12]
    assert data["CumulativeNetPnL"].tolist() == [100, 75, 125]


def test_filter_trades_for_chart_filters_by_date_and_direction():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "Direction": "Long",
            },
            {
                "TradeID": 2,
                "EntryTime": "2024-01-02 10:30:00",
                "ExitTime": "2024-01-02 10:40:00",
                "Direction": "Short",
            },
            {
                "TradeID": 3,
                "EntryTime": "2024-01-03 09:30:00",
                "ExitTime": "2024-01-03 09:40:00",
                "Direction": "Long",
            },
        ]
    )

    filtered = filter_trades_for_chart(
        trades,
        start_dt=pd.Timestamp("2024-01-02 09:00:00"),
        end_dt=pd.Timestamp("2024-01-02 11:00:00"),
        direction_filter="Long only",
        max_trades=100,
    )

    assert filtered["TradeID"].tolist() == [1]


def test_filter_trades_for_explorer_applies_filters():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": "2024-01-02 09:30:00",
                "ExitTime": "2024-01-02 09:40:00",
                "Direction": "Long",
                "NetPnL": 100,
                "ExitReason": "TP",
                "PhaseProfile": "EVALUATION",
            },
            {
                "TradeID": 2,
                "EntryTime": "2024-01-02 10:30:00",
                "ExitTime": "2024-01-02 10:40:00",
                "Direction": "Short",
                "NetPnL": -25,
                "ExitReason": "SL",
                "PhaseProfile": "FUNDED",
            },
        ]
    )

    filtered = filter_trades_for_explorer(
        trades,
        {
            "direction": "Long",
            "exit_reason": "TP",
            "phase_profile": "EVALUATION",
            "entry_date": "2024-01-02",
            "minimum_net_pnl": 0,
            "maximum_net_pnl": 200,
        },
    )

    assert filtered["TradeID"].tolist() == [1]


def test_compute_stochastic_for_chart_returns_k_and_d():
    ohlc = pd.DataFrame(
        {
            "DateTime": pd.date_range("2024-01-02 09:30:00", periods=6, freq="min"),
            "Open": [10, 20, 30, 40, 50, 60],
            "High": [100] * 6,
            "Low": [0] * 6,
            "Close": [10, 20, 30, 40, 50, 60],
        }
    )

    stochastic = compute_stochastic_for_chart(
        ohlc,
        {"period_k": 3, "period_d": 2, "smooth": 2},
    )

    assert {"DateTime", "K", "D"}.issubset(stochastic.columns)
    assert stochastic["K"].notna().any()
    assert stochastic["D"].notna().any()


def test_preset_option_label_includes_hierarchical_context():
    label = preset_option_label(
        {
            "preset_id": "tradeify_growth_50k",
            "company": "Tradeify",
            "plan": "Growth",
            "account_size": 50000,
        }
    )

    assert label == "Tradeify | Growth | 50K | tradeify_growth_50k"


def test_app_comparison_row_includes_bankroll_and_risk_adjusted_score():
    row = app_comparison_row(
        preset={
            "preset_id": "tradeify_growth_50k",
            "company": "Tradeify",
            "plan": "Growth",
            "account_name": "50K Growth",
            "account_size": 50000,
        },
        metrics={
            "pass_rate": 0.5,
            "payout_rate_on_evaluations": 0.25,
            "payout_rate_on_passed": 0.5,
            "total_net_payout": 900,
            "net_business_pnl": 600,
            "roi": 2.0,
        },
        bankroll_result={"metrics": {"final_bankroll": 3600}},
        risk_result={"metrics": {"ruin_probability": 0.25}},
    )

    assert row["final_bankroll"] == 3600
    assert row["ruin_probability"] == 0.25
    assert row["risk_adjusted_score"] == 450


def test_comparison_rows_to_dataframe_sorts_by_net_business_pnl():
    rows = [
        {"company": "B", "plan": "Two", "account_size": 50000, "net_business_pnl": -10},
        {"company": "A", "plan": "One", "account_size": 50000, "net_business_pnl": 100},
    ]

    dataframe = comparison_rows_to_dataframe(rows)

    assert dataframe["company"].tolist() == ["A", "B"]


def test_comparison_display_dataframe_formats_readable_values():
    rows = [
        {
            "company": "Tradeify",
            "plan": "Growth",
            "account_size": 50000,
            "pass_rate": 0.5,
            "payout_rate": 0.25,
            "total_net_payout": 900,
            "net_business_pnl": 600,
            "roi": 2.0,
            "final_bankroll": 3600,
            "ruin_probability": 0.1,
            "risk_adjusted_score": 540,
            "preset_id": "tradeify_growth_50k",
        }
    ]

    dataframe = comparison_display_dataframe(rows)

    assert dataframe.loc[0, "account_size"] == "50K"
    assert dataframe.loc[0, "pass_rate"] == "50.00%"
    assert dataframe.loc[0, "net_business_pnl"] == "$600.00"


def test_export_comparison_rows_creates_csv(tmp_path):
    rows = [
        {
            "company": "Tradeify",
            "plan": "Growth",
            "account_size": 50000,
            "net_business_pnl": 600,
            "preset_id": "tradeify_growth_50k",
        }
    ]

    output_path = export_comparison_rows(rows, tmp_path)

    assert output_path == tmp_path / "app_preset_comparison.csv"
    assert output_path.exists()
    assert "tradeify_growth_50k" in output_path.read_text(encoding="utf-8")


def test_market_data_file_options_lists_csv_files(tmp_path):
    (tmp_path / "B.csv").write_text("x", encoding="utf-8")
    (tmp_path / "A.csv").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    options = market_data_file_options(tmp_path)

    assert options == [
        str((tmp_path / "A.csv").as_posix()),
        str((tmp_path / "B.csv").as_posix()),
    ]


def test_market_data_option_label_is_readable():
    label = market_data_option_label("data/market_data/MNQ_1m.csv")

    assert label == "MNQ_1m.csv (data/market_data)"


def test_validate_market_data_file_returns_summary_for_valid_csv(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text(
        "\n".join(
            [
                "DateTime,Open,High,Low,Close,Volume",
                "2024-01-02 09:30:00,10,12,9,11,100",
                "2024-01-02 09:31:00,11,13,10,12,120",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_market_data_file(str(file_path), symbol="NQ")

    assert result["ok"] is True
    assert result["summary"]["rows"] == 2
    assert result["summary"]["symbols"] == "NQ"


def test_validate_market_data_file_returns_error_for_invalid_csv(tmp_path):
    file_path = tmp_path / "bad.csv"
    file_path.write_text(
        "\n".join(
            [
                "DateTime,Open,High,Low,Close",
                "2024-01-02 09:30:00,10,9,8,11",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_market_data_file(str(file_path), symbol="NQ")

    assert result["ok"] is False
    assert "invalid ohlc" in result["error"].lower()


def test_build_market_data_summary_handles_empty_dataframe():
    ohlc = pd.DataFrame(columns=["DateTime", "Open", "High", "Low", "Close"])

    summary = build_market_data_summary(ohlc, "empty.csv")

    assert summary["file_path"] == "empty.csv"
    assert summary["rows"] == 0


def test_slugify_setup_name_creates_safe_filename_stem():
    assert slugify_setup_name("MNQ Growth 50K / Morning") == "mnq_growth_50k_morning"


def test_save_and_load_app_setup_round_trip(tmp_path):
    setup = {
        "version": 1,
        "market_data_path": "data/market_data/sample_NQ_1m.csv",
        "symbol": "NQ",
        "preset_id": "tradeify_growth_50k",
    }

    output_path = save_app_setup("My Setup", setup, tmp_path)
    loaded = load_app_setup(output_path)

    assert output_path == tmp_path / "my_setup.json"
    assert loaded == setup


def test_current_controls_snapshot_captures_reproducible_setup():
    snapshot = current_controls_snapshot(
        {
            "market_data_path": "data/market_data/sample_NQ_1m.csv",
            "symbol": "NQ",
            "point_value": 20.0,
            "selected_preset_id": "lucid_trading_lucidflex_50k",
            "comparison_enabled": False,
            "comparison_preset_ids": [],
            "strategy_name": "stochastic",
            "strategy_params": {"period_k": 20, "period_d": 5},
            "strategy_start_time": "09:45",
            "strategy_end_time": "16:00",
            "force_close_time": "16:00",
            "contracts": 1,
            "stop_loss_points": 70,
            "take_profit_points": 50,
            "max_holding_minutes": 60,
            "commission_per_side": 1.24,
            "slippage_points": 0.25,
            "spread_points": 0.25,
            "bankroll": 3000,
            "monte_carlo_runs": 100,
            "monte_carlo_max_accounts": 100,
        }
    )

    assert snapshot["preset_id"] == "lucid_trading_lucidflex_50k"
    assert snapshot["strategy_params"]["period_k"] == 20
    assert snapshot["bankroll"] == 3000


def test_build_preset_rules_summary_extracts_key_sections():
    preset = {
        "preset_id": "tradeify_growth_50k",
        "company": "Tradeify",
        "plan": "Growth",
        "account_name": "Growth 50K",
        "account_size": 50000,
        "is_official": True,
        "rules_verified": True,
        "evaluation": {
            "enabled": True,
            "evaluation_cost": 87,
            "profit_target": 3000,
        },
        "funded": {
            "enabled": True,
            "payout_trigger_profit": 3000,
            "profit_split": 0.9,
        },
        "metadata": {
            "drawdown_type": "EOD trailing max drawdown",
            "funded_consistency_percent": 0.35,
        },
    }

    summary = build_preset_rules_summary(preset)

    assert summary["identity"]["company"] == "Tradeify"
    assert summary["evaluation"]["profit_target"] == 3000
    assert summary["funded"]["profit_split"] == 0.9
    assert summary["metadata"]["drawdown_type"] == "EOD trailing max drawdown"


def test_preset_rules_rows_formats_values_for_display():
    summary = {
        "identity": {"company": "Tradeify", "account_size": 50000},
        "evaluation": {"profit_target": 3000},
        "funded": {"profit_split": 0.9},
        "metadata": {"funded_consistency_enabled": True},
    }

    rows = preset_rules_rows(summary)
    values_by_rule = {row["Rule"]: row["Value"] for row in rows}

    assert values_by_rule["profit_target"] == "$3,000.00"
    assert values_by_rule["profit_split"] == "90.00%"
    assert values_by_rule["funded_consistency_enabled"] == "Yes"


def test_format_rule_value_handles_complex_metadata():
    assert format_rule_value("payout_tiers", {"1": 1500}) == '{"1": 1500}'
    assert format_rule_value("platforms", ["Tradovate", "NinjaTrader"]) == "Tradovate, NinjaTrader"


def test_build_account_event_timeline_includes_core_events():
    account = SimpleNamespace(
        account_id=1,
        phase="EVALUATION",
        status="PASSED",
        pnl=3000,
        started_at=None,
        ended_at="2024-01-02 10:00:00",
        result_reason="Profit target reached",
    )
    payout = SimpleNamespace(
        account_id=1,
        payout_time="2024-01-03 10:00:00",
        gross_payout=1000,
        net_payout=900,
    )
    results = {
        "accounts": [account],
        "business_events": [
            {"time": None, "type": "EVALUATION_COST", "amount": -87, "account_id": 1},
            {"time": "2024-01-03 10:00:00", "type": "PAYOUT", "amount": 900, "account_id": 1},
        ],
        "payouts": [payout],
        "trade_log": [
            {
                "AccountID": 1,
                "Phase": "EVALUATION",
                "TradeID": 10,
                "TradeTime": "2024-01-02 10:00:00",
                "AppliedNetPnL": 100,
                "AccountPnL": 3000,
                "StatusAfterTrade": "PASSED",
                "StatusReason": "EVALUATION_TARGET_REACHED; Profit target reached",
            }
        ],
    }

    timeline = build_account_event_timeline(results)
    event_types = {row["EventType"] for row in timeline}

    assert "ACCOUNT_OPENED" in event_types
    assert "ACCOUNT_PASSED" in event_types
    assert "EVALUATION_COST" in event_types
    assert "PAYOUT" in event_types
    assert "EVALUATION_TARGET_REACHED" in event_types
    assert [row["Step"] for row in timeline] == list(range(1, len(timeline) + 1))


def test_account_event_timeline_dataframe_uses_expected_columns():
    rows = [
        {
            "Step": 1,
            "Time": None,
            "AccountID": 1,
            "Phase": "EVALUATION",
            "EventType": "EVALUATION_COST",
            "TradeID": None,
            "Amount": -87,
            "AccountPnL": None,
            "Status": None,
            "Reason": None,
        }
    ]

    dataframe = account_event_timeline_dataframe(rows)
    formatted = format_account_event_timeline_dataframe(dataframe)

    assert dataframe.columns.tolist()[0:5] == ["Step", "Time", "AccountID", "Phase", "EventType"]
    assert formatted.loc[0, "Amount"] == "-$87.00"
