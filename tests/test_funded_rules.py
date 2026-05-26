from datetime import date, datetime

from onix_fondeo.models import Account
from onix_fondeo.rules import (
    apply_account_aware_exit,
    apply_daily_loss_exit,
    calculate_daily_continuity_payout_amount,
    check_daily_continuity_eligibility,
    check_drawdown_breach,
    check_funded_consistency,
    check_funded_payout_eligibility,
    check_funded_status,
    check_winning_days_requirement,
    count_winning_days,
    get_current_consistency_percent,
    get_next_payout_number,
    get_payout_tier_key,
    get_required_winning_days,
    get_tiered_payout_amount,
    initialize_drawdown_floor,
    is_daily_payout_policy,
    process_funded_payout,
    update_eod_trailing_drawdown,
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


def test_apply_account_aware_exit_clips_evaluation_target():
    account = Account(account_id=1, phase="EVALUATION", pnl=2850)

    adjusted, reason = apply_account_aware_exit(
        account,
        300,
        {"profit_target": 3000, "max_drawdown": 2000},
    )

    assert adjusted == 150
    assert reason == "EVALUATION_TARGET_REACHED"


def test_apply_account_aware_exit_clips_evaluation_max_loss():
    account = Account(account_id=1, phase="EVALUATION", pnl=-1900)

    adjusted, reason = apply_account_aware_exit(
        account,
        -300,
        {"profit_target": 3000, "max_drawdown": 2000},
    )

    assert adjusted == -100
    assert reason == "ACCOUNT_MAX_LOSS"


def test_apply_account_aware_exit_clips_funded_payout_trigger():
    account = Account(account_id=1, phase="FUNDED", pnl=3900)

    adjusted, reason = apply_account_aware_exit(
        account,
        300,
        {"payout_trigger_profit": 4000, "max_drawdown": 2000},
    )

    assert adjusted == 100
    assert reason == "FUNDED_PAYOUT_TRIGGER_REACHED"


def test_apply_account_aware_exit_clips_funded_max_loss():
    account = Account(account_id=1, phase="FUNDED", pnl=-1900)

    adjusted, reason = apply_account_aware_exit(
        account,
        -300,
        {"payout_trigger_profit": 4000, "max_drawdown": 2000},
    )

    assert adjusted == -100
    assert reason == "ACCOUNT_MAX_LOSS"


def test_apply_account_aware_exit_does_not_adjust_without_threshold_cross():
    account = Account(account_id=1, phase="EVALUATION", pnl=1000)

    adjusted, reason = apply_account_aware_exit(
        account,
        100,
        {"profit_target": 3000, "max_drawdown": 2000},
    )

    assert adjusted == 100
    assert reason is None


def test_apply_daily_loss_exit_clips_daily_loss():
    account = Account(account_id=1, phase="FUNDED")
    account.daily_pnl[date(2026, 5, 20)] = -900

    adjusted, reason = apply_daily_loss_exit(
        account,
        -300,
        max_daily_loss=1000,
        trade_date=date(2026, 5, 20),
    )

    assert adjusted == -100
    assert reason == "ACCOUNT_DAILY_LOSS"


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


def test_no_winning_days_requirement_does_not_block_payout():
    account = Account(account_id=1, phase="FUNDED", pnl=4100)

    is_eligible, reasons = check_funded_payout_eligibility(
        account,
        funded_rules(),
        metadata={},
    )

    assert is_eligible is True
    assert reasons == []


def test_winning_days_requirement_is_satisfied_with_threshold():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={
            date(2026, 5, 18): 150,
            date(2026, 5, 19): 200,
            date(2026, 5, 20): 175,
            date(2026, 5, 21): 300,
            date(2026, 5, 22): 250,
        },
    )
    metadata = {
        "minimum_winning_days": 5,
        "winning_day_threshold": 150,
    }

    is_eligible, reasons = check_funded_payout_eligibility(
        account,
        funded_rules(),
        metadata,
    )

    assert is_eligible is True
    assert reasons == []


def test_winning_days_requirement_blocks_payout_without_failing_account():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={
            date(2026, 5, 18): 150,
            date(2026, 5, 19): 200,
            date(2026, 5, 20): 175,
            date(2026, 5, 21): 100,
            date(2026, 5, 22): -50,
        },
    )
    metadata = {
        "minimum_winning_days": 5,
        "winning_day_threshold": 150,
    }

    status, reason = check_funded_status(account, funded_rules(), metadata)

    assert status == "ACTIVE"
    assert reason == "Winning days requirement not satisfied: 3/5"


def test_winning_days_threshold_none_counts_positive_days():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={
            date(2026, 5, 18): 100,
            date(2026, 5, 19): -50,
            date(2026, 5, 20): 25,
        },
    )
    metadata = {"winning_days_required": 2}

    required_days, threshold = get_required_winning_days(metadata)
    is_satisfied, reason = check_winning_days_requirement(account, metadata)

    assert required_days == 2
    assert threshold is None
    assert count_winning_days(account, threshold) == 2
    assert is_satisfied is True
    assert reason is None


def test_get_next_payout_number_uses_account_payouts():
    account = Account(account_id=1, phase="FUNDED")

    assert get_next_payout_number(account) == 1

    account.register_payout(
        payout_time=datetime(2026, 5, 23),
        gross_payout=1000,
        profit_split=0.9,
    )

    assert get_next_payout_number(account) == 2


def test_get_payout_tier_key_maps_fourth_and_later_to_four_plus():
    assert get_payout_tier_key(1) == "1"
    assert get_payout_tier_key(2) == "2"
    assert get_payout_tier_key(3) == "3"
    assert get_payout_tier_key(4) == "4_plus"
    assert get_payout_tier_key(9) == "4_plus"


def test_tiered_payout_amount_uses_payout_tiers():
    account = Account(account_id=1, phase="FUNDED")
    metadata = {"payout_tiers": {"1": 1500, "2": 2000, "3": 2500, "4_plus": 3000}}

    assert get_tiered_payout_amount(account, funded_rules(), metadata) == 1500

    account.register_payout(datetime(2026, 5, 23), 1500, 0.9)
    assert get_tiered_payout_amount(account, funded_rules(), metadata) == 2000

    account.register_payout(datetime(2026, 5, 24), 2000, 0.9)
    assert get_tiered_payout_amount(account, funded_rules(), metadata) == 2500

    account.register_payout(datetime(2026, 5, 25), 2500, 0.9)
    assert get_tiered_payout_amount(account, funded_rules(), metadata) == 3000


def test_tiered_payout_amount_uses_first_and_second_plus_maximums():
    account = Account(account_id=1, phase="FUNDED")
    metadata = {
        "payout_1_maximum": 1000,
        "payout_2_plus_maximum": 1500,
    }

    assert get_tiered_payout_amount(account, funded_rules(), metadata) == 1000

    account.register_payout(datetime(2026, 5, 23), 1000, 0.9)

    assert get_tiered_payout_amount(account, funded_rules(), metadata) == 1500


def test_consistency_progression_uses_next_payout_number():
    account = Account(account_id=1, phase="FUNDED")
    metadata = {"consistency_progression_post_2025_09_12": [0.2, 0.25, 0.3]}

    assert get_current_consistency_percent(account, metadata) == 0.2

    account.register_payout(datetime(2026, 5, 23), 1000, 0.9)
    assert get_current_consistency_percent(account, metadata) == 0.25

    account.register_payout(datetime(2026, 5, 24), 1000, 0.9)
    assert get_current_consistency_percent(account, metadata) == 0.3

    account.register_payout(datetime(2026, 5, 25), 1000, 0.9)
    assert get_current_consistency_percent(account, metadata) == 0.3


def test_consistency_progression_is_enforced_without_enabled_flag():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=5000,
        daily_pnl={date(2026, 5, 23): 1500, date(2026, 5, 24): 3500},
    )
    metadata = {"consistency_progression_post_2025_09_12": [0.2, 0.25, 0.3]}

    assert check_funded_consistency(account, funded_rules(), metadata) is False


def test_process_funded_payout_uses_tiered_amounts():
    account = Account(account_id=1, phase="FUNDED", pnl=10000)
    metadata = {"payout_tiers": {"1": 1500, "2": 2000, "3": 2500, "4_plus": 3000}}

    first_payout = process_funded_payout(
        account,
        payout_time=datetime(2026, 5, 23),
        funded_rules=funded_rules(),
        metadata=metadata,
    )
    second_payout = process_funded_payout(
        account,
        payout_time=datetime(2026, 5, 24),
        funded_rules=funded_rules(),
        metadata=metadata,
    )

    assert first_payout.gross_payout == 1500
    assert second_payout.gross_payout == 2000


def test_is_daily_payout_policy_detects_supported_metadata_keys():
    assert is_daily_payout_policy({"funded_payout_policy": "Select Daily"}) is True
    assert is_daily_payout_policy({"payout_style": "Daily Payout Policy"}) is True
    assert is_daily_payout_policy({"daily_payouts": True}) is True
    assert is_daily_payout_policy({"funded_payout_policy": "Select Flex"}) is False


def test_daily_continuity_payout_is_zero_when_buffer_is_not_satisfied():
    account = Account(account_id=1, phase="FUNDED", pnl=3000)
    metadata = {
        "payout_cap": 1000,
        "minimum_payout": 250,
        "buffer_amount": 2100,
    }

    assert calculate_daily_continuity_payout_amount(account, metadata) == 0.0


def test_daily_continuity_payout_is_zero_when_below_minimum():
    account = Account(account_id=1, phase="FUNDED", pnl=100)
    metadata = {
        "payout_cap": None,
        "minimum_payout": 250,
        "buffer_amount": 0,
    }

    assert calculate_daily_continuity_payout_amount(account, metadata) == 0.0


def test_daily_continuity_payout_uses_cap_when_two_times_profit_exceeds_cap():
    account = Account(account_id=1, phase="FUNDED", pnl=3100)
    metadata = {
        "payout_cap": 1000,
        "minimum_payout": 250,
        "buffer_amount": 2100,
    }

    assert calculate_daily_continuity_payout_amount(account, metadata) == 1000


def test_daily_payout_policy_can_be_eligible_without_normal_trigger():
    rules = funded_rules()
    rules["payout_trigger_profit"] = 999999
    account = Account(account_id=1, phase="FUNDED", pnl=3100)
    metadata = {
        "daily_payouts": True,
        "payout_cap": 1000,
        "minimum_payout": 250,
        "buffer_amount": 2100,
    }

    is_eligible, reasons = check_funded_payout_eligibility(account, rules, metadata)

    assert is_eligible is True
    assert reasons == []


def test_daily_payout_policy_is_blocked_when_buffer_is_not_satisfied():
    rules = funded_rules()
    rules["payout_trigger_profit"] = 0
    account = Account(account_id=1, phase="FUNDED", pnl=3000)
    metadata = {
        "daily_payouts": True,
        "payout_cap": 1000,
        "minimum_payout": 250,
        "buffer_amount": 2100,
    }

    status, reason = check_funded_status(account, rules, metadata)

    assert status == "ACTIVE"
    assert reason == "Daily continuity rule not satisfied"


def test_check_daily_continuity_eligibility_ignores_non_daily_policies():
    account = Account(account_id=1, phase="FUNDED", pnl=0)

    is_eligible, reason = check_daily_continuity_eligibility(account, {})

    assert is_eligible is True
    assert reason is None


def test_process_funded_payout_uses_daily_continuity_amount():
    account = Account(account_id=1, phase="FUNDED", pnl=3100)
    metadata = {
        "daily_payouts": True,
        "payout_cap": 1000,
        "minimum_payout": 250,
        "buffer_amount": 2100,
    }
    rules = funded_rules()
    rules["minimum_withdrawable_profit"] = 2000

    payout = process_funded_payout(
        account,
        payout_time=datetime(2026, 5, 23),
        funded_rules=rules,
        metadata=metadata,
    )

    assert payout.gross_payout == 1000


def test_static_drawdown_breach_still_works_without_eod_metadata():
    account = Account(account_id=1, phase="FUNDED", pnl=-2000)

    assert check_drawdown_breach(account, 2000, {}) is True


def test_eod_drawdown_initial_floor_is_static_relative_floor():
    account = Account(account_id=1, phase="FUNDED")

    initialize_drawdown_floor(account, 2000)

    assert account.trailing_drawdown_floor == -2000


def test_eod_drawdown_floor_moves_after_eod_update():
    account = Account(account_id=1, phase="FUNDED", pnl=1000)
    metadata = {"drawdown_type": "EOD trailing max drawdown"}

    update_eod_trailing_drawdown(account, 2000, metadata, account_size=50000)

    assert account.eod_high_pnl == 1000
    assert account.trailing_drawdown_floor == -1000


def test_eod_drawdown_floor_does_not_move_down():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=1000,
    )
    metadata = {"drawdown_type": "EOD trailing max drawdown"}

    update_eod_trailing_drawdown(account, 2000, metadata, account_size=50000)
    account.pnl = 500
    update_eod_trailing_drawdown(account, 2000, metadata, account_size=50000)

    assert account.eod_high_pnl == 1000
    assert account.trailing_drawdown_floor == -1000


def test_eod_drawdown_can_lock_to_absolute_floor():
    account = Account(account_id=1, phase="FUNDED", pnl=2100)
    metadata = {
        "drawdown_type": "EOD trailing max drawdown",
        "lock_trigger_balance": 52100,
        "locked_drawdown_floor": 50100,
    }

    update_eod_trailing_drawdown(account, 2000, metadata, account_size=50000)

    assert account.drawdown_locked is True
    assert account.trailing_drawdown_floor == 100


def test_eod_drawdown_breaches_against_active_floor():
    account = Account(
        account_id=1,
        phase="FUNDED",
        pnl=50,
        trailing_drawdown_floor=100,
    )
    metadata = {"drawdown_type": "EOD trailing max drawdown"}

    assert check_drawdown_breach(account, 2000, metadata) is True
