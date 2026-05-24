from __future__ import annotations

import random
from typing import Optional

import pandas as pd

from onix_fondeo.strategies.base import BaseStrategy, StrategySignal


class RandomEntryStrategy(BaseStrategy):
    name = "Random Entry"

    def __init__(
        self,
        probability: float = 0.005,
        allow_long: bool = True,
        allow_short: bool = True,
        seed: Optional[int] = 42,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> None:
        if not allow_long and not allow_short:
            raise ValueError("At least one direction must be enabled.")

        self.probability = probability
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.seed = seed
        self.start_time = start_time
        self.end_time = end_time

    def generate_signals(self, ohlc: pd.DataFrame) -> list[StrategySignal]:
        rng = random.Random(self.seed)
        signals = []

        for _, row in ohlc.iterrows():
            signal_time = row["DateTime"]
            if not _is_inside_time_window(signal_time, self.start_time, self.end_time):
                continue

            if rng.random() > self.probability:
                continue

            direction = self._choose_direction(rng)
            signals.append(
                StrategySignal(
                    signal_time=signal_time,
                    direction=direction,
                    reason="Random entry",
                )
            )

        return signals

    def _choose_direction(self, rng: random.Random) -> str:
        if self.allow_long and self.allow_short:
            return rng.choice(["Long", "Short"])
        if self.allow_long:
            return "Long"
        return "Short"


def _is_inside_time_window(
    value: object,
    start_time: Optional[str],
    end_time: Optional[str],
) -> bool:
    if start_time is None and end_time is None:
        return True

    value_time = pd.Timestamp(value).time()
    if start_time is not None and value_time < pd.Timestamp(start_time).time():
        return False
    if end_time is not None and value_time > pd.Timestamp(end_time).time():
        return False
    return True
