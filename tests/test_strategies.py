import pandas as pd

from onix_fondeo.strategies.random_entry import RandomEntryStrategy
from onix_fondeo.strategies.stochastic_level import StochasticLevelStrategy


def test_random_entry_strategy_is_reproducible_with_seed():
    ohlc = _sample_ohlc(rows=20)
    first = RandomEntryStrategy(probability=0.5, seed=123).generate_signals(ohlc)
    second = RandomEntryStrategy(probability=0.5, seed=123).generate_signals(ohlc)

    assert first == second


def test_random_entry_strategy_respects_time_window():
    ohlc = _sample_ohlc(rows=5)
    strategy = RandomEntryStrategy(
        probability=1.0,
        allow_long=True,
        allow_short=False,
        seed=42,
        start_time="09:31",
        end_time="09:32",
    )

    signals = strategy.generate_signals(ohlc)

    assert [signal.signal_time.time().strftime("%H:%M") for signal in signals] == [
        "09:31",
        "09:32",
    ]
    assert all(signal.direction == "Long" for signal in signals)


def test_stochastic_level_strategy_generates_expected_long_signal():
    ohlc = pd.DataFrame(
        {
            "DateTime": pd.date_range("2026-05-20 09:30:00", periods=4, freq="min"),
            "Open": [5, 5, 1, 3],
            "High": [10, 10, 10, 10],
            "Low": [0, 0, 0, 0],
            "Close": [5, 5, 0, 3],
        }
    )
    strategy = StochasticLevelStrategy(
        k_period=3,
        d_period=2,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
    )

    signals = strategy.generate_signals(ohlc)

    assert len(signals) == 1
    assert signals[0].direction == "Long"
    assert signals[0].signal_time == pd.Timestamp("2026-05-20 09:33:00")


def _sample_ohlc(rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DateTime": pd.date_range("2026-05-20 09:30:00", periods=rows, freq="min"),
            "Open": [100.0] * rows,
            "High": [101.0] * rows,
            "Low": [99.0] * rows,
            "Close": [100.5] * rows,
        }
    )
