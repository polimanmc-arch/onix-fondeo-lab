from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BANKROLL_COLUMNS = [
    "step",
    "time",
    "event_type",
    "amount",
    "account_id",
    "bankroll",
]


def calculate_bankroll_curve(
    business_events: list[dict[str, Any]],
    initial_bankroll: float | None,
    account_cost: float | None = None,
) -> dict[str, Any] | None:
    if initial_bankroll is None:
        return None
    if initial_bankroll < 0:
        raise ValueError("initial_bankroll must be greater than or equal to 0")

    bankroll = float(initial_bankroll)
    curve = [
        {
            "step": 0,
            "time": None,
            "event_type": "INITIAL",
            "amount": 0.0,
            "account_id": None,
            "bankroll": bankroll,
        }
    ]

    sorted_events = sorted(business_events, key=_business_event_sort_key)
    ruined = bankroll < 0
    ruin_step = 0 if ruined else None

    for step, event in enumerate(sorted_events, start=1):
        amount = float(event.get("amount", 0) or 0)
        bankroll += amount
        if bankroll < 0 and not ruined:
            ruined = True
            ruin_step = step
        curve.append(
            {
                "step": step,
                "time": event.get("time"),
                "event_type": event.get("type"),
                "amount": amount,
                "account_id": event.get("account_id"),
                "bankroll": bankroll,
            }
        )

    bankroll_values = [point["bankroll"] for point in curve]
    final_bankroll = bankroll_values[-1]
    highest_bankroll = max(bankroll_values)
    lowest_bankroll = min(bankroll_values)
    max_drawdown = _max_drawdown(bankroll_values)
    metrics = {
        "initial_bankroll": float(initial_bankroll),
        "final_bankroll": final_bankroll,
        "lowest_bankroll": lowest_bankroll,
        "highest_bankroll": highest_bankroll,
        "net_bankroll_change": final_bankroll - float(initial_bankroll),
        "bankroll_return": _safe_divide(
            final_bankroll - float(initial_bankroll),
            float(initial_bankroll),
        ),
        "max_bankroll_drawdown": max_drawdown,
        "max_bankroll_drawdown_percent": _safe_divide(
            max_drawdown,
            highest_bankroll,
        ),
        "bankroll_ruined": ruined,
        "ruin_step": ruin_step,
        "events_count": len(sorted_events),
        "accounts_affordable_remaining": _accounts_affordable(
            final_bankroll,
            account_cost,
        ),
    }

    return {"curve": curve, "metrics": metrics}


def export_bankroll_curve(
    bankroll_result: dict[str, Any],
    output_dir: str | Path = "data/output",
) -> Path:
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / "bankroll_curve.csv"
    pd.DataFrame(bankroll_result["curve"], columns=BANKROLL_COLUMNS).to_csv(
        file_path,
        index=False,
    )
    return file_path


def _business_event_sort_key(event: dict[str, Any]) -> tuple[int, str]:
    event_time = event.get("time")
    if event_time is None or pd.isna(event_time):
        return (0, "")
    return (1, str(event_time))


def _max_drawdown(values: list[float]) -> float:
    peak = values[0] if values else 0.0
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, peak - value)
    return max_drawdown


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _accounts_affordable(
    final_bankroll: float,
    account_cost: float | None,
) -> int | None:
    if account_cost is None or account_cost <= 0:
        return None
    return math.floor(final_bankroll / account_cost)
