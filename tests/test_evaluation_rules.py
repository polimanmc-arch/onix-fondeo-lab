from datetime import date

from onix_fondeo.models import Account
from onix_fondeo.rules import check_evaluation_status


def evaluation_rules() -> dict:
    return {
        "profit_target": 3000,
        "max_drawdown": 2000,
        "max_daily_loss": None,
        "minimum_trading_days": 2,
        "daily_profit_cap": 1300,
        "consistency_enabled": True,
        "consistency_percent": 0.5,
    }


def test_evaluation_fails_when_max_drawdown_is_breached():
    account = Account(account_id=1, phase="EVALUATION", pnl=-2000)

    status, reason = check_evaluation_status(account, evaluation_rules())

    assert status == "FAILED"
    assert reason == "Max drawdown breached"


def test_evaluation_does_not_pass_without_minimum_trading_days():
    account = Account(
        account_id=1,
        phase="EVALUATION",
        pnl=3000,
        trading_days={date(2026, 5, 23)},
        daily_pnl={date(2026, 5, 23): 1500},
    )

    status, reason = check_evaluation_status(account, evaluation_rules())

    assert status == "ACTIVE"
    assert reason is None


def test_evaluation_passes_when_profit_days_and_consistency_are_met():
    account = Account(
        account_id=1,
        phase="EVALUATION",
        pnl=3000,
        trading_days={date(2026, 5, 23), date(2026, 5, 24)},
        daily_pnl={
            date(2026, 5, 23): 1500,
            date(2026, 5, 24): 1500,
        },
    )

    status, reason = check_evaluation_status(account, evaluation_rules())

    assert status == "PASSED"
    assert reason == "Profit target reached"


def test_evaluation_does_not_pass_when_consistency_is_violated():
    account = Account(
        account_id=1,
        phase="EVALUATION",
        pnl=3000,
        trading_days={date(2026, 5, 23), date(2026, 5, 24)},
        daily_pnl={
            date(2026, 5, 23): 1600,
            date(2026, 5, 24): 1400,
        },
    )

    status, reason = check_evaluation_status(account, evaluation_rules())

    assert status == "ACTIVE"
    assert reason is None
