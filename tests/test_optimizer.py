import pandas as pd

import onix_fondeo.optimizer as optimizer
from onix_fondeo.optimizer import (
    build_stochastic_parameter_grid,
    filter_ohlc_by_date,
    run_stochastic_optimization,
)
from onix_fondeo.report import export_optimization_results


def test_build_stochastic_parameter_grid_returns_non_empty_list():
    grid = build_stochastic_parameter_grid()

    assert grid


def test_fast_stochastic_parameter_grid_is_smaller_than_full_grid():
    fast_grid = build_stochastic_parameter_grid("fast")
    full_grid = build_stochastic_parameter_grid("full")

    assert len(fast_grid) < len(full_grid)


def test_invalid_stochastic_parameter_grid_name_raises_value_error():
    try:
        build_stochastic_parameter_grid("huge")
    except ValueError as error:
        assert "Unknown optimization grid" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid grid name")


def test_stochastic_parameter_grid_contains_required_keys():
    row = build_stochastic_parameter_grid()[0]

    assert {
        "stoch_k_period",
        "stoch_d_period",
        "oversold",
        "overbought",
        "signal_mode",
        "use_d_confirmation",
        "min_k_d_gap",
        "cooldown_bars",
        "stop_loss_points",
        "take_profit_points",
    }.issubset(row)


def test_run_stochastic_optimization_returns_rows():
    rows = run_stochastic_optimization(
        ohlc=_sample_ohlc(),
        presets=[_preset()],
        max_runs=1,
        workers=1,
    )

    assert len(rows) == 1
    assert rows[0]["preset_id"] == "test_preset"
    assert rows[0]["strategy"] == "stochastic"
    assert "net_business_pnl" in rows[0]


def test_run_stochastic_optimization_max_runs_limits_parameter_sets():
    rows = run_stochastic_optimization(
        ohlc=_sample_ohlc(),
        presets=[_preset(), _preset("test_preset_b")],
        max_runs=2,
    )

    assert len(rows) == 4
    assert {row["run_id"] for row in rows} == {1, 2}


def test_run_stochastic_optimization_with_parallel_workers_returns_rows():
    rows = run_stochastic_optimization(
        ohlc=_sample_ohlc(),
        presets=[_preset()],
        max_runs=2,
        workers=2,
    )

    assert len(rows) == 2
    assert [row["run_id"] for row in rows] == [1, 2]


def test_run_stochastic_optimization_can_include_bankroll_fields():
    rows = run_stochastic_optimization(
        ohlc=_sample_ohlc(),
        presets=[_preset()],
        base_args={"initial_bankroll": 3000},
        max_runs=1,
    )

    assert "final_bankroll" in rows[0]
    assert "bankroll_ruined" in rows[0]


def test_filter_ohlc_by_date_limits_rows_without_mutating_source():
    ohlc = pd.DataFrame(
        {
            "DateTime": pd.to_datetime(
                [
                    "2026-03-11 09:30:00",
                    "2026-03-12 09:30:00",
                    "2026-03-19 09:30:00",
                    "2026-03-20 09:30:00",
                ]
            ),
            "Open": [1, 2, 3, 4],
        }
    )

    filtered = filter_ohlc_by_date(
        ohlc,
        start_date="2026-03-12",
        end_date="2026-03-19",
    )

    assert len(filtered) == 2
    assert len(ohlc) == 4
    assert filtered.iloc[0]["DateTime"] == pd.Timestamp("2026-03-12 09:30:00")


def test_export_optimization_results_creates_csv_and_html(tmp_path):
    rows = run_stochastic_optimization(
        ohlc=_sample_ohlc(),
        presets=[_preset()],
        max_runs=1,
    )

    files = export_optimization_results(rows, output_dir=tmp_path)

    assert files["optimization_results"].exists()
    assert files["optimization_report"].exists()
    assert "test_preset" in files["optimization_results"].read_text(encoding="utf-8")
    assert (
        "Onix Fondeo Lab - Strategy Optimization Report"
        in files["optimization_report"].read_text(encoding="utf-8")
    )


def test_run_stochastic_optimization_passes_force_close_time(monkeypatch):
    captured = {}

    def fake_backtest_strategy(**kwargs):
        captured["force_close_time"] = kwargs["force_close_time"]
        return pd.DataFrame(
            columns=[
                "TradeID",
                "EntryTime",
                "ExitTime",
                "Symbol",
                "Direction",
                "Quantity",
                "EntryPrice",
                "ExitPrice",
                "GrossPnL",
                "Commission",
                "NetPnL",
                "ExitReason",
                "StrategyName",
            ]
        )

    monkeypatch.setattr(optimizer, "backtest_strategy", fake_backtest_strategy)

    run_stochastic_optimization(
        ohlc=_sample_ohlc(),
        presets=[_preset()],
        base_args={"force_close_time": "15:55"},
        max_runs=1,
    )

    assert captured["force_close_time"] == "15:55"


def _sample_ohlc() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DateTime": pd.date_range("2026-05-20 09:30:00", periods=20, freq="min"),
            "Open": [100 + index for index in range(20)],
            "High": [102 + index for index in range(20)],
            "Low": [98 + index for index in range(20)],
            "Close": [100 + index for index in range(20)],
        }
    )


def _preset(preset_id: str = "test_preset") -> dict:
    return {
        "preset_id": preset_id,
        "company": "TestCo",
        "plan": "Test Plan",
        "account_name": "Test Account",
        "account_size": 50000,
        "evaluation": {
            "enabled": True,
            "account_size": 50000,
            "evaluation_cost": 100,
            "profit_target": 1000,
            "max_drawdown": 1000,
            "max_daily_loss": None,
            "minimum_trading_days": 1,
            "daily_profit_cap": None,
            "consistency_enabled": False,
            "consistency_percent": None,
        },
        "funded": {
            "enabled": True,
            "max_drawdown": 1000,
            "max_daily_loss": None,
            "minimum_withdrawable_profit": 500,
            "payout_trigger_profit": 1000,
            "profit_split": 0.9,
            "reset_after_payout": False,
        },
        "simulation": {
            "max_accounts": 10,
            "recycle_failed_accounts": True,
            "continue_after_pass": True,
        },
        "metadata": {},
    }
