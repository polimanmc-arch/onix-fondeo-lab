from pathlib import Path

import pytest

from onix_fondeo.risk_of_ruin import (
    estimate_required_bankroll,
    export_risk_of_ruin_results,
    extract_account_net_outcomes,
    run_monte_carlo_ruin_simulation,
)


def test_extract_account_net_outcomes_groups_events_by_account_id():
    results = {
        "business_events": [
            {"account_id": 1, "amount": -100},
            {"account_id": 1, "amount": 900},
            {"account_id": 2, "amount": -100},
        ]
    }

    outcomes = extract_account_net_outcomes(results)

    assert outcomes[0]["account_id"] == 1
    assert outcomes[0]["net_amount"] == 800
    assert outcomes[0]["cost_amount"] == -100
    assert outcomes[0]["payout_amount"] == 900
    assert outcomes[1]["net_amount"] == -100


def test_monte_carlo_positive_outcomes_have_zero_ruin_probability():
    result = run_monte_carlo_ruin_simulation(
        [{"net_amount": 100}],
        initial_bankroll=1000,
        runs=100,
        max_accounts=10,
    )

    assert result["metrics"]["ruin_probability"] == 0


def test_monte_carlo_negative_outcomes_with_small_bankroll_ruin():
    result = run_monte_carlo_ruin_simulation(
        [{"net_amount": -100}],
        initial_bankroll=50,
        runs=100,
        max_accounts=10,
    )

    assert result["metrics"]["ruin_probability"] == 1


def test_monte_carlo_seed_is_deterministic():
    outcomes = [{"net_amount": -100}, {"net_amount": 200}]

    first = run_monte_carlo_ruin_simulation(outcomes, 300, runs=50, seed=7)
    second = run_monte_carlo_ruin_simulation(outcomes, 300, runs=50, seed=7)

    assert first["paths"] == second["paths"]


def test_estimate_required_bankroll_returns_first_bankroll_meeting_target():
    result = estimate_required_bankroll(
        [{"net_amount": -100}],
        target_ruin_probability=0.0,
        bankroll_grid=[50, 1000],
        runs=100,
        max_accounts=5,
    )

    assert result["recommended_bankroll"] == 1000


def test_empty_outcomes_returns_safe_result():
    result = run_monte_carlo_ruin_simulation([], initial_bankroll=1000)

    assert result["metrics"]["ruin_probability"] == 0
    assert result["metrics"]["median_final_bankroll"] == 1000
    assert result["paths"] == []


def test_export_risk_of_ruin_results_creates_files(tmp_path: Path):
    result = run_monte_carlo_ruin_simulation(
        [{"net_amount": 100}],
        initial_bankroll=1000,
        runs=5,
        max_accounts=2,
    )
    required = estimate_required_bankroll(
        [{"net_amount": 100}],
        bankroll_grid=[500],
        runs=5,
        max_accounts=2,
    )

    files = export_risk_of_ruin_results(
        result,
        output_dir=tmp_path,
        required_bankroll_result=required,
    )

    assert files["risk_of_ruin_metrics"].exists()
    assert files["risk_of_ruin_paths"].exists()
    assert files["required_bankroll_grid"].exists()


def test_negative_initial_bankroll_raises_value_error():
    with pytest.raises(ValueError, match="initial_bankroll"):
        run_monte_carlo_ruin_simulation([], initial_bankroll=-1)
