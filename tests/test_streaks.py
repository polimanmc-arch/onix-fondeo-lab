from pathlib import Path

from onix_fondeo.streaks import (
    calculate_binary_runs_z_score,
    calculate_max_streak,
    calculate_streak_analysis,
    export_streak_analysis,
)


def test_calculate_max_streak_counts_target_value():
    assert calculate_max_streak([0, 0, 1, 0, 0, 0], 0) == 3
    assert calculate_max_streak([], 0) == 0


def test_calculate_binary_runs_z_score_counts_runs():
    result = calculate_binary_runs_z_score([1, 1, 0, 0, 1])

    assert result["runs"] == 3
    assert result["ones"] == 3
    assert result["zeros"] == 2
    assert result["z_score"] is not None


def test_calculate_binary_runs_z_score_all_ones_is_safe():
    result = calculate_binary_runs_z_score([1, 1, 1])

    assert result["z_score"] is None
    assert "Insufficient variation" in result["note"]


def test_calculate_streak_analysis_with_minimal_business_events():
    results = {
        "accounts": [],
        "business_events": [
            {"account_id": 1, "amount": -100},
            {"account_id": 2, "amount": -100},
            {"account_id": 3, "amount": 900},
        ],
    }

    analysis = calculate_streak_analysis(results)

    assert analysis["funded_payout_sequence"] == [0, 0, 1]
    assert analysis["net_positive_sequence"] == [0, 0, 1]
    assert analysis["max_consecutive_no_payout_accounts"] == 2
    assert "z_score_funded_payout" in analysis


def test_export_streak_analysis_creates_json(tmp_path: Path):
    analysis = calculate_streak_analysis({"accounts": [], "business_events": []})

    file_path = export_streak_analysis(analysis, output_dir=tmp_path)

    assert file_path.exists()
    assert "funded_payout_sequence" in file_path.read_text(encoding="utf-8")
