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
        smooth=1,
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
        smooth=1,
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
        smooth=1,
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
        smooth=1,
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


def test_stochastic_d_cross_mode_uses_d_line_exit_from_oversold():
    ohlc = _stoch_ohlc([10, 30, 30])
    strategy = StochasticLevelStrategy(
        k_period=1,
        d_period=2,
        smooth=1,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        signal_mode="d_cross",
    )

    signals = strategy.generate_signals(ohlc)

    assert len(signals) == 1
    assert signals[0].direction == "Long"
    assert signals[0].reason == "stoch_d_cross_long"
    assert signals[0].signal_time == pd.Timestamp("2026-05-20 09:32:00")


def test_stochastic_d_cross_mode_ignores_k_cross_without_d_cross():
    ohlc = _stoch_ohlc([10, 30])
    strategy = StochasticLevelStrategy(
        k_period=1,
        d_period=2,
        smooth=1,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        signal_mode="d_cross",
    )

    signals = strategy.generate_signals(ohlc)

    assert signals == []


def test_stochastic_d_confirmation_blocks_signal_when_relationship_fails():
    ohlc = _stoch_ohlc([50, 10])
    strategy = StochasticLevelStrategy(
        k_period=1,
        d_period=2,
        smooth=1,
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
        smooth=1,
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
        smooth=1,
        oversold_level=20,
        overbought_level=80,
        allow_long=True,
        allow_short=False,
        use_d_confirmation=True,
        min_k_d_gap=16,
    )

    assert len(loose_gap.generate_signals(ohlc)) == 1
    assert strict_gap.generate_signals(ohlc) == []


def test_stochastic_matches_ninjatrader_smoothing_chain():
    ohlc = _stoch_ohlc([10, 20, 30, 40, 50, 60])
    strategy = StochasticLevelStrategy(period_k=3, smooth=2, period_d=2)

    fast_k, percent_k, percent_d = strategy.calculate_stochastics(ohlc)

    assert fast_k.iloc[2] == 30
    assert fast_k.iloc[3] == 40
    assert percent_k.iloc[3] == 35
    assert percent_k.iloc[4] == 45
    assert percent_d.iloc[4] == 40


def test_stochastic_den_zero_uses_50_then_previous_fast_k():
    ohlc = pd.DataFrame(
        {
            "DateTime": pd.date_range("2026-05-20 09:30:00", periods=4, freq="min"),
            "Open": [100, 100, 100, 100],
            "High": [100, 100, 100, 100],
            "Low": [100, 100, 100, 100],
            "Close": [100, 100, 100, 100],
        }
    )
    strategy = StochasticLevelStrategy(period_k=2, smooth=1, period_d=1)

    fast_k, percent_k, percent_d = strategy.calculate_stochastics(ohlc)

    assert fast_k.iloc[1] == 50
    assert fast_k.iloc[2] == 50
    assert percent_k.iloc[2] == 50
    assert percent_d.iloc[2] == 50


def test_stochastic_fast_k_is_clamped_between_0_and_100():
    ohlc = pd.DataFrame(
        {
            "DateTime": pd.date_range("2026-05-20 09:30:00", periods=4, freq="min"),
            "Open": [0, 0, 0, 0],
            "High": [100, 100, 100, 100],
            "Low": [0, 0, 0, 0],
            "Close": [50, 150, -50, 50],
        }
    )
    strategy = StochasticLevelStrategy(period_k=2, smooth=1, period_d=1)

    fast_k, _, _ = strategy.calculate_stochastics(ohlc)

    assert fast_k.iloc[1] == 100
    assert fast_k.iloc[2] == 0


def test_stochastic_backward_compatible_period_aliases():
    strategy = StochasticLevelStrategy(k_period=20, d_period=5)

    assert strategy.period_k == 20
    assert strategy.period_d == 5


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
