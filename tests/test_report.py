from onix_fondeo.models import Account
from onix_fondeo.report import (
    export_comparison_results,
    export_optimization_results,
    generate_html_report,
)


def test_export_comparison_results_creates_csv_and_html(tmp_path):
    rows = [
        {
            "preset_id": "preset_a",
            "company": "Company A",
            "plan": "Plan A",
            "account_name": "Account A",
            "account_size": 50000,
            "straight_to_funded": False,
            "total_evaluations": 1,
            "passed_evaluations": 1,
            "failed_evaluations": 0,
            "active_evaluations": 0,
            "funded_accounts_created": 1,
            "funded_failed": 0,
            "funded_active": 1,
            "funded_with_payout": 1,
            "pass_rate": 1.0,
            "payout_rate_on_evaluations": 1.0,
            "payout_rate_on_passed": 1.0,
            "total_evaluation_cost": 100,
            "total_gross_payout": 1000,
            "total_net_payout": 900,
            "net_business_pnl": 800,
            "roi": 8.0,
            "expected_value_per_evaluation": 800,
            "total_payouts": 1,
        }
    ]

    files = export_comparison_results(rows, output_dir=tmp_path)

    assert files["comparison_summary"].exists()
    assert files["comparison_report"].exists()
    assert "preset_a" in files["comparison_summary"].read_text(encoding="utf-8")
    assert (
        "Onix Fondeo Lab - Preset Comparison Report"
        in files["comparison_report"].read_text(encoding="utf-8")
    )


def test_generate_html_report_includes_strategy_summary_when_metrics_are_provided(tmp_path):
    report_path = generate_html_report(
        _results(),
        _metrics(),
        output_dir=tmp_path,
        strategy_metrics={
            "total_trades": 2,
            "win_rate": 0.5,
            "net_pnl": 100,
            "profit_factor": 2.0,
            "average_trade": 50,
            "best_trade": 150,
            "worst_trade": -50,
            "average_holding_minutes": 12.5,
            "tp_exits": 1,
            "sl_exits": 1,
            "time_exits": 0,
            "end_of_data_exits": 0,
        },
    )

    html = report_path.read_text(encoding="utf-8")

    assert "Strategy Summary" in html
    assert "Strategy Exit Reasons" in html


def test_generate_html_report_omits_strategy_summary_without_metrics(tmp_path):
    report_path = generate_html_report(_results(), _metrics(), output_dir=tmp_path)

    html = report_path.read_text(encoding="utf-8")

    assert "Strategy Summary" not in html


def test_generate_html_report_includes_bankroll_summary_when_provided(tmp_path):
    report_path = generate_html_report(
        _results(),
        _metrics(),
        output_dir=tmp_path,
        bankroll_result={
            "curve": [
                {
                    "step": 0,
                    "time": None,
                    "event_type": "INITIAL",
                    "amount": 0,
                    "account_id": None,
                    "bankroll": 3000,
                }
            ],
            "metrics": {
                "initial_bankroll": 3000,
                "final_bankroll": 3000,
                "lowest_bankroll": 3000,
                "highest_bankroll": 3000,
                "net_bankroll_change": 0,
                "bankroll_return": 0,
                "max_bankroll_drawdown": 0,
                "max_bankroll_drawdown_percent": 0,
                "bankroll_ruined": False,
                "ruin_step": None,
                "events_count": 0,
                "accounts_affordable_remaining": 30,
            },
        },
    )

    html = report_path.read_text(encoding="utf-8")

    assert "Bankroll Summary" in html
    assert "Accounts Affordable Remaining" in html


def test_generate_html_report_includes_risk_of_ruin_when_provided(tmp_path):
    report_path = generate_html_report(
        _results(),
        _metrics(),
        output_dir=tmp_path,
        risk_of_ruin_result={
            "metrics": {
                "runs": 100,
                "max_accounts": 10,
                "initial_bankroll": 3000,
                "ruin_probability": 0.1,
                "survival_probability": 0.9,
                "median_final_bankroll": 3500,
                "mean_final_bankroll": 3600,
                "p5_final_bankroll": 1000,
                "p95_final_bankroll": 7000,
                "average_lowest_bankroll": 2500,
                "worst_lowest_bankroll": -100,
                "average_max_drawdown": 500,
                "worst_max_drawdown": 1200,
                "average_accounts_completed": 8,
            },
            "paths": [],
        },
        required_bankroll_result={
            "target_ruin_probability": 0.05,
            "recommended_bankroll": 5000,
            "grid_results": [
                {
                    "bankroll": 3000,
                    "ruin_probability": 0.1,
                    "survival_probability": 0.9,
                }
            ],
        },
    )

    html = report_path.read_text(encoding="utf-8")

    assert "Risk of Ruin Summary" in html
    assert "Required Bankroll Grid" in html


def test_export_optimization_results_adds_ranking_sections(tmp_path):
    files = export_optimization_results(_optimization_rows(), output_dir=tmp_path)

    html = files["optimization_report"].read_text(encoding="utf-8")

    assert "Top 10 by Funding Net PnL" in html
    assert "Top 10 by ROI" in html
    assert "Top 10 by Strategy Net PnL" in html
    assert "Top 10 by Profit Factor" in html
    assert "Ranking by Preset" in html


def test_export_optimization_results_min_trades_filters_rankings_only(tmp_path):
    files = export_optimization_results(
        _optimization_rows(),
        output_dir=tmp_path,
        min_trades=10,
    )

    csv_text = files["optimization_results"].read_text(encoding="utf-8")
    html = files["optimization_report"].read_text(encoding="utf-8")
    top_funding_section = _section_between(
        html,
        "<h2>Top 10 by Funding Net PnL</h2>",
        "<h2>Top 10 by ROI</h2>",
    )

    assert "too_few_trades" in csv_text
    assert "too_few_trades" not in top_funding_section
    assert "enough_trades" in top_funding_section
    assert "CSV export includes all rows" in html


def _results():
    return {
        "accounts": [Account(account_id=1, phase="EVALUATION")],
        "trade_log": [],
        "payouts": [],
        "business_events": [],
    }


def _metrics():
    return {
        "total_evaluations": 1,
        "passed_evaluations": 0,
        "failed_evaluations": 0,
        "active_evaluations": 1,
        "funded_accounts_created": 0,
        "funded_failed": 0,
        "funded_active": 0,
        "funded_with_payout": 0,
        "pass_rate": 0.0,
        "payout_rate_on_evaluations": 0.0,
        "payout_rate_on_passed": 0.0,
        "total_evaluation_cost": 0.0,
        "total_gross_payout": 0.0,
        "total_net_payout": 0.0,
        "net_business_pnl": 0.0,
        "roi": 0.0,
        "expected_value_per_evaluation": 0.0,
        "average_net_payout": 0.0,
        "total_payouts": 0,
    }


def _optimization_rows():
    base_row = {
        "run_id": 1,
        "company": "TestCo",
        "plan": "Plan",
        "account_name": "Account",
        "account_size": 50000,
        "strategy": "stochastic",
        "stoch_k_period": 14,
        "stoch_d_period": 3,
        "oversold": 20,
        "overbought": 80,
        "signal_mode": "cross",
        "use_d_confirmation": False,
        "min_k_d_gap": 0,
        "cooldown_bars": 0,
        "stop_loss_points": 20,
        "take_profit_points": 30,
        "win_rate": 0.5,
        "average_trade": 25,
        "max_consecutive_wins": 2,
        "max_consecutive_losses": 1,
        "total_evaluations": 2,
        "passed_evaluations": 1,
        "pass_rate": 0.5,
        "funded_with_payout": 1,
        "payout_rate_on_evaluations": 0.5,
        "total_evaluation_cost": 200,
        "total_net_payout": 900,
        "expected_value_per_evaluation": 350,
        "total_payouts": 1,
    }
    return [
        {
            **base_row,
            "preset_id": "too_few_trades",
            "total_trades": 2,
            "net_pnl": 5000,
            "profit_factor": 10,
            "net_business_pnl": 2000,
            "roi": 10,
        },
        {
            **base_row,
            "run_id": 2,
            "preset_id": "enough_trades",
            "total_trades": 30,
            "net_pnl": 1000,
            "profit_factor": 2,
            "net_business_pnl": 800,
            "roi": 4,
        },
    ]


def _section_between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]
