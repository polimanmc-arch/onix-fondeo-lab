from __future__ import annotations

import json
import random
from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def extract_account_net_outcomes(results: dict[str, Any]) -> list[dict[str, Any]]:
    grouped_events: dict[Any, list[dict[str, Any]]] = {}
    fallback_outcomes = []

    for index, event in enumerate(results.get("business_events", []), start=1):
        account_id = event.get("account_id")
        if account_id is None:
            fallback_outcomes.append(_outcome_from_events(f"event_{index}", [event]))
        else:
            grouped_events.setdefault(account_id, []).append(event)

    outcomes = [
        _outcome_from_events(account_id, events)
        for account_id, events in sorted(grouped_events.items(), key=lambda item: item[0])
    ]
    outcomes.extend(fallback_outcomes)
    return outcomes


def run_monte_carlo_ruin_simulation(
    account_outcomes: list[dict[str, Any]],
    initial_bankroll: float,
    account_cost: float | None = None,
    runs: int = 10000,
    max_accounts: int = 100,
    seed: int | None = 42,
) -> dict[str, Any]:
    if initial_bankroll < 0:
        raise ValueError("initial_bankroll must be greater than or equal to 0")
    if not account_outcomes or runs <= 0 or max_accounts <= 0:
        return _empty_ruin_result(initial_bankroll, runs, max_accounts)

    random_generator = random.Random(seed)
    paths = []
    for run_id in range(1, runs + 1):
        bankroll = float(initial_bankroll)
        peak = bankroll
        lowest_bankroll = bankroll
        max_drawdown = 0.0
        ruined = False
        accounts_completed = 0

        for _ in range(max_accounts):
            if account_cost is not None and account_cost > 0 and bankroll < account_cost:
                ruined = True
                break

            outcome = random_generator.choice(account_outcomes)
            bankroll += float(outcome.get("net_amount", 0) or 0)
            accounts_completed += 1
            lowest_bankroll = min(lowest_bankroll, bankroll)
            peak = max(peak, bankroll)
            max_drawdown = max(max_drawdown, peak - bankroll)

            if bankroll < 0:
                ruined = True
                break

        paths.append(
            {
                "run_id": run_id,
                "final_bankroll": bankroll,
                "ruined": ruined,
                "lowest_bankroll": lowest_bankroll,
                "max_drawdown": max_drawdown,
                "accounts_completed": accounts_completed,
            }
        )

    metrics = _ruin_metrics(paths, initial_bankroll, runs, max_accounts)
    return {"metrics": metrics, "paths": paths}


def estimate_required_bankroll(
    account_outcomes: list[dict[str, Any]],
    target_ruin_probability: float = 0.05,
    bankroll_grid: list[float] | None = None,
    account_cost: float | None = None,
    runs: int = 5000,
    max_accounts: int = 100,
    seed: int | None = 42,
) -> dict[str, Any]:
    bankroll_grid = bankroll_grid or [
        500,
        1000,
        1500,
        2000,
        2500,
        3000,
        4000,
        5000,
        7500,
        10000,
    ]
    grid_results = []
    recommended_bankroll = None

    for bankroll in bankroll_grid:
        result = run_monte_carlo_ruin_simulation(
            account_outcomes=account_outcomes,
            initial_bankroll=bankroll,
            account_cost=account_cost,
            runs=runs,
            max_accounts=max_accounts,
            seed=seed,
        )
        ruin_probability = result["metrics"]["ruin_probability"]
        grid_row = {
            "bankroll": bankroll,
            "ruin_probability": ruin_probability,
            "survival_probability": result["metrics"]["survival_probability"],
        }
        grid_results.append(grid_row)
        if recommended_bankroll is None and ruin_probability <= target_ruin_probability:
            recommended_bankroll = bankroll

    return {
        "target_ruin_probability": target_ruin_probability,
        "recommended_bankroll": recommended_bankroll,
        "grid_results": grid_results,
    }


def export_risk_of_ruin_results(
    result: dict[str, Any],
    output_dir: str | Path = "data/output",
    required_bankroll_result: dict[str, Any] | None = None,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    file_paths = {"risk_of_ruin_metrics": output_path / "risk_of_ruin_metrics.json"}
    with file_paths["risk_of_ruin_metrics"].open("w", encoding="utf-8") as file:
        json.dump(result.get("metrics", {}), file, indent=2, default=str)

    if result.get("paths"):
        file_paths["risk_of_ruin_paths"] = output_path / "risk_of_ruin_paths.csv"
        pd.DataFrame(result["paths"]).to_csv(file_paths["risk_of_ruin_paths"], index=False)

    if required_bankroll_result is not None:
        file_paths["required_bankroll_grid"] = output_path / "required_bankroll_grid.csv"
        pd.DataFrame(required_bankroll_result.get("grid_results", [])).to_csv(
            file_paths["required_bankroll_grid"],
            index=False,
        )

    return file_paths


def _outcome_from_events(account_id: Any, events: list[dict[str, Any]]) -> dict[str, Any]:
    amounts = [float(event.get("amount", 0) or 0) for event in events]
    payout_amount = sum(amount for amount in amounts if amount > 0)
    cost_amount = sum(amount for amount in amounts if amount < 0)
    return {
        "account_id": account_id,
        "phase": None,
        "net_amount": sum(amounts),
        "cost_amount": cost_amount,
        "payout_amount": payout_amount,
        "passed_evaluation": None,
        "reached_payout": payout_amount > 0,
    }


def _empty_ruin_result(
    initial_bankroll: float,
    runs: int,
    max_accounts: int,
) -> dict[str, Any]:
    return {
        "metrics": {
            "runs": runs,
            "max_accounts": max_accounts,
            "initial_bankroll": initial_bankroll,
            "ruin_probability": 0.0,
            "survival_probability": 1.0,
            "median_final_bankroll": initial_bankroll,
            "mean_final_bankroll": initial_bankroll,
            "p5_final_bankroll": initial_bankroll,
            "p95_final_bankroll": initial_bankroll,
            "average_lowest_bankroll": initial_bankroll,
            "worst_lowest_bankroll": initial_bankroll,
            "average_max_drawdown": 0.0,
            "worst_max_drawdown": 0.0,
            "average_accounts_completed": 0.0,
        },
        "paths": [],
    }


def _ruin_metrics(
    paths: list[dict[str, Any]],
    initial_bankroll: float,
    runs: int,
    max_accounts: int,
) -> dict[str, Any]:
    final_bankrolls = sorted(float(path["final_bankroll"]) for path in paths)
    lowest_bankrolls = [float(path["lowest_bankroll"]) for path in paths]
    max_drawdowns = [float(path["max_drawdown"]) for path in paths]
    accounts_completed = [int(path["accounts_completed"]) for path in paths]
    ruined_count = sum(1 for path in paths if path["ruined"])

    return {
        "runs": runs,
        "max_accounts": max_accounts,
        "initial_bankroll": initial_bankroll,
        "ruin_probability": ruined_count / len(paths),
        "survival_probability": 1 - ruined_count / len(paths),
        "median_final_bankroll": median(final_bankrolls),
        "mean_final_bankroll": mean(final_bankrolls),
        "p5_final_bankroll": _percentile(final_bankrolls, 0.05),
        "p95_final_bankroll": _percentile(final_bankrolls, 0.95),
        "average_lowest_bankroll": mean(lowest_bankrolls),
        "worst_lowest_bankroll": min(lowest_bankrolls),
        "average_max_drawdown": mean(max_drawdowns),
        "worst_max_drawdown": max(max_drawdowns),
        "average_accounts_completed": mean(accounts_completed),
    }


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    index = round((len(sorted_values) - 1) * percentile)
    return sorted_values[index]
