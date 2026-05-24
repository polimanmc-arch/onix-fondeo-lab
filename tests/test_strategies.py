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


def test_stochastic_cross_mode_generates_long_signal():
    ohlc = _stoch_ohlc([50, 50, 0, 30])
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
    assert signals[0].reason == "stoch_cross_long"
    assert signals[0].signal_time == pd.Timestamp("2026-05-20 09:33:00")


def test_stochastic_cross_mode_generates_short_signal():
    ohlc = _stoch_ohlc([50, 50, 100, 70])
    strategy = StochasticLevelStrategy(
        k_period=3,
        d_period=2,
        oversold_level=20,
        overbought_level=80,
        allow_long=False,
        allow_short=True,
    )

    signals = strategy.generate_signals(ohlc)

    assert len(signals) == 1
    assert signals[0].direction == "Short"
    assert signals[0].reason == "stoch_cross_short"
    assert signals[0].signal_time == pd.Timestamp("2026-05-20 09:33:00")


def test_stochastic_zone_mode_repeats_signals_but_respects_cooldown():
    ohlc = _stoch_ohlc([50, 50, 10, 10, 10, 10, 10])
    no_cooldown = StochasticLevelStrategy(
        k_period=3,
        d_period=2,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        signal_mode="zone",
        cooldown_bars=0,
    )
    with_cooldown = StochasticLevelStrategy(
        k_period=3,
        d_period=2,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        signal_mode="zone",
        cooldown_bars=2,
    )

    repeated_signals = no_cooldown.generate_signals(ohlc)
    cooled_signals = with_cooldown.generate_signals(ohlc)

    assert [signal.reason for signal in repeated_signals] == [
        "stoch_zone_long",
        "stoch_zone_long",
        "stoch_zone_long",
        "stoch_zone_long",
    ]
    assert len(cooled_signals) == 2


def test_stochastic_d_confirmation_blocks_signal_when_relationship_fails():
    ohlc = _stoch_ohlc([50, 10])
    strategy = StochasticLevelStrategy(
        k_period=1,
        d_period=2,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        signal_mode="zone",
        use_d_confirmation=True,
    )

    signals = strategy.generate_signals(ohlc)

    assert signals == []


def test_stochastic_min_k_d_gap_filters_small_confirmation_gap():
    ohlc = _stoch_ohlc([50, 50, 0, 30])
    loose_gap = StochasticLevelStrategy(
        k_period=3,
        d_period=2,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        use_d_confirmation=True,
        min_k_d_gap=15,
    )
    strict_gap = StochasticLevelStrategy(
        k_period=3,
        d_period=2,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        use_d_confirmation=True,
        min_k_d_gap=16,
    )

    assert len(loose_gap.generate_signals(ohlc)) == 1
    assert strict_gap.generate_signals(ohlc) == []


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


def _stoch_ohlc(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DateTime": pd.date_range(
                "2026-05-20 09:30:00",
                periods=len(closes),
                freq="min",
            ),
            "Open": closes,
            "High": [100] * len(closes),
            "Low": [0] * len(closes),
            "Close": closes,
        }
    )
