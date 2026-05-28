from datetime import datetime

import pandas as pd

from onix_fondeo.simulator import simulate_funding


def _timed_trade_row(trade_id: int, entry_time: str, exit_time: str, net_pnl: float) -> dict:
    return {
        "TradeID": trade_id,
        "EntryTime": pd.Timestamp(entry_time),
        "ExitTime": pd.Timestamp(exit_time),
        "Symbol": "NQ",
        "Direction": "Long",
        "Quantity": 1,
        "NetPnL": net_pnl,
    }


def _transition_wait_config() -> dict:
    return {
        "evaluation": {
            "evaluation_cost": 100,
            "profit_target": 1000,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_trading_days": 1,
            "daily_profit_cap": None,
            "consistency_enabled": False,
            "consistency_percent": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 5000,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": False,
        },
    }


def test_simulate_funding_returns_logs_and_creates_funded_account_on_pass():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 1500,
            },
            {
                "TradeID": 2,
                "EntryTime": datetime(2026, 5, 21, 9, 30),
                "ExitTime": datetime(2026, 5, 21, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 1500,
            },
        ]
    )
    config = {
        "evaluation": {
            "evaluation_cost": 100,
            "profit_target": 3000,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_trading_days": 2,
            "daily_profit_cap": None,
            "consistency_enabled": True,
            "consistency_percent": 0.5,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "mll_freeze_profit": 2100,
            "minimum_withdrawable_profit": 2000,
            "payout_trigger_profit": 4100,
            "profit_split": 0.8,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": False,
        },
    }

    results = simulate_funding(trades, config)

    assert set(results) == {"accounts", "trade_log", "payouts", "business_events"}
    assert any(account.phase == "EVALUATION" for account in results["accounts"])
    assert any(
        event["type"] == "EVALUATION_COST"
        for event in results["business_events"]
    )
    assert any(account.phase == "FUNDED" for account in results["accounts"])


def test_transition_wait_zero_preserves_current_behavior():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 1000,
            },
            {
                "TradeID": 2,
                "EntryTime": datetime(2026, 5, 20, 10, 15),
                "ExitTime": datetime(2026, 5, 20, 10, 30),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 100,
            },
        ]
    )
    base_config = _transition_wait_config()
    explicit_zero_config = _transition_wait_config()
    explicit_zero_config["simulation"]["pass_transition_wait_minutes"] = 0
    explicit_zero_config["simulation"]["fail_transition_wait_minutes"] = 0

    base_results = simulate_funding(trades, base_config)
    zero_results = simulate_funding(trades, explicit_zero_config)

    assert base_results["trade_log"] == zero_results["trade_log"]
    assert [account.trades_count for account in base_results["accounts"]] == [
        account.trades_count for account in zero_results["accounts"]
    ]


def test_pass_transition_wait_skips_funded_trades_inside_window():
    trades = pd.DataFrame(
        [
                _timed_trade_row(1, "2026-05-20 09:30", "2026-05-20 10:00", 1000),
                _timed_trade_row(2, "2026-05-20 10:30", "2026-05-20 10:45", 100),
                _timed_trade_row(3, "2026-05-20 11:00", "2026-05-20 11:15", 100),
        ]
    )
    config = _transition_wait_config()
    config["simulation"]["pass_transition_wait_minutes"] = 60

    results = simulate_funding(trades, config)
    funded = [account for account in results["accounts"] if account.phase == "FUNDED"][0]
    funded_logs = [row for row in results["trade_log"] if row["Phase"] == "FUNDED"]

    assert funded.earliest_trade_time == pd.Timestamp("2026-05-20 11:00")
    assert funded.trades_count == 1
    assert funded_logs[0]["TradeID"] == 3


def test_fail_transition_wait_skips_recycled_eval_trades_inside_window():
    trades = pd.DataFrame(
        [
                _timed_trade_row(1, "2026-05-20 09:30", "2026-05-20 10:00", -1000),
                _timed_trade_row(2, "2026-05-20 10:15", "2026-05-20 10:20", 100),
                _timed_trade_row(3, "2026-05-20 10:30", "2026-05-20 10:35", 100),
        ]
    )
    config = _transition_wait_config()
    config["evaluation"]["profit_target"] = 9999
    config["evaluation"]["max_drawdown"] = 1000
    config["simulation"]["fail_transition_wait_minutes"] = 30

    results = simulate_funding(trades, config)
    recycled_eval = [account for account in results["accounts"] if account.account_id == 2][0]
    recycled_logs = [
        row for row in results["trade_log"]
        if row["AccountID"] == 2 and row["Phase"] == "EVALUATION"
    ]

    assert recycled_eval.earliest_trade_time == pd.Timestamp("2026-05-20 10:30")
    assert recycled_eval.trades_count == 1
    assert recycled_logs[0]["TradeID"] == 3


def test_wait_window_prevents_failure_from_skipped_trade():
    trades = pd.DataFrame(
        [
                _timed_trade_row(1, "2026-05-20 09:30", "2026-05-20 10:00", -1000),
                _timed_trade_row(2, "2026-05-20 10:15", "2026-05-20 10:20", -2000),
        ]
    )
    config = _transition_wait_config()
    config["evaluation"]["profit_target"] = 9999
    config["evaluation"]["max_drawdown"] = 1000
    config["simulation"]["fail_transition_wait_minutes"] = 60

    results = simulate_funding(trades, config)
    recycled_eval = [account for account in results["accounts"] if account.account_id == 2][0]

    assert recycled_eval.status == "ACTIVE"
    assert recycled_eval.trades_count == 0
    assert recycled_eval.pnl == 0


def test_transition_wait_boundary_trade_is_applied():
    trades = pd.DataFrame(
        [
                _timed_trade_row(1, "2026-05-20 09:30", "2026-05-20 10:00", -1000),
                _timed_trade_row(2, "2026-05-20 10:30", "2026-05-20 10:35", 100),
        ]
    )
    config = _transition_wait_config()
    config["evaluation"]["profit_target"] = 9999
    config["evaluation"]["max_drawdown"] = 1000
    config["simulation"]["fail_transition_wait_minutes"] = 30

    results = simulate_funding(trades, config)
    recycled_eval = [account for account in results["accounts"] if account.account_id == 2][0]

    assert recycled_eval.earliest_trade_time == pd.Timestamp("2026-05-20 10:30")
    assert recycled_eval.trades_count == 1
    assert recycled_eval.pnl == 100


def test_simulate_funding_can_start_directly_with_funded_account():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 500,
            },
            {
                "TradeID": 2,
                "EntryTime": datetime(2026, 5, 21, 9, 30),
                "ExitTime": datetime(2026, 5, 21, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 600,
            },
        ]
    )
    config = {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 1000,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
    }

    results = simulate_funding(trades, config)

    assert all(account.phase != "EVALUATION" for account in results["accounts"])
    assert len(results["accounts"]) == 1
    assert results["accounts"][0].phase == "FUNDED"
    assert results["accounts"][0].trades_count == 2
    assert len(results["trade_log"]) == 2
    assert len(results["payouts"]) == 1
    assert all(event["type"] != "EVALUATION_COST" for event in results["business_events"])


def test_simulate_funding_blocks_funded_payout_when_consistency_fails():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 5000,
            },
        ]
    )
    config = {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 1000,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
        "metadata": {
            "funded_consistency_enabled": True,
            "funded_consistency_percent": 0.4,
        },
    }

    results = simulate_funding(trades, config)

    assert results["accounts"][0].status == "ACTIVE"
    assert len(results["payouts"]) == 0
    assert results["trade_log"][0]["StatusAfterTrade"] == "ACTIVE"
    assert "FUNDED_PAYOUT_TRIGGER_REACHED" in results["trade_log"][0]["StatusReason"]
    assert (
        "Funded consistency rule not satisfied"
        in results["trade_log"][0]["StatusReason"]
    )


def test_simulate_funding_logs_winning_days_payout_block():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 5000,
            },
        ]
    )
    config = {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 1000,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
        "metadata": {
            "minimum_winning_days": 2,
            "winning_day_threshold": 150,
        },
    }

    results = simulate_funding(trades, config)

    assert results["accounts"][0].status == "ACTIVE"
    assert len(results["payouts"]) == 0
    assert "FUNDED_PAYOUT_TRIGGER_REACHED" in results["trade_log"][0]["StatusReason"]
    assert (
        "Winning days requirement not satisfied: 1/2"
        in results["trade_log"][0]["StatusReason"]
    )


def test_simulate_funding_processes_tiered_funded_payouts():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 5000,
            },
            {
                "TradeID": 2,
                "EntryTime": datetime(2026, 5, 21, 9, 30),
                "ExitTime": datetime(2026, 5, 21, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 3000,
            },
        ]
    )
    config = {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 1000,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
        "metadata": {
            "payout_tiers": {
                "1": 1500,
                "2": 2000,
                "3": 2500,
                "4_plus": 3000,
            },
        },
    }

    results = simulate_funding(trades, config)

    assert [payout.gross_payout for payout in results["payouts"]] == [1500, 2000]


def test_simulate_funding_logs_daily_continuity_payout_block():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 3000,
            },
        ]
    )
    config = {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 0,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
        "metadata": {
            "daily_payouts": True,
            "payout_cap": 1000,
            "minimum_payout": 250,
            "buffer_amount": 2100,
        },
    }

    results = simulate_funding(trades, config)

    assert len(results["payouts"]) == 0
    assert results["trade_log"][0]["StatusReason"] == "Daily continuity rule not satisfied"


def test_simulate_funding_processes_daily_continuity_payout_amount():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 3100,
            },
        ]
    )
    config = {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 2000,
            "payout_trigger_profit": 999999,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
        "metadata": {
            "daily_payouts": True,
            "payout_cap": 1000,
            "minimum_payout": 250,
            "buffer_amount": 2100,
        },
    }

    results = simulate_funding(trades, config)

    assert [payout.gross_payout for payout in results["payouts"]] == [1000]


def test_simulate_funding_updates_eod_drawdown_floor_on_day_change():
    trades = pd.DataFrame(
        [
            {
                "TradeID": 1,
                "EntryTime": datetime(2026, 5, 20, 9, 30),
                "ExitTime": datetime(2026, 5, 20, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": 1000,
            },
            {
                "TradeID": 2,
                "EntryTime": datetime(2026, 5, 21, 9, 30),
                "ExitTime": datetime(2026, 5, 21, 10, 0),
                "Symbol": "NQ",
                "Direction": "Long",
                "Quantity": 1,
                "NetPnL": -100,
            },
        ]
    )
    config = {
        "evaluation": {
            "enabled": False,
            "account_size": 50000,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 999999,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
        "metadata": {
            "drawdown_type": "EOD trailing max drawdown",
        },
    }

    results = simulate_funding(trades, config)
    account = results["accounts"][0]

    assert account.eod_high_pnl == 1000
    assert account.trailing_drawdown_floor == -1000
    assert account.drawdown_locked is False


def test_simulate_funding_routes_phase_profile_trades_to_evaluation_only():
    trades = pd.DataFrame(
        [
            _trade_row(1, 100, "EVALUATION"),
            _trade_row(2, 999, "FUNDED"),
        ]
    )
    config = _simple_evaluation_config()

    results = simulate_funding(trades, config)
    evaluation_account = results["accounts"][0]

    assert evaluation_account.trades_count == 1
    assert evaluation_account.pnl == 100
    assert len(results["trade_log"]) == 1


def test_simulate_funding_clips_trade_at_evaluation_target():
    trades = pd.DataFrame(
        [
            _trade_row(1, 2850, None),
            _trade_row(2, 300, None),
        ]
    )
    config = _simple_evaluation_config()
    config["evaluation"]["profit_target"] = 3000
    config["simulation"]["continue_after_pass"] = False

    results = simulate_funding(trades, config)
    evaluation_account = results["accounts"][0]
    clipped_log = results["trade_log"][1]

    assert evaluation_account.status == "PASSED"
    assert evaluation_account.pnl == 3000
    assert clipped_log["OriginalNetPnL"] == 300
    assert clipped_log["AppliedNetPnL"] == 150
    assert clipped_log["AccountAwareExitReason"] == "EVALUATION_TARGET_REACHED"
    assert clipped_log["AccountAwareExitApplied"] is True


def test_simulate_funding_clips_trade_at_daily_loss():
    trades = pd.DataFrame(
        [
            _trade_row(1, -900, None),
            _trade_row(2, -300, None),
        ]
    )
    config = _simple_straight_to_funded_config()
    config["funded"]["max_daily_loss"] = 1000
    config["funded"]["max_drawdown"] = 5000

    results = simulate_funding(trades, config)
    funded_account = results["accounts"][0]
    clipped_log = results["trade_log"][1]

    assert funded_account.pnl == -1000
    assert clipped_log["OriginalNetPnL"] == -300
    assert clipped_log["AppliedNetPnL"] == -100
    assert clipped_log["AccountAwareExitReason"] == "ACCOUNT_DAILY_LOSS"


def test_simulate_funding_straight_to_funded_consumes_funded_phase_profile():
    trades = pd.DataFrame(
        [
            _trade_row(1, 1000, "EVALUATION"),
            _trade_row(2, 600, "FUNDED"),
        ]
    )
    config = _simple_straight_to_funded_config()

    results = simulate_funding(trades, config)
    funded_account = results["accounts"][0]

    assert funded_account.trades_count == 1
    assert funded_account.pnl == 600
    assert len(results["trade_log"]) == 1


def test_simulate_funding_without_phase_profile_keeps_old_behavior():
    trades = pd.DataFrame(
        [
            _trade_row(1, 1000, None),
            _trade_row(2, 600, None),
        ]
    )
    config = _simple_straight_to_funded_config()

    results = simulate_funding(trades, config)
    funded_account = results["accounts"][0]

    assert funded_account.trades_count == 2
    assert funded_account.pnl == 1600


def _trade_row(trade_id: int, net_pnl: float, phase_profile: str | None) -> dict:
    row = {
        "TradeID": trade_id,
        "EntryTime": datetime(2026, 5, 20, 9, 30),
        "ExitTime": datetime(2026, 5, 20, 10, trade_id),
        "Symbol": "NQ",
        "Direction": "Long",
        "Quantity": 1,
        "NetPnL": net_pnl,
    }
    if phase_profile is not None:
        row["PhaseProfile"] = phase_profile
    return row


def _simple_evaluation_config() -> dict:
    return {
        "evaluation": {
            "enabled": True,
            "evaluation_cost": 100,
            "profit_target": 999999,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_trading_days": 1,
            "daily_profit_cap": None,
            "consistency_enabled": False,
            "consistency_percent": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 999999,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
    }


def _simple_straight_to_funded_config() -> dict:
    return {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 2000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 1000,
            "payout_trigger_profit": 999999,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
    }
