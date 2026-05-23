from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class Trade:
    trade_id: int
    entry_time: Any
    exit_time: Any
    symbol: str
    direction: str
    quantity: float
    net_pnl: float


@dataclass
class Payout:
    account_id: int
    payout_time: Any
    gross_payout: float
    net_payout: float


@dataclass
class Account:
    account_id: int
    phase: str
    status: str = "ACTIVE"
    pnl: float = 0.0
    high_watermark: float = 0.0
    trading_days: set[date] = field(default_factory=set)
    daily_pnl: dict[date, float] = field(default_factory=dict)
    trades_count: int = 0
    started_at: Optional[Any] = None
    ended_at: Optional[Any] = None
    result_reason: Optional[str] = None
    payouts: list[Payout] = field(default_factory=list)

    def apply_trade(
        self,
        trade: Trade,
        daily_profit_cap: Optional[float] = None,
    ) -> float:
        trade_day = _as_trade_day(trade.exit_time or trade.entry_time)
        applied_pnl = _apply_daily_profit_cap(
            current_daily_pnl=self.daily_pnl.get(trade_day, 0.0),
            trade_pnl=trade.net_pnl,
            daily_profit_cap=daily_profit_cap,
        )

        self.pnl += applied_pnl
        self.high_watermark = max(self.high_watermark, self.pnl)
        self.daily_pnl[trade_day] = self.daily_pnl.get(trade_day, 0.0) + applied_pnl
        self.trading_days.add(trade_day)
        self.trades_count += 1

        if self.started_at is None:
            self.started_at = trade.entry_time

        return applied_pnl

    def register_payout(
        self,
        payout_time: Any,
        gross_payout: float,
        profit_split: float,
    ) -> Payout:
        net_payout = gross_payout * profit_split
        payout = Payout(
            account_id=self.account_id,
            payout_time=payout_time,
            gross_payout=gross_payout,
            net_payout=net_payout,
        )
        self.payouts.append(payout)
        return payout


def _as_trade_day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    raise TypeError(f"Unsupported trade time value: {value!r}")


def _apply_daily_profit_cap(
    current_daily_pnl: float,
    trade_pnl: float,
    daily_profit_cap: Optional[float],
) -> float:
    if daily_profit_cap is None or trade_pnl <= 0:
        return trade_pnl

    remaining_daily_profit = daily_profit_cap - current_daily_pnl
    return max(0.0, min(trade_pnl, remaining_daily_profit))
