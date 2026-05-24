from __future__ import annotations

from typing import Any


def calculate_business_metrics(
    results: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, float | int]:
    accounts = results["accounts"]
    payouts = results["payouts"]

    evaluation_accounts = [
        account for account in accounts if account.phase == "EVALUATION"
    ]
    funded_accounts = [account for account in accounts if account.phase == "FUNDED"]

    total_evaluations = len(evaluation_accounts)
    passed_evaluations = sum(
        1 for account in evaluation_accounts if account.status == "PASSED"
    )
    failed_evaluations = sum(
        1 for account in evaluation_accounts if account.status == "FAILED"
    )
    active_evaluations = sum(
        1 for account in evaluation_accounts if account.status == "ACTIVE"
    )

    funded_accounts_created = len(funded_accounts)
    funded_failed = sum(1 for account in funded_accounts if account.status == "FAILED")
    funded_active = sum(1 for account in funded_accounts if account.status == "ACTIVE")
    funded_with_payout = sum(
        1 for account in funded_accounts if len(account.payouts) > 0
    )

    total_payouts = len(payouts)
    total_gross_payout = sum(payout.gross_payout for payout in payouts)
    total_net_payout = sum(payout.net_payout for payout in payouts)

    evaluation_cost = config["evaluation"].get("evaluation_cost") or 0
    total_evaluation_cost = total_evaluations * evaluation_cost
    net_business_pnl = total_net_payout - total_evaluation_cost

    return {
        "total_evaluations": total_evaluations,
        "passed_evaluations": passed_evaluations,
        "failed_evaluations": failed_evaluations,
        "active_evaluations": active_evaluations,
        "funded_accounts_created": funded_accounts_created,
        "funded_failed": funded_failed,
        "funded_active": funded_active,
        "funded_with_payout": funded_with_payout,
        "pass_rate": _safe_divide(passed_evaluations, total_evaluations),
        "payout_rate_on_evaluations": _safe_divide(
            funded_with_payout,
            total_evaluations,
        ),
        "payout_rate_on_passed": _safe_divide(
            funded_with_payout,
            passed_evaluations,
        ),
        "total_evaluation_cost": total_evaluation_cost,
        "total_gross_payout": total_gross_payout,
        "total_net_payout": total_net_payout,
        "net_business_pnl": net_business_pnl,
        "roi": _safe_divide(net_business_pnl, total_evaluation_cost),
        "expected_value_per_evaluation": _safe_divide(
            net_business_pnl,
            total_evaluations,
        ),
        "average_net_payout": _safe_divide(total_net_payout, total_payouts),
        "total_payouts": total_payouts,
    }


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
