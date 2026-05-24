from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class StrategySignal:
    signal_time: Any
    direction: str
    reason: str | None = None


class BaseStrategy:
    name = "BaseStrategy"

    def generate_signals(self, ohlc: pd.DataFrame) -> list[StrategySignal]:
        raise NotImplementedError
