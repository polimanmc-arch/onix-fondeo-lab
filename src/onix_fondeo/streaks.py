from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def calculate_max_streak(values: list, target_value) -> int:
    max_streak = 0
    current_streak = 0
    for value in values:
        if value == target_value:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    return max_streak


def calculate_binary_runs_z_score(sequence: list[int]) -> dict[str, Any]:
    n1 = sum(1 for value in sequence if value == 1)
    n0 = sum(1 for value in sequence if value == 0)
    n = n1 + n0
    runs = _count_runs(sequence)

    if n1 == 0 or n0 == 0 or n < 2:
        return {
            "n": n,
            "ones": n1,
            "zeros": n0,
            "runs": runs,
            "expected_runs": None,
            "variance": None,
            "z_score": None,
            "note": "Insufficient variation for runs-test z-score.",
        }

    expected_runs = 1 + (2 * n1 * n0) / n
    variance = (2 * n1 * n0 * (2 * n1 * n0 - n)) / (n**2 * (n - 1))
    z_score = None if variance <= 0 else (runs - expected_runs) / math.sqrt(variance)
    return {
        "n": n,
        "ones": n1,
        "zeros": n0,
        "runs": runs,
        "expected_runs": expected_runs,
        "variance": variance,
        "z_score": z_score,
        "note": None,
    }


def build_account_sequence(results: dict[str, Any], mode: str = "funded_payout") -> list[int]:
    if mode == "passed_evaluation":
        return _passed_evaluation_sequence(results)

    grouped_events = _business_events_by_account(results)
    if mode == "funded_payout":
        return [
            1 if any(float(event.get("amount", 0) or 0) > 0 for event in events) else 0
            for _, events in grouped_events
        ]
    if mode == "net_positive":
        return [
            1 if sum(float(event.get("amount", 0) or 0) for event in events) > 0 else 0
            for _, events in grouped_events
        ]

    raise ValueError(f"Unsupported account sequence mode: {mode}")


def calculate_streak_analysis(results: dict[str, Any]) -> dict[str, Any]:
    funded_payout_sequence = build_account_sequence(results, "funded_payout")
    net_positive_sequence = build_account_sequence(results, "net_positive")
    passed_evaluation_sequence = build_account_sequence(results, "passed_evaluation")

    return {
        "funded_payout_sequence": funded_payout_sequence,
        "net_positive_sequence": net_positive_sequence,
        "passed_evaluation_sequence": passed_evaluation_sequence,
        "max_consecutive_no_payout_accounts": calculate_max_streak(
            funded_payout_sequence,
            0,
        ),
        "max_consecutive_payout_accounts": calculate_max_streak(
            funded_payout_sequence,
            1,
        ),
        "max_consecutive_negative_accounts": calculate_max_streak(
            net_positive_sequence,
            0,
        ),
        "max_consecutive_positive_accounts": calculate_max_streak(
            net_positive_sequence,
            1,
        ),
        "max_consecutive_failed_evaluations": calculate_max_streak(
            passed_evaluation_sequence,
            0,
        ),
        "max_consecutive_passed_evaluations": calculate_max_streak(
            passed_evaluation_sequence,
            1,
        ),
        "z_score_funded_payout": calculate_binary_runs_z_score(funded_payout_sequence),
        "z_score_net_positive": calculate_binary_runs_z_score(net_positive_sequence),
        "z_score_passed_evaluation": calculate_binary_runs_z_score(
            passed_evaluation_sequence
        ),
    }


def export_streak_analysis(
    streak_analysis: dict[str, Any],
    output_dir: str | Path = "data/output",
) -> Path:
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / "streak_analysis.json"
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(streak_analysis, file, indent=2, default=str)
    return file_path


def _count_runs(sequence: list[int]) -> int:
    if not sequence:
        return 0
    runs = 1
    for previous, current in zip(sequence, sequence[1:]):
        if current != previous:
            runs += 1
    return runs


def _business_events_by_account(results: dict[str, Any]) -> list[tuple[Any, list[dict]]]:
    grouped: dict[Any, list[dict]] = {}
    fallback_index = 0
    for event in results.get("business_events", []):
        account_id = event.get("account_id")
        if account_id is None:
            fallback_index += 1
            account_id = f"event_{fallback_index}"
        grouped.setdefault(account_id, []).append(event)
    return sorted(grouped.items(), key=lambda item: str(item[0]))


def _passed_evaluation_sequence(results: dict[str, Any]) -> list[int]:
    accounts = results.get("accounts", [])
    evaluation_accounts = [
        account for account in accounts if getattr(account, "phase", None) == "EVALUATION"
    ]
    if evaluation_accounts:
        return [
            1 if getattr(account, "status", None) == "PASSED" else 0
            for account in sorted(
                evaluation_accounts,
                key=lambda account: getattr(account, "account_id", 0),
            )
        ]

    grouped_events = _business_events_by_account(results)
    return [
        1 if any(float(event.get("amount", 0) or 0) > 0 for event in events) else 0
        for _, events in grouped_events
    ]
