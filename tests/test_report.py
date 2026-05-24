from onix_fondeo.report import export_comparison_results


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
