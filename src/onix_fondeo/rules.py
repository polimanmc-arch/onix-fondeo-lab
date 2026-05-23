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
) -> tuple[str, str | None]:
    if not funded_rules.get("enabled", True):
        return "ACTIVE", None

    if check_max_drawdown(account, funded_rules["max_drawdown"]):
        return "FAILED", "Funded max drawdown breached"

    if check_max_daily_loss(account, funded_rules.get("max_daily_loss")):
        return "FAILED", "Funded max daily loss breached"

    if account.pnl >= funded_rules["payout_trigger_profit"]:
        return "PAYOUT_ELIGIBLE", "Payout trigger reached"

    return "ACTIVE", None


def process_funded_payout(
    account: Account,
    payout_time: Any,
    funded_rules: dict[str, Any],
) -> Payout:
    gross_payout = funded_rules["minimum_withdrawable_profit"]
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
