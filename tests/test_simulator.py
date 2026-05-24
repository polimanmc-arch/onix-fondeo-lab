from datetime import datetime

import pandas as pd

from onix_fondeo.simulator import simulate_funding


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
    assert (
        results["trade_log"][0]["StatusReason"]
        == "Funded consistency rule not satisfied"
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
    assert (
        results["trade_log"][0]["StatusReason"]
        == "Winning days requirement not satisfied: 1/2"
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
