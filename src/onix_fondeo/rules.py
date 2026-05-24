from __future__ import annotations

from typing import Any, Optional

from onix_fondeo.models import Account, Payout


def check_max_drawdown(account: Account, max_drawdown: float) -> bool:
    return account.pnl <= -max_drawdown


def check_max_daily_loss(
    account: Account,
    max_daily_loss: Optional[float],
) -> bool:
    if max_daily_loss is None:
        return False
    return any(daily_pnl <= -max_daily_loss for daily_pnl in account.daily_pnl.values())


def check_minimum_trading_days(
    account: Account,
    minimum_trading_days: int,
) -> bool:
    return len(account.trading_days) >= minimum_trading_days


def check_consistency(account: Account, consistency_percent: float) -> bool:
    if account.pnl <= 0:
        return False
    if not account.daily_pnl:
        return False

    best_day = max(account.daily_pnl.values())
    return best_day <= account.pnl * consistency_percent


def check_evaluation_status(
    account: Account,
    evaluation_rules: dict[str, Any],
) -> tuple[str, str | None]:
    if check_max_drawdown(account, evaluation_rules["max_drawdown"]):
        return "FAILED", "Max drawdown breached"

    if check_max_daily_loss(account, evaluation_rules.get("max_daily_loss")):
        return "FAILED", "Max daily loss breached"

    if account.pnl < evaluation_rules["profit_target"]:
        return "ACTIVE", None

    if not check_minimum_trading_days(
        account,
        evaluation_rules["minimum_trading_days"],
    ):
        return "ACTIVE", None

    if evaluation_rules.get("consistency_enabled", False) and not check_consistency(
        account,
        evaluation_rules["consistency_percent"],
    ):
        return "ACTIVE", None

    return "PASSED", "Profit target reached"


def check_funded_status(
    account: Account,
    funded_rules: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> tuple[str, str | None]:
    metadata = metadata or {}

    if not funded_rules.get("enabled", True):
        return "ACTIVE", None

    if check_max_drawdown(account, funded_rules["max_drawdown"]):
        return "FAILED", "Funded max drawdown breached"

    if check_max_daily_loss(account, funded_rules.get("max_daily_loss")):
        return "FAILED", "Funded max daily loss breached"

    is_eligible, reasons = check_funded_payout_eligibility(
        account,
        funded_rules,
        metadata,
    )
    if is_eligible:
        return "PAYOUT_ELIGIBLE", "Payout trigger reached"

    if "Funded consistency rule not satisfied" in reasons:
        return "ACTIVE", "Funded consistency rule not satisfied"

    winning_days_reason = _first_reason_starting_with(
        reasons,
        "Winning days requirement not satisfied",
    )
    if winning_days_reason is not None:
        return "ACTIVE", winning_days_reason

    return "ACTIVE", None


def _first_reason_starting_with(
    reasons: list[str],
    prefix: str,
) -> str | None:
    for reason in reasons:
        if reason.startswith(prefix):
            return reason
    return None


def check_funded_consistency(
    account: Account,
    funded_rules: dict[str, Any],
    metadata: dict[str, Any],
) -> bool:
    if (
        metadata.get("funded_consistency_enabled") is not True
        and not _has_consistency_progression(metadata)
    ):
        return True

    consistency_percent = get_current_consistency_percent(account, metadata)
    if consistency_percent is None:
        return True

    if account.pnl <= 0:
        return False
    if not account.daily_pnl:
        return False

    best_day = max(account.daily_pnl.values())
    consistency_ratio = best_day / account.pnl
    return consistency_ratio <= consistency_percent


def _has_consistency_progression(metadata: dict[str, Any]) -> bool:
    return bool(
        metadata.get("consistency_progression_post_2025_09_12")
        or metadata.get("consistency_progression_post_2025_12_09")
    )


def get_next_payout_number(account: Account) -> int:
    return len(getattr(account, "payouts", [])) + 1


def get_payout_tier_key(payout_number: int) -> str:
    if payout_number in {1, 2, 3}:
        return str(payout_number)
    return "4_plus"


def get_tiered_payout_amount(
    account: Account,
    funded_rules: dict[str, Any],
    metadata: dict[str, Any],
) -> float:
    payout_number = get_next_payout_number(account)
    fallback = funded_rules.get("minimum_withdrawable_profit")
    selected_value = None

    payout_tiers = metadata.get("payout_tiers")
    if payout_tiers:
        tier_key = get_payout_tier_key(payout_number)
        selected_value = payout_tiers.get(tier_key)
        if selected_value is None and payout_number >= 4:
            selected_value = payout_tiers.get("4_plus")

    elif (
        metadata.get("payout_1_maximum") is not None
        or metadata.get("payout_2_plus_maximum") is not None
    ):
        if payout_number == 1:
            selected_value = metadata.get("payout_1_maximum")
        else:
            selected_value = metadata.get("payout_2_plus_maximum")

    elif (
        metadata.get("payouts_1_to_3_maximum") is not None
        or metadata.get("payouts_4_to_5_maximum") is not None
    ):
        if payout_number <= 3:
            selected_value = metadata.get("payouts_1_to_3_maximum")
        else:
            selected_value = metadata.get("payouts_4_to_5_maximum")

    if selected_value is None:
        selected_value = fallback
    if selected_value is None:
        return 0.0

    return float(selected_value)


def get_current_consistency_percent(
    account: Account,
    metadata: dict[str, Any],
) -> float | None:
    payout_number = get_next_payout_number(account)
    progression = metadata.get("consistency_progression_post_2025_09_12")
    if progression is None:
        progression = metadata.get("consistency_progression_post_2025_12_09")

    if progression:
        index = min(payout_number - 1, len(progression) - 1)
        return float(progression[index])

    consistency_percent = metadata.get("funded_consistency_percent")
    if consistency_percent is None:
        return None

    return float(consistency_percent)


def get_required_winning_days(
    metadata: dict[str, Any],
) -> tuple[int | None, float | None]:
    required_day_keys = [
        "funded_minimum_trading_days_with_profit",
        "minimum_winning_days",
        "minimum_trading_days_with_profit",
        "winning_days_required",
        "payout_minimum_winning_days",
    ]
    threshold_keys = [
        "minimum_daily_profit",
        "minimum_daily_profit_for_payout_day",
        "winning_day_threshold",
        "minimum_profit_per_winning_day",
    ]

    required_days = _first_metadata_value(metadata, required_day_keys)
    if required_days is None:
        return None, None

    threshold = _first_metadata_value(metadata, threshold_keys)
    return int(required_days), _optional_float(threshold)


def count_winning_days(
    account: Account,
    threshold: Optional[float],
) -> int:
    if threshold is None:
        return sum(1 for daily_pnl in account.daily_pnl.values() if daily_pnl > 0)

    return sum(
        1
        for daily_pnl in account.daily_pnl.values()
        if daily_pnl >= threshold
    )


def check_winning_days_requirement(
    account: Account,
    metadata: dict[str, Any],
) -> tuple[bool, str | None]:
    required_days, threshold = get_required_winning_days(metadata)
    if required_days is None:
        return True, None

    winning_days = count_winning_days(account, threshold)
    if winning_days >= required_days:
        return True, None

    return (
        False,
        f"Winning days requirement not satisfied: {winning_days}/{required_days}",
    )


def _first_metadata_value(
    metadata: dict[str, Any],
    keys: list[str],
) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return value
    return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def check_funded_payout_eligibility(
    account: Account,
    funded_rules: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons = []

    if account.pnl < funded_rules["payout_trigger_profit"]:
        reasons.append("Payout trigger not reached")
        return False, reasons

    if not check_funded_consistency(account, funded_rules, metadata):
        reasons.append("Funded consistency rule not satisfied")
        return False, reasons

    winning_days_ok, winning_days_reason = check_winning_days_requirement(
        account,
        metadata,
    )
    if not winning_days_ok:
        reasons.append(str(winning_days_reason))
        return False, reasons

    return True, reasons


def process_funded_payout(
    account: Account,
    payout_time: Any,
    funded_rules: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> Payout:
    gross_payout = get_tiered_payout_amount(account, funded_rules, metadata or {})
    payout = account.register_payout(
        payout_time=payout_time,
        gross_payout=gross_payout,
        profit_split=funded_rules["profit_split"],
    )

    if funded_rules.get("reset_after_payout", False):
        account.pnl = 0.0
        account.high_watermark = 0.0
        account.daily_pnl.clear()
        account.trading_days.clear()
    else:
        account.pnl -= gross_payout
        account.high_watermark = account.pnl

    return payout
