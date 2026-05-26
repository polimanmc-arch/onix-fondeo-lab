from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from onix_fondeo.models import Account, Payout, Trade
from onix_fondeo.rules import (
    check_evaluation_status,
    check_funded_status,
    get_account_size_from_config,
    process_funded_payout,
    update_eod_trailing_drawdown,
)


def row_to_trade(row: Any) -> Trade:
    return Trade(
        trade_id=int(row["TradeID"]),
        entry_time=row["EntryTime"],
        exit_time=row["ExitTime"],
        symbol=str(row["Symbol"]),
        direction=str(row["Direction"]),
        quantity=float(row["Quantity"]),
        net_pnl=float(row["NetPnL"]),
    )


def simulate_funding(trades_df: Any, config: dict[str, Any]) -> dict[str, Any]:
    evaluation_rules = config["evaluation"]
    funded_rules = config["funded"]
    simulation_settings = config["simulation"]
    metadata = config.get("metadata", {})

    accounts: list[Account] = []
    trade_log: list[dict[str, Any]] = []
    payouts: list[Payout] = []
    business_events: list[dict[str, Any]] = []
    active_funded_accounts: list[Account] = []

    next_account_id = 1

    # Evaluation flow: start with one evaluation account and pay its cost if known.
    if evaluation_rules.get("enabled", True):
        active_eval = _open_evaluation_account(
            account_id=next_account_id,
            opened_at=None,
            evaluation_cost=evaluation_rules.get("evaluation_cost"),
            accounts=accounts,
            business_events=business_events,
        )
        next_account_id += 1
    else:
        active_eval = None
        # Straight-to-funded flow: skip evaluation and start with one funded account.
        funded_account = Account(
            account_id=next_account_id,
            phase="FUNDED",
            started_at=None,
        )
        accounts.append(funded_account)
        active_funded_accounts.append(funded_account)
        _register_account_cost(
            account_id=funded_account.account_id,
            opened_at=None,
            account_cost=(
                funded_rules.get("account_cost")
                or evaluation_rules.get("evaluation_cost")
            ),
            business_events=business_events,
        )
        next_account_id += 1

    current_trade_day = None

    for _, row in trades_df.iterrows():
        phase_profile = _phase_profile_for_row(row)
        trade = row_to_trade(row)
        trade_day = _trade_day(trade)
        if current_trade_day is not None and trade_day != current_trade_day:
            _finalize_eod_for_active_accounts(accounts, config)
        current_trade_day = trade_day

        funded_accounts_for_trade = list(active_funded_accounts)

        if (
            active_eval is not None
            and active_eval.status == "ACTIVE"
            and _trade_matches_account_phase(phase_profile, active_eval.phase)
        ):
            applied_pnl = active_eval.apply_trade(
                trade,
                daily_profit_cap=evaluation_rules.get("daily_profit_cap"),
            )
            status, reason = check_evaluation_status(
                active_eval,
                evaluation_rules,
                metadata,
            )

            if status in {"PASSED", "FAILED"}:
                active_eval.status = status
                active_eval.ended_at = trade.exit_time
                active_eval.result_reason = reason

            trade_log.append(
                _trade_log_row(active_eval, trade, applied_pnl, status, reason)
            )

            if status == "PASSED":
                funded_account = Account(
                    account_id=active_eval.account_id,
                    phase="FUNDED",
                    started_at=trade.exit_time,
                )
                accounts.append(funded_account)
                active_funded_accounts.append(funded_account)

                active_eval = _maybe_open_next_evaluation(
                    should_open=simulation_settings.get("continue_after_pass", False),
                    next_account_id=next_account_id,
                    opened_at=trade.exit_time,
                    evaluation_cost=evaluation_rules.get("evaluation_cost"),
                    max_accounts=simulation_settings.get("max_accounts"),
                    accounts=accounts,
                    business_events=business_events,
                )
                if active_eval is not None:
                    next_account_id += 1

            elif status == "FAILED":
                active_eval = _maybe_open_next_evaluation(
                    should_open=simulation_settings.get("recycle_failed_accounts", False),
                    next_account_id=next_account_id,
                    opened_at=trade.exit_time,
                    evaluation_cost=evaluation_rules.get("evaluation_cost"),
                    max_accounts=simulation_settings.get("max_accounts"),
                    accounts=accounts,
                    business_events=business_events,
                )
                if active_eval is not None:
                    next_account_id += 1

        for funded_account in funded_accounts_for_trade:
            if funded_account.status != "ACTIVE":
                continue
            if not _trade_matches_account_phase(phase_profile, funded_account.phase):
                continue

            applied_pnl = funded_account.apply_trade(trade)
            status, reason = check_funded_status(
                funded_account,
                funded_rules,
                metadata,
            )

            if status == "FAILED":
                funded_account.status = "FAILED"
                funded_account.ended_at = trade.exit_time
                funded_account.result_reason = reason
                active_funded_accounts.remove(funded_account)

            elif status == "PAYOUT_ELIGIBLE":
                payout = process_funded_payout(
                    funded_account,
                    payout_time=trade.exit_time,
                    funded_rules=funded_rules,
                    metadata=metadata,
                )
                payouts.append(payout)
                business_events.append(
                    {
                        "time": trade.exit_time,
                        "type": "PAYOUT",
                        "amount": payout.net_payout,
                        "account_id": funded_account.account_id,
                    }
                )

            trade_log.append(
                _trade_log_row(funded_account, trade, applied_pnl, status, reason)
            )

    if current_trade_day is not None:
        _finalize_eod_for_active_accounts(accounts, config)

    return {
        "accounts": accounts,
        "trade_log": trade_log,
        "payouts": payouts,
        "business_events": business_events,
    }


def _phase_profile_for_row(row: Any) -> str | None:
    if "PhaseProfile" not in row:
        return None
    value = row.get("PhaseProfile")
    if value is None or pd.isna(value):
        return None
    return str(value)


def _trade_matches_account_phase(
    phase_profile: str | None,
    account_phase: str,
) -> bool:
    if phase_profile is None:
        return True
    return phase_profile == account_phase


def _trade_day(trade: Trade) -> Any:
    trade_time = trade.exit_time or trade.entry_time
    if hasattr(trade_time, "date"):
        return trade_time.date()
    return trade_time


def _finalize_eod_for_active_accounts(
    accounts: list[Account],
    config: dict[str, Any],
) -> None:
    metadata = config.get("metadata", {})
    account_size = get_account_size_from_config(config)

    for account in accounts:
        if account.status != "ACTIVE":
            continue

        if account.phase == "EVALUATION":
            max_drawdown = config["evaluation"].get("max_drawdown")
        elif account.phase == "FUNDED":
            max_drawdown = config["funded"].get("max_drawdown")
        else:
            max_drawdown = None

        if max_drawdown is None:
            continue

        update_eod_trailing_drawdown(
            account,
            max_drawdown=max_drawdown,
            metadata=metadata,
            account_size=account_size,
        )


def _open_evaluation_account(
    account_id: int,
    opened_at: Any,
    evaluation_cost: Optional[float],
    accounts: list[Account],
    business_events: list[dict[str, Any]],
) -> Account:
    account = Account(account_id=account_id, phase="EVALUATION", started_at=opened_at)
    accounts.append(account)
    _register_account_cost(
        account_id=account_id,
        opened_at=opened_at,
        account_cost=evaluation_cost,
        business_events=business_events,
    )
    return account


def _register_account_cost(
    account_id: int,
    opened_at: Any,
    account_cost: Optional[float],
    business_events: list[dict[str, Any]],
) -> None:
    if account_cost is None:
        return

    business_events.append(
        {
            "time": opened_at,
            "type": "EVALUATION_COST",
            "amount": -account_cost,
            "account_id": account_id,
        }
    )


def _maybe_open_next_evaluation(
    should_open: bool,
    next_account_id: int,
    opened_at: Any,
    evaluation_cost: Optional[float],
    max_accounts: Optional[int],
    accounts: list[Account],
    business_events: list[dict[str, Any]],
) -> Optional[Account]:
    if not should_open:
        return None
    if max_accounts is not None and next_account_id > max_accounts:
        return None

    return _open_evaluation_account(
        account_id=next_account_id,
        opened_at=opened_at,
        evaluation_cost=evaluation_cost,
        accounts=accounts,
        business_events=business_events,
    )


def _trade_log_row(
    account: Account,
    trade: Trade,
    applied_pnl: float,
    status_after_trade: str,
    status_reason: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "AccountID": account.account_id,
        "Phase": account.phase,
        "TradeID": trade.trade_id,
        "TradeTime": trade.exit_time,
        "OriginalPnL": trade.net_pnl,
        "AppliedPnL": applied_pnl,
        "AccountPnL": account.pnl,
        "StatusAfterTrade": status_after_trade,
        "StatusReason": status_reason,
        "DrawdownFloor": account.trailing_drawdown_floor,
        "EODHighPnL": account.eod_high_pnl,
        "DrawdownLocked": account.drawdown_locked,
    }
