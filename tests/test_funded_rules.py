from datetime import date, datetime

from onix_fondeo.models import Account
from onix_fondeo.rules import (
    check_funded_payout_eligibility,
    check_funded_status,
    process_funded_payout,
)


def funded_rules() -> dict:
    return {
        "enabled": True,
        "max_drawdown": 2000,
        "max_daily_loss": None,
        "mll_freeze_profit": 2100,
        "minimum_withdrawable_profit": 2000,
        "payout_trigger_profit": 4100,
        "profit_split": 0.8,
        "reset_after_payout": False,
    }


def test_funded_account_fails_when_max_drawdown_is_breached():
    account = Account(account_id=1, phase="FUNDED", pnl=-2000)

    status, reason = check_funded_status(account, funded_rules())

    assert status == "FAILED"
    assert reason == "Funded max drawdown breached"


def test_funded_account_becomes_payout_eligible_at_trigger_profit():
    account = Account(account_id=1, phase="FUNDED", pnl=4100)

    status, reason = check_funded_status(account, funded_rules())

    assert status == "PAYOUT_ELIGIBLE"
    assert reason == "Payout trigger reached"


def test_process_funded_payout_uses_minimum_withdrawable_profit():
    account = Account(account_id=1, phase="FUNDED", pnl=4100)

    payout = process_funded_payout(
        account,
        payout_time=datetime(2026, 5, 23),
        funded_rules=funded_rules(),
    )

    assert payout.gross_payout == 2000


def test_process_funded_payout_applies_profit_split():
    account = Account(account_id=1, phase="FUNDED", pnl=4100)

    payout = process_funded_payout(
        account,
        payout_time=datetime(2026, 5, 23),
        funded_rules=funded_rules(),
    )

    assert payout.net_payout == 1600


def test_process_funded_payout_subtracts_gross_payout_when_not_resetting():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=4100,
        high_watermark=4100,
        trading_days={date(2026, 5, 23)},
        daily_pnl={date(2026, 5, 23): 4100},
    )

    process_funded_payout(
        account,
        payout_time=datetime(2026, 5, 23),
        funded_rules=funded_rules(),
    )

    assert account.pnl == 2100
    assert account.trading_days == {date(2026, 5, 23)}
    assert account.daily_pnl == {date(2026, 5, 23): 4100}


def test_funded_payout_is_eligible_when_consistency_is_satisfied():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={
            date(2026, 5, 20): 1500,
            date(2026, 5, 21): 1500,
            date(2026, 5, 22): 2000,
        },
    )
    metadata = {
        "funded_consistency_enabled": True,
        "funded_consistency_percent": 0.4,
    }

    is_eligible, reasons = check_funded_payout_eligibility(
        account,
        funded_rules(),
        metadata,
    )

    assert is_eligible is True
    assert reasons == []


def test_funded_payout_is_blocked_when_consistency_is_violated():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={
            date(2026, 5, 20): 3000,
            date(2026, 5, 21): 1000,
            date(2026, 5, 22): 1000,
        },
    )
    metadata = {
        "funded_consistency_enabled": True,
        "funded_consistency_percent": 0.4,
    }

    status, reason = check_funded_status(account, funded_rules(), metadata)

    assert status == "ACTIVE"
    assert reason == "Funded consistency rule not satisfied"


def test_funded_consistency_disabled_does_not_block_payout():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={date(2026, 5, 20): 5000},
    )
    metadata = {
        "funded_consistency_enabled": False,
        "funded_consistency_percent": 0.4,
    }

    status, reason = check_funded_status(account, funded_rules(), metadata)

    assert status == "PAYOUT_ELIGIBLE"
    assert reason == "Payout trigger reached"


def test_consistency_failure_does_not_fail_funded_account():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={date(2026, 5, 20): 5000},
    )
    metadata = {
        "funded_consistency_enabled": True,
        "funded_consistency_percent": 0.4,
    }

    status, _ = check_funded_status(account, funded_rules(), metadata)

    assert status != "FAILED"
