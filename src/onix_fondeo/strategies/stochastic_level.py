from __future__ import annotations

from typing import Optional

import pandas as pd

from onix_fondeo.strategies.base import BaseStrategy, StrategySignal
from onix_fondeo.strategies.random_entry import _is_inside_time_window


class StochasticLevelStrategy(BaseStrategy):
    name = "Stochastic Level"

    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
        oversold_level: float = 20,
        overbought_level: float = 80,
        allow_long: bool = True,
        allow_short: bool = True,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        signal_mode: str = "cross",
        use_d_confirmation: bool = False,
        min_k_d_gap: float = 0.0,
        cooldown_bars: int = 0,
    ) -> None:
        if signal_mode not in {"cross", "zone"}:
            raise ValueError("signal_mode must be 'cross' or 'zone'.")

        self.k_period = k_period
        self.d_period = d_period
        self.oversold_level = oversold_level
        self.overbought_level = overbought_level
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.start_time = start_time
        self.end_time = end_time
        self.signal_mode = signal_mode
        self.use_d_confirmation = use_d_confirmation
        self.min_k_d_gap = min_k_d_gap
        self.cooldown_bars = cooldown_bars

    def generate_signals(self, ohlc: pd.DataFrame) -> list[StrategySignal]:
        data = ohlc.copy()
        lowest_low = data["Low"].rolling(self.k_period).min()
        highest_high = data["High"].rolling(self.k_period).max()
        price_range = highest_high - lowest_low
        data["PercentK"] = 100 * (data["Close"] - lowest_low) / price_range
        data.loc[price_range == 0, "PercentK"] = 0.0
        data["PercentD"] = data["PercentK"].rolling(self.d_period).mean()

        signals = []
        cooldown_remaining = 0
        for index in range(1, len(data)):
            row = data.iloc[index]
            previous_k = data.iloc[index - 1]["PercentK"]
            current_k = row["PercentK"]
            current_d = row["PercentD"]

            if pd.isna(previous_k) or pd.isna(current_k):
                continue
            if not _is_inside_time_window(row["DateTime"], self.start_time, self.end_time):
                continue
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
                continue

            signal = self._signal_for_bar(
                signal_time=row["DateTime"],
                previous_k=previous_k,
                current_k=current_k,
                current_d=current_d,
            )
            if signal is not None:
                signals.append(signal)
                cooldown_remaining = self.cooldown_bars

        return signals

    def _signal_for_bar(
        self,
        signal_time: object,
        previous_k: float,
        current_k: float,
        current_d: float,
    ) -> StrategySignal | None:
        if self._is_long_signal(previous_k, current_k) and self._has_d_confirmation(
            direction="Long",
            current_k=current_k,
            current_d=current_d,
        ):
            return StrategySignal(
                signal_time=signal_time,
                direction="Long",
                reason=f"stoch_{self.signal_mode}_long",
            )

        if self._is_short_signal(previous_k, current_k) and self._has_d_confirmation(
            direction="Short",
            current_k=current_k,
            current_d=current_d,
        ):
            return StrategySignal(
                signal_time=signal_time,
                direction="Short",
                reason=f"stoch_{self.signal_mode}_short",
            )

        return None

    def _is_long_signal(self, previous_k: float, current_k: float) -> bool:
        if not self.allow_long:
            return False
        if self.signal_mode == "cross":
            return previous_k <= self.oversold_level and current_k > self.oversold_level
        return current_k <= self.oversold_level

    def _is_short_signal(self, previous_k: float, current_k: float) -> bool:
        if not self.allow_short:
            return False
        if self.signal_mode == "cross":
            return previous_k >= self.overbought_level and current_k < self.overbought_level
        return current_k >= self.overbought_level

    def _has_d_confirmation(
        self,
        direction: str,
        current_k: float,
        current_d: float,
    ) -> bool:
        if not self.use_d_confirmation:
            return True
        if pd.isna(current_d):
            return False
        if direction == "Long":
            return current_k - current_d >= self.min_k_d_gap
        return current_d - current_k >= self.min_k_d_gap
