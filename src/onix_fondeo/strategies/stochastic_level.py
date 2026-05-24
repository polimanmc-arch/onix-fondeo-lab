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
    ) -> None:
        self.k_period = k_period
        self.d_period = d_period
        self.oversold_level = oversold_level
        self.overbought_level = overbought_level
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.start_time = start_time
        self.end_time = end_time

    def generate_signals(self, ohlc: pd.DataFrame) -> list[StrategySignal]:
        data = ohlc.copy()
        lowest_low = data["Low"].rolling(self.k_period).min()
        highest_high = data["High"].rolling(self.k_period).max()
        price_range = highest_high - lowest_low
        data["PercentK"] = 100 * (data["Close"] - lowest_low) / price_range
        data.loc[price_range == 0, "PercentK"] = 0.0
        data["PercentD"] = data["PercentK"].rolling(self.d_period).mean()

        signals = []
        for index in range(1, len(data)):
            row = data.iloc[index]
            previous_k = data.iloc[index - 1]["PercentK"]
            current_k = row["PercentK"]

            if pd.isna(previous_k) or pd.isna(current_k):
                continue
            if not _is_inside_time_window(row["DateTime"], self.start_time, self.end_time):
                continue

            if (
                self.allow_long
                and previous_k <= self.oversold_level
                and current_k > self.oversold_level
            ):
                signals.append(
                    StrategySignal(
                        signal_time=row["DateTime"],
                        direction="Long",
                        reason="Stochastic crossed above oversold",
                    )
                )

            if (
                self.allow_short
                and previous_k >= self.overbought_level
                and current_k < self.overbought_level
            ):
                signals.append(
                    StrategySignal(
                        signal_time=row["DateTime"],
                        direction="Short",
                        reason="Stochastic crossed below overbought",
                    )
                )

        return signals
