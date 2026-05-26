from pathlib import Path

import pytest

from onix_fondeo.bankroll import calculate_bankroll_curve, export_bankroll_curve


def test_empty_business_events_keeps_initial_bankroll():
    result = calculate_bankroll_curve([], initial_bankroll=3000)

    metrics = result["metrics"]
    assert metrics["final_bankroll"] == 3000
    assert metrics["lowest_bankroll"] == 3000
    assert metrics["bankroll_ruined"] is False
    assert result["curve"][0]["event_type"] == "INITIAL"


def test_cost_events_reduce_bankroll():
    result = calculate_bankroll_curve(
        [{"time": None, "type": "EVALUATION_COST", "amount": -100, "account_id": 1}],
        initial_bankroll=3000,
    )

    assert result["metrics"]["final_bankroll"] == 2900


def test_payout_events_increase_bankroll():
    result = calculate_bankroll_curve(
        [
            {"time": None, "type": "EVALUATION_COST", "amount": -100, "account_id": 1},
            {"time": "2026-05-20", "type": "PAYOUT", "amount": 900, "account_id": 1},
        ],
        initial_bankroll=3000,
    )

    assert result["metrics"]["final_bankroll"] == 3800


def test_ruin_detection_records_first_ruin_step():
    result = calculate_bankroll_curve(
        [{"time": None, "type": "EVALUATION_COST", "amount": -100, "account_id": 1}],
        initial_bankroll=50,
    )

    assert result["metrics"]["bankroll_ruined"] is True
    assert result["metrics"]["ruin_step"] == 1


def test_max_bankroll_drawdown():
    result = calculate_bankroll_curve(
        [
            {"time": "1", "type": "COST", "amount": -500, "account_id": 1},
            {"time": "2", "type": "PAYOUT", "amount": 1000, "account_id": 1},
            {"time": "3", "type": "COST", "amount": -700, "account_id": 2},
        ],
        initial_bankroll=3000,
    )

    assert result["metrics"]["max_bankroll_drawdown"] == 700


def test_accounts_affordable_remaining():
    result = calculate_bankroll_curve(
        [
            {"time": None, "type": "EVALUATION_COST", "amount": -100, "account_id": 1},
            {"time": "2026-05-20", "type": "PAYOUT", "amount": 900, "account_id": 1},
        ],
        initial_bankroll=3000,
        account_cost=100,
    )

    assert result["metrics"]["accounts_affordable_remaining"] == 38


def test_export_bankroll_curve_creates_csv(tmp_path: Path):
    result = calculate_bankroll_curve([], initial_bankroll=3000)

    file_path = export_bankroll_curve(result, output_dir=tmp_path)

    assert file_path.exists()
    assert "INITIAL" in file_path.read_text(encoding="utf-8")


def test_negative_initial_bankroll_raises_value_error():
    with pytest.raises(ValueError, match="initial_bankroll"):
        calculate_bankroll_curve([], initial_bankroll=-1)
