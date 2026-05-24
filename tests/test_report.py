from onix_fondeo.models import Account
from onix_fondeo.report import export_comparison_results, generate_html_report


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
