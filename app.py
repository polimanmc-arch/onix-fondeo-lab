from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from onix_fondeo.backtester import backtest_strategy
from onix_fondeo.bankroll import calculate_bankroll_curve
from onix_fondeo.loader import (
    config_from_preset,
    list_presets,
    load_preset,
    validate_preset_is_runnable,
)
from onix_fondeo.market_data import load_ohlc_data
from onix_fondeo.metrics import calculate_business_metrics
from onix_fondeo.risk_of_ruin import (
    estimate_required_bankroll,
    extract_account_net_outcomes,
    run_monte_carlo_ruin_simulation,
)
from onix_fondeo.simulator import simulate_funding
from onix_fondeo.strategy_metrics import calculate_strategy_metrics
from onix_fondeo.strategies.random_entry import RandomEntryStrategy
from onix_fondeo.strategies.stochastic_level import StochasticLevelStrategy
from onix_fondeo.streaks import calculate_streak_analysis


OUTPUT_DIR = Path("data/output")
DEFAULT_PRESET_COMPANY = "Lucid Trading"
DEFAULT_PRESET_PLAN = "LucidFlex"
DEFAULT_PRESET_ACCOUNT_SIZE = 50000


def main() -> None:
    st.set_page_config(page_title="Onix Fondeo Lab", layout="wide")
    st.title("Onix Fondeo Lab")
    st.caption("Funding account strategy analyzer")

    controls = sidebar_controls()

    if controls["run_analysis"]:
        try:
            run_analysis(controls)
        except Exception as error:
            st.error(f"Analysis failed: {error}")

    analysis_state = get_analysis_state()
    if analysis_state is None:
        st.info("Configure the sidebar and click Run Analysis.")
        return

    render_outputs_from_state(analysis_state)


def sidebar_controls() -> dict[str, Any]:
    with st.sidebar:
        st.header("Market Data")
        market_data_path = st.text_input(
            "OHLC CSV path",
            value="data/market_data/sample_NQ_1m.csv",
        )
        symbol = st.text_input("Symbol", value="NQ")
        point_value = st.number_input("Point value", min_value=0.0, value=20.0)

        st.header("Funding Preset")
        presets = list_presets()
        show_non_runnable = st.checkbox("Show non-runnable presets", value=False)
        filtered_presets = filter_presets_by_runnable(presets, show_non_runnable)
        selected_preset = select_funding_preset(filtered_presets)
        selected_preset_id = selected_preset["preset_id"]
        selected_preset_runnable = selected_preset["is_runnable"]
        render_selected_preset_info(selected_preset)
        comparison_enabled = st.checkbox("Compare multiple presets", value=False)
        comparison_preset_ids = []
        if comparison_enabled:
            runnable_presets = filter_presets_by_runnable(presets, show_non_runnable=False)
            comparison_options = {
                preset_option_label(preset): preset["preset_id"]
                for preset in runnable_presets
            }
            default_labels = [
                label
                for label, preset_id in comparison_options.items()
                if preset_id == selected_preset_id
            ]
            selected_comparison_labels = st.multiselect(
                "Presets to compare",
                options=list(comparison_options),
                default=default_labels,
                help="Uses the same generated trades for every selected runnable preset.",
            )
            comparison_preset_ids = [
                comparison_options[label] for label in selected_comparison_labels
            ]
            if len(comparison_preset_ids) < 2:
                st.caption("Select at least two presets for a meaningful comparison.")

        st.header("Strategy")
        strategy_name = st.selectbox(
            "Strategy",
            options=["random", "stochastic"],
            index=1,
        )
        strategy_params = _strategy_controls(strategy_name)

        st.header("Time Filters")
        strategy_start_time = st.text_input("Strategy start time", value="09:45")
        strategy_end_time = st.text_input("Strategy end time", value="16:00")
        force_close_time = st.text_input("Force close time", value="16:00")

        st.header("Risk Settings")
        contracts = st.number_input("Contracts", min_value=0.0, value=1.0)
        stop_loss_points = st.number_input("Stop loss points", min_value=0.0, value=70.0)
        take_profit_points = st.number_input(
            "Take profit points",
            min_value=0.0,
            value=50.0,
        )
        max_holding_minutes = st.number_input(
            "Max holding minutes",
            min_value=1,
            value=60,
            step=1,
        )

        st.header("Costs")
        commission_per_side = st.number_input(
            "Commission per side",
            min_value=0.0,
            value=0.0,
        )
        slippage_points = st.number_input("Slippage points", min_value=0.0, value=0.0)
        spread_points = st.number_input("Spread points", min_value=0.0, value=0.0)

        st.header("Bankroll / Risk")
        bankroll = st.number_input("Bankroll", min_value=0.0, value=3000.0)
        monte_carlo_runs = st.number_input(
            "Monte Carlo runs",
            min_value=0,
            value=100,
            step=100,
        )
        monte_carlo_max_accounts = st.number_input(
            "Monte Carlo max accounts",
            min_value=1,
            value=100,
            step=1,
        )

        run_analysis_button = st.button(
            "Run Analysis",
            type="primary",
            disabled=not selected_preset_runnable,
        )

    return {
        "market_data_path": market_data_path,
        "symbol": symbol,
        "point_value": point_value,
        "preset_id": selected_preset_id,
        "comparison_enabled": comparison_enabled,
        "comparison_preset_ids": comparison_preset_ids,
        "strategy_name": strategy_name,
        "strategy_params": strategy_params,
        "strategy_start_time": _blank_to_none(strategy_start_time),
        "strategy_end_time": _blank_to_none(strategy_end_time),
        "force_close_time": _blank_to_none(force_close_time),
        "contracts": contracts,
        "stop_loss_points": stop_loss_points,
        "take_profit_points": take_profit_points,
        "max_holding_minutes": int(max_holding_minutes),
        "commission_per_side": commission_per_side,
        "slippage_points": slippage_points,
        "spread_points": spread_points,
        "bankroll": bankroll if bankroll > 0 else None,
        "monte_carlo_runs": int(monte_carlo_runs),
        "monte_carlo_max_accounts": int(monte_carlo_max_accounts),
        "run_analysis": run_analysis_button,
    }


def _strategy_controls(strategy_name: str) -> dict[str, Any]:
    if strategy_name == "random":
        return {
            "probability": st.number_input(
                "Random probability",
                min_value=0.0,
                max_value=1.0,
                value=0.005,
                format="%.4f",
            ),
            "seed": st.number_input("Random seed", value=42, step=1),
        }

    return {
        "period_k": st.number_input("PeriodK", min_value=1, value=20, step=1),
        "period_d": st.number_input("PeriodD", min_value=1, value=5, step=1),
        "smooth": st.number_input("Smooth", min_value=1, value=3, step=1),
        "oversold": st.number_input("Oversold", min_value=0.0, value=20.0),
        "overbought": st.number_input("Overbought", min_value=0.0, value=80.0),
        "signal_mode": st.selectbox("Signal mode", options=["cross", "zone"], index=0),
        "use_d_confirmation": st.checkbox("Use D confirmation", value=False),
        "min_k_d_gap": st.number_input("Min K/D gap", min_value=0.0, value=0.0),
        "cooldown_bars": st.number_input("Cooldown bars", min_value=0, value=0, step=1),
    }


def run_analysis(controls: dict[str, Any]) -> None:
    if controls["preset_id"] is None:
        st.error("No preset selected.")
        return

    preset = load_preset(controls["preset_id"])
    is_runnable, missing_fields = validate_preset_is_runnable(preset)
    if not is_runnable:
        st.error("Selected preset is not runnable.")
        st.write(missing_fields)
        return

    st.info(
        f"Selected preset: {preset['company']} | "
        f"{preset.get('plan')} | {preset.get('account_name')}"
    )

    ohlc = load_ohlc_data(controls["market_data_path"], symbol=controls["symbol"])
    strategy = build_strategy(controls)
    trades = backtest_strategy(
        ohlc=ohlc,
        strategy=strategy,
        symbol=controls["symbol"],
        contracts=controls["contracts"],
        point_value=controls["point_value"],
        stop_loss_points=controls["stop_loss_points"],
        take_profit_points=controls["take_profit_points"],
        max_holding_minutes=controls["max_holding_minutes"],
        commission_per_side=controls["commission_per_side"],
        slippage_points=controls["slippage_points"],
        spread_points=controls["spread_points"],
        force_close_time=controls["force_close_time"],
    )
    if trades.empty:
        st.warning("No trades were generated by the selected strategy.")

    strategy_metrics = calculate_strategy_metrics(trades)
    config = config_from_preset(preset)
    results = simulate_funding(trades, config)
    business_metrics = calculate_business_metrics(results, config)
    bankroll_result = None
    if controls["bankroll"] is not None:
        bankroll_result = calculate_bankroll_curve(
            results["business_events"],
            initial_bankroll=controls["bankroll"],
            account_cost=_account_cost_from_config(config),
        )
    streak_analysis = calculate_streak_analysis(results)
    risk_result = None
    required_bankroll = None
    if controls["bankroll"] is not None and controls["monte_carlo_runs"] > 0:
        outcomes = extract_account_net_outcomes(results)
        risk_result = run_monte_carlo_ruin_simulation(
            outcomes,
            initial_bankroll=controls["bankroll"],
            account_cost=_account_cost_from_config(config),
            runs=controls["monte_carlo_runs"],
            max_accounts=controls["monte_carlo_max_accounts"],
        )
        required_bankroll = estimate_required_bankroll(
            outcomes,
            account_cost=_account_cost_from_config(config),
            runs=max(1, min(controls["monte_carlo_runs"], 5000)),
            max_accounts=controls["monte_carlo_max_accounts"],
        )
    comparison_rows = []
    if controls.get("comparison_enabled"):
        comparison_rows = run_app_preset_comparison(
            trades=trades,
            preset_ids=controls.get("comparison_preset_ids", []),
            bankroll=controls.get("bankroll"),
            monte_carlo_runs=controls.get("monte_carlo_runs", 0),
            monte_carlo_max_accounts=controls.get("monte_carlo_max_accounts", 100),
        )
        if not comparison_rows:
            st.warning("No runnable presets were available for comparison.")

    exported_files = export_app_outputs(
        trades,
        strategy_metrics,
        business_metrics,
        bankroll_result,
        streak_analysis,
        risk_result,
        required_bankroll,
        comparison_rows,
    )
    store_analysis_results(
        ohlc,
        trades,
        strategy_metrics,
        business_metrics,
        bankroll_result,
        streak_analysis,
        risk_result,
        required_bankroll,
        exported_files,
        preset,
        controls,
        config,
        comparison_rows,
    )


def build_strategy(controls: dict[str, Any]):
    params = controls["strategy_params"]
    if controls["strategy_name"] == "random":
        return RandomEntryStrategy(
            probability=params["probability"],
            seed=int(params["seed"]),
            start_time=controls["strategy_start_time"],
            end_time=controls["strategy_end_time"],
        )

    return StochasticLevelStrategy(
        period_k=int(params["period_k"]),
        period_d=int(params["period_d"]),
        smooth=int(params["smooth"]),
        oversold_level=params["oversold"],
        overbought_level=params["overbought"],
        signal_mode=params["signal_mode"],
        use_d_confirmation=params["use_d_confirmation"],
        min_k_d_gap=params["min_k_d_gap"],
        cooldown_bars=int(params["cooldown_bars"]),
        start_time=controls["strategy_start_time"],
        end_time=controls["strategy_end_time"],
    )


def run_app_preset_comparison(
    trades: pd.DataFrame,
    preset_ids: list[str],
    bankroll: float | None,
    monte_carlo_runs: int,
    monte_carlo_max_accounts: int,
) -> list[dict[str, Any]]:
    rows = []
    for preset_id in preset_ids:
        try:
            preset = load_preset(preset_id)
        except ValueError:
            continue
        is_runnable, _ = validate_preset_is_runnable(preset)
        if not is_runnable:
            continue

        config = config_from_preset(preset)
        results = simulate_funding(trades, config)
        metrics = calculate_business_metrics(results, config)
        bankroll_result = None
        if bankroll is not None:
            bankroll_result = calculate_bankroll_curve(
                results["business_events"],
                initial_bankroll=bankroll,
                account_cost=_account_cost_from_config(config),
            )
        risk_result = None
        if bankroll is not None and monte_carlo_runs > 0:
            outcomes = extract_account_net_outcomes(results)
            risk_result = run_monte_carlo_ruin_simulation(
                outcomes,
                initial_bankroll=bankroll,
                account_cost=_account_cost_from_config(config),
                runs=monte_carlo_runs,
                max_accounts=monte_carlo_max_accounts,
            )
        rows.append(
            app_comparison_row(
                preset=preset,
                metrics=metrics,
                bankroll_result=bankroll_result,
                risk_result=risk_result,
            )
        )
    return rows


def app_comparison_row(
    preset: dict[str, Any],
    metrics: dict[str, Any],
    bankroll_result: dict[str, Any] | None = None,
    risk_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bankroll_metrics = None if bankroll_result is None else bankroll_result["metrics"]
    risk_metrics = None if risk_result is None else risk_result["metrics"]
    final_bankroll = None if bankroll_metrics is None else bankroll_metrics["final_bankroll"]
    ruin_probability = None if risk_metrics is None else risk_metrics["ruin_probability"]
    risk_adjusted_score = metrics["net_business_pnl"]
    if ruin_probability is not None:
        risk_adjusted_score = metrics["net_business_pnl"] * (1 - ruin_probability)

    return {
        "preset_id": preset.get("preset_id"),
        "company": preset.get("company"),
        "plan": preset.get("plan"),
        "account_name": preset.get("account_name"),
        "account_size": preset.get("account_size"),
        "pass_rate": metrics.get("pass_rate", 0.0),
        "payout_rate": metrics.get("payout_rate_on_evaluations", 0.0),
        "payout_rate_on_passed": metrics.get("payout_rate_on_passed", 0.0),
        "total_net_payout": metrics.get("total_net_payout", 0.0),
        "net_business_pnl": metrics.get("net_business_pnl", 0.0),
        "roi": metrics.get("roi", 0.0),
        "final_bankroll": final_bankroll,
        "ruin_probability": ruin_probability,
        "risk_adjusted_score": risk_adjusted_score,
    }


def store_analysis_results(
    ohlc_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    strategy_metrics: dict[str, Any],
    business_metrics: dict[str, Any],
    bankroll_result: dict[str, Any] | None,
    streak_analysis: dict[str, Any],
    risk_of_ruin_result: dict[str, Any] | None,
    required_bankroll_result: dict[str, Any] | None,
    exported_files: dict[str, Path],
    preset: dict[str, Any],
    controls: dict[str, Any],
    config: dict[str, Any],
    comparison_rows: list[dict[str, Any]] | None = None,
) -> None:
    st.session_state["analysis_ran"] = True
    st.session_state["analysis"] = {
        "ohlc_df": ohlc_df,
        "trades_df": trades_df,
        "strategy_metrics": strategy_metrics,
        "business_metrics": business_metrics,
        "bankroll_result": bankroll_result,
        "risk_of_ruin_result": risk_of_ruin_result,
        "required_bankroll_result": required_bankroll_result,
        "streak_analysis": streak_analysis,
        "comparison_rows": comparison_rows or [],
        "exported_files": exported_files,
        "selected_preset": {
            "preset_id": preset.get("preset_id"),
            "company": preset.get("company"),
            "plan": preset.get("plan"),
            "account_name": preset.get("account_name"),
            "account_size": preset.get("account_size"),
        },
        "selected_strategy_name": controls.get("strategy_name"),
        "strategy_params": controls.get("strategy_params", {}),
        "input_configuration": {
            "market_data_path": controls.get("market_data_path"),
            "symbol": controls.get("symbol"),
            "point_value": controls.get("point_value"),
            "time_filters": {
                "strategy_start_time": controls.get("strategy_start_time"),
                "strategy_end_time": controls.get("strategy_end_time"),
                "force_close_time": controls.get("force_close_time"),
            },
            "cost_settings": {
                "commission_per_side": controls.get("commission_per_side"),
                "slippage_points": controls.get("slippage_points"),
                "spread_points": controls.get("spread_points"),
            },
            "bankroll": controls.get("bankroll"),
            "monte_carlo_runs": controls.get("monte_carlo_runs"),
            "monte_carlo_max_accounts": controls.get("monte_carlo_max_accounts"),
            "comparison_enabled": controls.get("comparison_enabled"),
            "comparison_preset_ids": controls.get("comparison_preset_ids", []),
        },
        "risk_settings": {
            "stop_loss_points": controls.get("stop_loss_points"),
            "take_profit_points": controls.get("take_profit_points"),
            "max_holding_minutes": controls.get("max_holding_minutes"),
            "contracts": controls.get("contracts"),
        },
        "config_summary": {
            "evaluation_enabled": config.get("evaluation", {}).get("enabled"),
            "funded_enabled": config.get("funded", {}).get("enabled"),
        },
    }


def get_analysis_state() -> dict[str, Any] | None:
    if not st.session_state.get("analysis_ran"):
        return None
    return st.session_state.get("analysis")


def render_outputs_from_state(analysis_state: dict[str, Any]) -> None:
    render_outputs(
        analysis_state["ohlc_df"],
        analysis_state["trades_df"],
        analysis_state["strategy_metrics"],
        analysis_state["business_metrics"],
        analysis_state["bankroll_result"],
        analysis_state["streak_analysis"],
        analysis_state["risk_of_ruin_result"],
        analysis_state["required_bankroll_result"],
        analysis_state["exported_files"],
        analysis_state,
    )


def render_outputs(
    ohlc,
    trades,
    strategy_metrics: dict[str, Any],
    business_metrics: dict[str, Any],
    bankroll_result: dict[str, Any] | None,
    streak_analysis: dict[str, Any],
    risk_result: dict[str, Any] | None,
    required_bankroll: dict[str, Any] | None,
    exported_files: dict[str, Path],
    analysis_state: dict[str, Any] | None = None,
) -> None:
    dashboard_tab, backtest_tab, funding_risk_tab, data_tab = st.tabs(
        ["Dashboard", "Backtest", "Funding & Risk", "Data"]
    )

    state = analysis_state or {}
    with dashboard_tab:
        render_dashboard_tab(state)
    with backtest_tab:
        render_backtest_tab(state)
    with funding_risk_tab:
        render_funding_risk_tab(state)
    with data_tab:
        render_data_tab(state)


def render_dashboard_tab(analysis_state: dict[str, Any]) -> None:
    strategy_metrics = analysis_state["strategy_metrics"]
    business_metrics = analysis_state["business_metrics"]
    bankroll_result = analysis_state.get("bankroll_result")
    risk_result = analysis_state.get("risk_of_ruin_result")
    final_bankroll = (
        bankroll_result["metrics"]["final_bankroll"] if bankroll_result is not None else None
    )
    ruin_probability = (
        risk_result["metrics"]["ruin_probability"] if risk_result is not None else None
    )

    st.subheader("Executive Summary")
    render_metric_grid(
        [
            ("Total Trades", strategy_metrics["total_trades"]),
            ("Strategy Net PnL", format_currency_compact(strategy_metrics["net_pnl"])),
            ("Profit Factor", format_profit_factor(strategy_metrics["profit_factor"])),
            ("Funding Net PnL", format_currency_compact(business_metrics["net_business_pnl"])),
            ("ROI", format_percent(business_metrics["roi"])),
            ("Final Bankroll", "N/A" if final_bankroll is None else format_currency_compact(final_bankroll)),
            ("Risk of Ruin", "N/A" if ruin_probability is None else format_percent(ruin_probability)),
        ],
        columns_per_row=4,
    )

    st.subheader("Selected Setup")
    setup_rows = _setup_summary_rows(analysis_state)
    st.dataframe(pd.DataFrame(setup_rows), hide_index=True, use_container_width=True)

    st.subheader("Main Warnings / Insights")
    render_dashboard_insights(analysis_state)
    render_comparison_summary(analysis_state.get("comparison_rows", []))


def render_dashboard_insights(analysis_state: dict[str, Any]) -> None:
    diagnostics = build_trade_diagnostics(analysis_state["trades_df"])
    strategy_metrics = analysis_state["strategy_metrics"]
    bankroll_result = analysis_state.get("bankroll_result")
    risk_result = analysis_state.get("risk_of_ruin_result")
    warnings_count = 0

    if strategy_metrics.get("total_trades", 0) < 30:
        st.warning("Small sample size: strategy metrics may not be reliable.")
        warnings_count += 1
    if _numeric_value(strategy_metrics.get("profit_factor"), default=0.0) < 1:
        st.warning("Profit factor below 1.0 indicates the strategy lost money after costs.")
        warnings_count += 1
    if diagnostics["overtrading"].get("average_trades_per_day", 0) > 20:
        st.warning("High trading frequency detected. Costs may dominate results.")
        warnings_count += 1
    cost_ratio = diagnostics["costs"].get("cost_as_percent_of_gross_profit")
    if cost_ratio is not None and cost_ratio > 0.5:
        st.warning("High cost impact: costs consumed more than 50% of gross profit.")
        warnings_count += 1
    if bankroll_result is not None and bankroll_result["metrics"].get("bankroll_ruined"):
        st.warning("Bankroll was ruined during the simulated business path.")
        warnings_count += 1
    if risk_result is not None and risk_result["metrics"].get("ruin_probability", 0) > 0.25:
        st.warning("High risk of ruin detected in Monte Carlo analysis.")
        warnings_count += 1
    if warnings_count == 0:
        st.success("No major dashboard warnings detected for this run.")


def render_comparison_summary(comparison_rows: list[dict[str, Any]]) -> None:
    if not comparison_rows:
        return

    st.subheader("Preset Comparison")
    comparison_df = comparison_rows_to_dataframe(comparison_rows)
    render_comparison_rankings(comparison_df)
    st.dataframe(
        comparison_display_dataframe(comparison_rows),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Download comparison CSV",
        data=comparison_df.to_csv(index=False),
        file_name="app_preset_comparison.csv",
        mime="text/csv",
    )


def render_comparison_rankings(comparison_df: pd.DataFrame) -> None:
    ranking_items = [
        ("Best Net Business PnL", "net_business_pnl", format_currency_compact),
        ("Best ROI", "roi", format_percent),
        ("Best Final Bankroll", "final_bankroll", format_currency_compact),
        ("Best Risk-Adjusted", "risk_adjusted_score", format_currency_compact),
    ]
    cards = []
    for label, column, formatter in ranking_items:
        if column not in comparison_df.columns:
            cards.append((label, "N/A"))
            continue
        numeric_values = pd.to_numeric(comparison_df[column], errors="coerce")
        if numeric_values.dropna().empty:
            cards.append((label, "N/A"))
            continue
        best_row = comparison_df.loc[numeric_values.idxmax()]
        cards.append(
            (
                label,
                f"{best_row['company']} | {best_row['plan']} | "
                f"{format_account_size(best_row['account_size'])} | "
                f"{formatter(best_row[column])}",
            )
        )
    render_metric_grid(cards, columns_per_row=2)


def comparison_rows_to_dataframe(comparison_rows: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(comparison_rows)
    if dataframe.empty:
        return dataframe
    ordered_columns = [
        "company",
        "plan",
        "account_size",
        "pass_rate",
        "payout_rate",
        "total_net_payout",
        "net_business_pnl",
        "roi",
        "final_bankroll",
        "ruin_probability",
        "risk_adjusted_score",
        "preset_id",
    ]
    available_columns = [column for column in ordered_columns if column in dataframe.columns]
    return dataframe[available_columns].sort_values(
        "net_business_pnl",
        ascending=False,
    )


def comparison_display_dataframe(comparison_rows: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = comparison_rows_to_dataframe(comparison_rows)
    if dataframe.empty:
        return dataframe
    formatted = dataframe.copy()
    currency_columns = [
        "total_net_payout",
        "net_business_pnl",
        "final_bankroll",
        "risk_adjusted_score",
    ]
    percent_columns = [
        "pass_rate",
        "payout_rate",
        "roi",
        "ruin_probability",
    ]
    for column in currency_columns:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(format_currency_full)
    for column in percent_columns:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(format_percent)
    if "account_size" in formatted.columns:
        formatted["account_size"] = formatted["account_size"].apply(format_account_size)
    return formatted


def render_backtest_tab(analysis_state: dict[str, Any]) -> None:
    with st.expander("Trade Explorer", expanded=True):
        render_backtest_trade_explorer(analysis_state)
    with st.expander("PnL Charts", expanded=False):
        render_trade_pnl_charts(analysis_state["trades_df"])
    with st.expander("Trade Diagnostics", expanded=False):
        render_diagnostics_tab(analysis_state["trades_df"], analysis_state["strategy_metrics"])
    with st.expander("Trades Table", expanded=False):
        render_filtered_trades_table(analysis_state["trades_df"])


def render_funding_risk_tab(analysis_state: dict[str, Any]) -> None:
    with st.expander("Funding Results", expanded=True):
        render_funding_summary(analysis_state["business_metrics"])
    with st.expander("Bankroll", expanded=True):
        render_bankroll_summary(analysis_state.get("bankroll_result"))
    with st.expander("Risk of Ruin", expanded=False):
        render_risk_summary(
            analysis_state.get("risk_of_ruin_result"),
            analysis_state.get("required_bankroll_result"),
        )
    with st.expander("Streak Analysis", expanded=False):
        render_streak_summary(analysis_state["streak_analysis"])


def render_data_tab(analysis_state: dict[str, Any]) -> None:
    st.subheader("Input Configuration")
    st.dataframe(
        pd.DataFrame(_configuration_rows(analysis_state)),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Generated Outputs")
    exported_files = analysis_state.get("exported_files", {})
    output_rows = [
        {"Output": label, "Path": str(path), "Exists": Path(path).exists()}
        for label, path in exported_files.items()
    ]
    st.dataframe(pd.DataFrame(output_rows), hide_index=True, use_container_width=True)

    st.subheader("Raw Data Previews")
    with st.expander("OHLC Preview", expanded=False):
        st.dataframe(analysis_state["ohlc_df"].head(100), use_container_width=True)
    with st.expander("Generated Trades Preview", expanded=False):
        st.dataframe(analysis_state["trades_df"].head(100), use_container_width=True)
    comparison_rows = analysis_state.get("comparison_rows", [])
    if comparison_rows:
        with st.expander("Preset Comparison Rows", expanded=False):
            st.dataframe(
                comparison_display_dataframe(comparison_rows),
                hide_index=True,
                use_container_width=True,
            )
    with st.expander("JSON Metrics", expanded=False):
        st.json(
            {
                "strategy_metrics": analysis_state["strategy_metrics"],
                "business_metrics": analysis_state["business_metrics"],
                "comparison_rows": comparison_rows,
                "bankroll_metrics": None
                if analysis_state.get("bankroll_result") is None
                else analysis_state["bankroll_result"]["metrics"],
                "risk_of_ruin_metrics": None
                if analysis_state.get("risk_of_ruin_result") is None
                else analysis_state["risk_of_ruin_result"]["metrics"],
                "streak_analysis": analysis_state["streak_analysis"],
            }
        )


def render_strategy_summary(strategy_metrics: dict[str, Any]) -> None:
    st.subheader("Strategy Summary")
    _metric_row(
        [
            ("Total Trades", strategy_metrics["total_trades"]),
            ("Win Rate", f"{strategy_metrics['win_rate']:.2%}"),
            ("Net PnL", _money(strategy_metrics["net_pnl"])),
            ("Profit Factor", format_profit_factor(strategy_metrics["profit_factor"])),
            ("Total Cost", _money(strategy_metrics["total_cost"])),
            ("Average Trade", _money(strategy_metrics["average_trade"])),
        ]
    )
    if _is_infinite_profit_factor(strategy_metrics.get("profit_factor")):
        st.info(
            "Profit Factor is infinite because there were no losing trades in this "
            "sample. Interpret carefully."
        )
    if strategy_metrics.get("total_trades", 0) < 30:
        st.warning("Small sample size: strategy metrics may not be reliable.")


def render_trade_pnl_charts(trades_df: pd.DataFrame) -> None:
    if trades_df.empty or "NetPnL" not in trades_df.columns:
        st.info("No NetPnL data available for trade PnL charts.")
        return

    pnl_data = prepare_trade_pnl_chart_data(trades_df)
    st.subheader("Trade PnL")
    bar_colors = [
        "#16a34a" if value >= 0 else "#dc2626"
        for value in pnl_data["NetPnL"]
    ]
    pnl_fig = go.Figure(
        data=[
            go.Bar(
                x=pnl_data["TradeIndex"],
                y=pnl_data["NetPnL"],
                marker_color=bar_colors,
                hovertemplate="Trade %{x}<br>Net PnL: $%{y:,.2f}<extra></extra>",
            )
        ]
    )
    pnl_fig.update_layout(
        xaxis_title="Trade",
        yaxis_title="Net PnL",
        height=360,
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(pnl_fig, use_container_width=True)

    st.subheader("Cumulative Trade PnL")
    equity_fig = go.Figure(
        data=[
            go.Scatter(
                x=pnl_data["TradeIndex"],
                y=pnl_data["CumulativeNetPnL"],
                mode="lines",
                line=dict(color="#2563eb", width=2),
                hovertemplate="Trade %{x}<br>Cumulative PnL: $%{y:,.2f}<extra></extra>",
            )
        ]
    )
    equity_fig.update_layout(
        xaxis_title="Trade",
        yaxis_title="Cumulative Net PnL",
        height=360,
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(equity_fig, use_container_width=True)


def render_funding_summary(business_metrics: dict[str, Any]) -> None:
    st.subheader("Funding Summary")
    _metric_row(
        [
            ("Total Evaluations", business_metrics["total_evaluations"]),
            ("Passed Evaluations", business_metrics["passed_evaluations"]),
            ("Pass Rate", f"{business_metrics['pass_rate']:.2%}"),
            ("Funded With Payout", business_metrics["funded_with_payout"]),
            ("Total Net Payout", _money(business_metrics["total_net_payout"])),
            ("Net Business PnL", _money(business_metrics["net_business_pnl"])),
            ("ROI", f"{business_metrics['roi']:.2%}"),
        ]
    )


def render_bankroll_summary(bankroll_result: dict[str, Any] | None) -> None:
    if bankroll_result is None:
        st.info("No bankroll was configured for this run.")
        return

    metrics = bankroll_result["metrics"]
    st.subheader("Bankroll Summary")
    _metric_row(
        [
            ("Initial Bankroll", _money(metrics["initial_bankroll"])),
            ("Final Bankroll", _money(metrics["final_bankroll"])),
            ("Lowest Bankroll", _money(metrics["lowest_bankroll"])),
            ("Ruined", "Yes" if metrics["bankroll_ruined"] else "No"),
            ("Max Drawdown", _money(metrics["max_bankroll_drawdown"])),
        ]
    )
    render_bankroll_chart(bankroll_result)


def render_bankroll_chart(bankroll_result: dict[str, Any]) -> None:
    curve = bankroll_result.get("curve", [])
    if not curve:
        st.info("No bankroll curve is available.")
        return

    curve_df = pd.DataFrame(curve)
    if "bankroll" not in curve_df.columns:
        st.info("No bankroll values are available for charting.")
        return

    x_column = "time" if "time" in curve_df.columns and curve_df["time"].notna().any() else "step"
    fig = go.Figure(
        data=[
            go.Scatter(
                x=curve_df[x_column],
                y=curve_df["bankroll"],
                mode="lines+markers",
                line=dict(color="#2563eb", width=2),
                hovertemplate="Step: %{x}<br>Bankroll: $%{y:,.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Bankroll Evolution",
        xaxis_title="Event",
        yaxis_title="Bankroll",
        height=380,
        margin=dict(l=20, r=20, t=45, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(curve_df, use_container_width=True)


def render_risk_summary(
    risk_result: dict[str, Any] | None,
    required_bankroll: dict[str, Any] | None,
) -> None:
    if risk_result is None:
        st.info("No Monte Carlo risk of ruin analysis was run.")
        return

    metrics = risk_result["metrics"]
    recommended = None if required_bankroll is None else required_bankroll.get(
        "recommended_bankroll"
    )
    st.subheader("Risk of Ruin Summary")
    _metric_row(
        [
            ("Ruin Probability", f"{metrics['ruin_probability']:.2%}"),
            ("Survival Probability", f"{metrics['survival_probability']:.2%}"),
            ("Median Final Bankroll", _money(metrics["median_final_bankroll"])),
            (
                "Recommended Bankroll",
                "N/A" if recommended is None else _money(recommended),
            ),
        ]
    )


def render_streak_summary(streak_analysis: dict[str, Any]) -> None:
    st.subheader("Streak Analysis")
    _metric_row(
        [
            (
                "Max No-Payout Accounts",
                streak_analysis["max_consecutive_no_payout_accounts"],
            ),
            (
                "Max Negative Accounts",
                streak_analysis["max_consecutive_negative_accounts"],
            ),
            (
                "Max Failed Evaluations",
                streak_analysis["max_consecutive_failed_evaluations"],
            ),
        ]
    )


def render_diagnostics_tab(
    trades_df: pd.DataFrame,
    strategy_metrics: dict[str, Any],
) -> None:
    if trades_df.empty:
        st.info("No trades available for diagnostics.")
        return

    diagnostics = build_trade_diagnostics(trades_df)
    overtrading = diagnostics["overtrading"]
    costs = diagnostics["costs"]
    quality = diagnostics["quality"]

    st.subheader("Trade Activity")
    st.caption("How often the strategy traded and how long trades stayed open.")
    render_metric_grid(
        [
            ("Total Trades", overtrading["total_trades"]),
            ("Trading Days", overtrading["unique_trading_days"]),
            ("Avg Trades / Day", format_number(overtrading["average_trades_per_day"])),
            ("Max Trades / Day", overtrading["max_trades_in_one_day"]),
            ("Avg Trades / Hour", format_number(overtrading["average_trades_per_hour"])),
            ("Median Holding Minutes", format_number(overtrading["median_holding_minutes"])),
        ],
        columns_per_row=3,
    )

    st.subheader("Cost Impact")
    st.caption("How much commissions, slippage and spread consumed the strategy edge.")
    render_metric_grid(
        [
            ("Gross PnL", format_currency_compact(costs["gross_pnl"])),
            ("Net PnL", format_currency_compact(costs["net_pnl"])),
            ("Total Cost", format_currency_compact(costs["total_cost"])),
            ("Avg Cost / Trade", format_currency_compact(costs["average_cost_per_trade"])),
            ("Commission", format_currency_compact(costs["total_commission"])),
            ("Slippage", format_currency_compact(costs["total_slippage_cost"])),
            ("Spread", format_currency_compact(costs["total_spread_cost"])),
            ("Cost / Gross Profit", format_percent(costs["cost_as_percent_of_gross_profit"])),
        ],
        columns_per_row=4,
    )

    st.subheader("Trade Quality")
    st.caption("Whether the strategy wins often enough for its average win/loss profile.")
    render_metric_grid(
        [
            ("Win Rate", format_percent(quality["win_rate"])),
            ("Average Winner", format_currency_compact(quality["average_winner"])),
            ("Average Loser", format_currency_compact(quality["average_loser"])),
            ("Payoff Ratio", format_number(quality["payoff_ratio"])),
            ("Breakeven Win Rate", format_percent(quality["breakeven_win_rate"])),
            ("Expectancy / Trade", format_currency_compact(quality["expectancy_per_trade"])),
        ],
        columns_per_row=3,
    )

    st.subheader("Warnings / Insights")
    render_diagnostic_warnings(diagnostics, strategy_metrics)

    st.subheader("Diagnostic Tables & Charts")
    with st.expander("Exit Reason Breakdown", expanded=False):
        st.dataframe(
            _format_diagnostic_money_columns(
                diagnostics["exit_reason_table"],
                ["NetPnL", "AverageNetPnL"],
            ),
            use_container_width=True,
        )

    hourly_table = diagnostics["hourly_table"]
    if not hourly_table.empty:
        with st.expander("Hourly Diagnostics", expanded=False):
            st.dataframe(
                _format_diagnostic_money_columns(hourly_table, ["NetPnL", "TotalCost"]),
                use_container_width=True,
            )
            st.caption("Trades by hour")
            st.bar_chart(hourly_table.set_index("Hour")["Trades"])
            st.caption("Net PnL by hour")
            st.bar_chart(hourly_table.set_index("Hour")["NetPnL"])

    daily_table = diagnostics["daily_table"]
    if not daily_table.empty:
        with st.expander("Daily Diagnostics", expanded=False):
            st.dataframe(
                _format_diagnostic_money_columns(daily_table, ["NetPnL", "TotalCost"]),
                use_container_width=True,
            )
            st.caption("Trades by date")
            st.bar_chart(daily_table.set_index("Date")["Trades"])
            st.caption("Net PnL by date")
            st.bar_chart(daily_table.set_index("Date")["NetPnL"])
            best_day = diagnostics["best_day"]
            worst_day = diagnostics["worst_day"]
            if best_day is not None and worst_day is not None:
                st.caption(
                    f"Best day: {best_day['Date']} ({format_currency_full(best_day['NetPnL'])}) | "
                    f"Worst day: {worst_day['Date']} ({format_currency_full(worst_day['NetPnL'])})"
                )


def render_backtest_chart(ohlc_df: pd.DataFrame, trades_df: pd.DataFrame) -> None:
    st.info(
        "For performance, the backtest chart is limited to a filtered date range "
        "and a maximum number of bars/trades."
    )
    ohlc = prepare_ohlc_for_chart(ohlc_df)
    if ohlc.empty:
        st.info("No OHLC data available for the backtest chart.")
        return

    available_dates = sorted(ohlc["DateTime"].dt.date.unique())
    if not available_dates:
        st.info("No valid OHLC timestamps available for the backtest chart.")
        return

    control_cols = st.columns(4)
    with control_cols[0]:
        selected_day = st.selectbox("Trading day", options=available_dates, index=0)
    with control_cols[1]:
        max_bars = st.number_input("Max bars", min_value=50, max_value=5000, value=500, step=50)
    with control_cols[2]:
        max_trades = st.number_input("Max trades", min_value=1, max_value=1000, value=100, step=10)
    with control_cols[3]:
        direction_filter = st.selectbox("Direction", options=["All", "Long only", "Short only"])

    option_cols = st.columns(2)
    with option_cols[0]:
        show_exit_markers = st.checkbox("Show exit markers", value=True)
    with option_cols[1]:
        show_entry_exit_lines = st.checkbox("Show entry-exit lines", value=True)

    day_ohlc = ohlc[ohlc["DateTime"].dt.date == selected_day].head(int(max_bars))
    if day_ohlc.empty:
        st.info("No bars found for the selected date.")
        return

    start_dt = day_ohlc["DateTime"].min()
    end_dt = day_ohlc["DateTime"].max()
    chart_trades = filter_trades_for_chart(
        trades_df,
        start_dt=start_dt,
        end_dt=end_dt,
        direction_filter=direction_filter,
        max_trades=int(max_trades),
    )
    if chart_trades.empty:
        st.info("No trades found in the selected chart range.")

    fig = build_backtest_price_figure(
        day_ohlc,
        chart_trades,
        show_exit_markers=show_exit_markers,
        show_entry_exit_lines=show_entry_exit_lines,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_backtest_trade_explorer(analysis_state: dict[str, Any]) -> None:
    st.subheader("Backtest Trade Explorer")
    ohlc_df = analysis_state.get("ohlc_df")
    trades_df = analysis_state.get("trades_df")
    if ohlc_df is None or trades_df is None or trades_df.empty:
        st.info("No trades or OHLC data available for the trade explorer.")
        return

    trades = prepare_trades_for_explorer(trades_df)
    if trades.empty:
        st.info("No valid trades available for the trade explorer.")
        return

    filters = render_trade_explorer_filters(trades)
    filtered_trades = filter_trades_for_explorer(trades, filters)
    if filtered_trades.empty:
        st.warning("No trades match the selected filters.")
        return

    display_columns = [
        column
        for column in [
            "TradeID",
            "EntryTime",
            "ExitTime",
            "Direction",
            "EntryPrice",
            "ExitPrice",
            "NetPnL",
            "ExitReason",
            "PhaseProfile",
            "StrategyName",
        ]
        if column in filtered_trades.columns
    ]
    st.dataframe(filtered_trades[display_columns].head(1000), use_container_width=True)

    # Future: replace selectbox with interactive row selection / double-click using streamlit-aggrid.
    trade_ids = filtered_trades["TradeID"].tolist()
    selected_trade_id = st.selectbox("Select TradeID to inspect", options=trade_ids)
    selected_trade = filtered_trades[filtered_trades["TradeID"] == selected_trade_id].iloc[0]
    context_minutes = st.number_input(
        "Context minutes before/after",
        min_value=5,
        max_value=240,
        value=60,
        step=5,
    )
    render_selected_trade_chart(
        ohlc_df=ohlc_df,
        selected_trade=selected_trade,
        analysis_state=analysis_state,
        context_minutes=int(context_minutes),
    )


def render_trade_explorer_filters(trades: pd.DataFrame) -> dict[str, Any]:
    filter_cols = st.columns(3)
    with filter_cols[0]:
        direction_filter = st.selectbox(
            "Direction filter",
            options=["All", "Long", "Short"],
            key="explorer_direction_filter",
        )
    exit_reasons = ["All"]
    if "ExitReason" in trades.columns:
        exit_reasons.extend(sorted(str(value) for value in trades["ExitReason"].dropna().unique()))
    with filter_cols[1]:
        exit_reason_filter = st.selectbox(
            "ExitReason filter",
            options=exit_reasons,
            key="explorer_exit_reason_filter",
        )
    phase_options = ["All"]
    if "PhaseProfile" in trades.columns:
        phase_options.extend(sorted(str(value) for value in trades["PhaseProfile"].dropna().unique()))
    with filter_cols[2]:
        phase_filter = st.selectbox(
            "PhaseProfile filter",
            options=phase_options,
            key="explorer_phase_filter",
        )

    date_values = ["All dates"]
    if "EntryTime" in trades.columns:
        date_values.extend(
            str(value)
            for value in sorted(trades["EntryTime"].dt.date.dropna().unique())
        )
    range_cols = st.columns(3)
    with range_cols[0]:
        selected_date = st.selectbox(
            "Entry date",
            options=date_values,
            key="explorer_date_filter",
        )
    min_pnl = float(trades["NetPnL"].min()) if "NetPnL" in trades.columns else 0.0
    max_pnl = float(trades["NetPnL"].max()) if "NetPnL" in trades.columns else 0.0
    with range_cols[1]:
        minimum_net_pnl = st.number_input(
            "Minimum NetPnL",
            value=min_pnl,
            key="explorer_min_net_pnl",
        )
    with range_cols[2]:
        maximum_net_pnl = st.number_input(
            "Maximum NetPnL",
            value=max_pnl,
            key="explorer_max_net_pnl",
        )

    return {
        "direction": direction_filter,
        "exit_reason": exit_reason_filter,
        "phase_profile": phase_filter,
        "entry_date": selected_date,
        "minimum_net_pnl": minimum_net_pnl,
        "maximum_net_pnl": maximum_net_pnl,
    }


def render_filtered_trades_table(trades_df: pd.DataFrame) -> None:
    if trades_df.empty:
        st.info("No generated trades available.")
        return

    trades = prepare_trades_for_explorer(trades_df)
    filters = render_trade_table_filters(trades)
    filtered = filter_trades_for_explorer(trades, filters)
    if filtered.empty:
        st.warning("No trades match the selected filters.")
        return

    display_columns = [
        column
        for column in [
            "TradeID",
            "EntryTime",
            "ExitTime",
            "Direction",
            "EntryPrice",
            "ExitPrice",
            "NetPnL",
            "ExitReason",
            "PhaseProfile",
            "StrategyName",
        ]
        if column in filtered.columns
    ]
    st.dataframe(filtered[display_columns].head(1000), use_container_width=True)


def render_trade_table_filters(trades: pd.DataFrame) -> dict[str, Any]:
    filter_cols = st.columns(4)
    with filter_cols[0]:
        direction_filter = st.selectbox(
            "Table direction",
            options=["All", "Long", "Short"],
            key="table_direction_filter",
        )
    exit_reasons = ["All"]
    if "ExitReason" in trades.columns:
        exit_reasons.extend(sorted(str(value) for value in trades["ExitReason"].dropna().unique()))
    with filter_cols[1]:
        exit_reason_filter = st.selectbox(
            "Table ExitReason",
            options=exit_reasons,
            key="table_exit_reason_filter",
        )
    phase_options = ["All"]
    if "PhaseProfile" in trades.columns:
        phase_options.extend(sorted(str(value) for value in trades["PhaseProfile"].dropna().unique()))
    with filter_cols[2]:
        phase_filter = st.selectbox(
            "Table PhaseProfile",
            options=phase_options,
            key="table_phase_filter",
        )
    with filter_cols[3]:
        selected_date = st.selectbox(
            "Table entry date",
            options=_trade_entry_date_options(trades),
            key="table_date_filter",
        )

    min_pnl = float(trades["NetPnL"].min()) if "NetPnL" in trades.columns else 0.0
    max_pnl = float(trades["NetPnL"].max()) if "NetPnL" in trades.columns else 0.0
    pnl_cols = st.columns(2)
    with pnl_cols[0]:
        minimum_net_pnl = st.number_input(
            "Table minimum NetPnL",
            value=min_pnl,
            key="table_min_net_pnl",
        )
    with pnl_cols[1]:
        maximum_net_pnl = st.number_input(
            "Table maximum NetPnL",
            value=max_pnl,
            key="table_max_net_pnl",
        )

    return {
        "direction": direction_filter,
        "exit_reason": exit_reason_filter,
        "phase_profile": phase_filter,
        "entry_date": selected_date,
        "minimum_net_pnl": minimum_net_pnl,
        "maximum_net_pnl": maximum_net_pnl,
    }


def _trade_entry_date_options(trades: pd.DataFrame) -> list[str]:
    date_values = ["All dates"]
    if "EntryTime" in trades.columns:
        date_values.extend(
            str(value)
            for value in sorted(trades["EntryTime"].dt.date.dropna().unique())
        )
    return date_values


def prepare_trades_for_explorer(trades_df: pd.DataFrame) -> pd.DataFrame:
    trades = trades_df.copy().reset_index(drop=True)
    if "TradeID" not in trades.columns:
        trades["TradeID"] = range(1, len(trades) + 1)
    for column in ["EntryTime", "ExitTime"]:
        if column in trades.columns:
            trades[column] = pd.to_datetime(trades[column], errors="coerce")
    for column in ["EntryPrice", "ExitPrice", "NetPnL"]:
        if column in trades.columns:
            trades[column] = pd.to_numeric(trades[column], errors="coerce")
    if "NetPnL" not in trades.columns:
        trades["NetPnL"] = 0.0
    return trades.dropna(subset=["EntryTime", "ExitTime"], how="all")


def filter_trades_for_explorer(
    trades_df: pd.DataFrame,
    filters: dict[str, Any],
) -> pd.DataFrame:
    trades = prepare_trades_for_explorer(trades_df)
    if filters.get("direction") in {"Long", "Short"} and "Direction" in trades.columns:
        trades = trades[trades["Direction"] == filters["direction"]]
    if filters.get("exit_reason") not in {None, "All"} and "ExitReason" in trades.columns:
        trades = trades[trades["ExitReason"].astype(str) == filters["exit_reason"]]
    if filters.get("phase_profile") not in {None, "All"} and "PhaseProfile" in trades.columns:
        trades = trades[trades["PhaseProfile"].astype(str) == filters["phase_profile"]]
    if filters.get("entry_date") not in {None, "All dates"} and "EntryTime" in trades.columns:
        selected_date = pd.to_datetime(filters["entry_date"]).date()
        trades = trades[trades["EntryTime"].dt.date == selected_date]
    minimum_net_pnl = filters.get("minimum_net_pnl")
    maximum_net_pnl = filters.get("maximum_net_pnl")
    if minimum_net_pnl is not None:
        trades = trades[trades["NetPnL"] >= float(minimum_net_pnl)]
    if maximum_net_pnl is not None:
        trades = trades[trades["NetPnL"] <= float(maximum_net_pnl)]
    return trades.sort_values("EntryTime").reset_index(drop=True)


def render_selected_trade_chart(
    ohlc_df: pd.DataFrame,
    selected_trade: pd.Series,
    analysis_state: dict[str, Any],
    context_minutes: int,
) -> None:
    entry_time = pd.to_datetime(selected_trade.get("EntryTime"), errors="coerce")
    exit_time = pd.to_datetime(selected_trade.get("ExitTime"), errors="coerce")
    if pd.isna(entry_time) or pd.isna(exit_time):
        st.error("Selected trade timestamps could not be parsed.")
        return

    start_dt = entry_time - pd.Timedelta(minutes=context_minutes)
    end_dt = exit_time + pd.Timedelta(minutes=context_minutes)
    ohlc = prepare_ohlc_for_chart(ohlc_df)
    ohlc_window = ohlc[(ohlc["DateTime"] >= start_dt) & (ohlc["DateTime"] <= end_dt)]
    if ohlc_window.empty:
        st.warning("No OHLC bars found around selected trade.")
        return

    strategy_context = {
        "strategy_name": analysis_state.get("selected_strategy_name"),
        "strategy_params": analysis_state.get("strategy_params", {}),
        "risk_settings": analysis_state.get("risk_settings", {}),
    }
    fig = build_selected_trade_figure(ohlc_window, selected_trade, strategy_context)
    st.plotly_chart(fig, use_container_width=True)


def build_selected_trade_figure(
    ohlc_window: pd.DataFrame,
    selected_trade: pd.Series,
    strategy_context: dict[str, Any],
) -> go.Figure:
    show_stochastic = strategy_context.get("strategy_name") == "stochastic"
    if show_stochastic:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=[0.72, 0.28],
        )
    else:
        fig = make_subplots(rows=1, cols=1)

    fig.add_trace(
        go.Candlestick(
            x=ohlc_window["DateTime"],
            open=ohlc_window["Open"],
            high=ohlc_window["High"],
            low=ohlc_window["Low"],
            close=ohlc_window["Close"],
            name="OHLC",
        ),
        row=1,
        col=1,
    )

    _add_selected_trade_marker(fig, selected_trade, "entry")
    _add_selected_trade_marker(fig, selected_trade, "exit")
    _add_selected_trade_line(fig, selected_trade)
    _add_sl_tp_lines(fig, selected_trade, strategy_context.get("risk_settings", {}))

    if show_stochastic:
        stoch = compute_stochastic_for_chart(
            ohlc_window,
            strategy_context.get("strategy_params", {}),
        )
        if not stoch.empty:
            fig.add_trace(
                go.Scatter(x=stoch["DateTime"], y=stoch["K"], mode="lines", name="K"),
                row=2,
                col=1,
            )
            fig.add_trace(
                go.Scatter(x=stoch["DateTime"], y=stoch["D"], mode="lines", name="D"),
                row=2,
                col=1,
            )
            oversold = strategy_context.get("strategy_params", {}).get("oversold", 20)
            overbought = strategy_context.get("strategy_params", {}).get("overbought", 80)
            fig.add_hline(y=oversold, line_dash="dot", line_color="#64748b", row=2, col=1)
            fig.add_hline(y=overbought, line_dash="dot", line_color="#64748b", row=2, col=1)
            fig.update_yaxes(title_text="Stoch K/D", row=2, col=1, range=[0, 100])

    trade_id = selected_trade.get("TradeID")
    direction = selected_trade.get("Direction", "")
    net_pnl = _numeric_value(selected_trade.get("NetPnL"))
    exit_reason = selected_trade.get("ExitReason", "")
    fig.update_layout(
        title=(
            f"Trade {trade_id} | {direction} | NetPnL "
            f"{format_currency_full(net_pnl)} | ExitReason {exit_reason}"
        ),
        xaxis_rangeslider_visible=False,
        height=760 if show_stochastic else 620,
        margin=dict(l=20, r=20, t=55, b=20),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    return fig


def compute_stochastic_for_chart(
    ohlc_df: pd.DataFrame,
    strategy_params: dict[str, Any],
) -> pd.DataFrame:
    if ohlc_df.empty:
        return pd.DataFrame(columns=["DateTime", "K", "D"])
    strategy = StochasticLevelStrategy(
        period_k=int(strategy_params.get("period_k", 14)),
        period_d=int(strategy_params.get("period_d", 7)),
        smooth=int(strategy_params.get("smooth", 3)),
    )
    _, percent_k, percent_d = strategy.calculate_stochastics(ohlc_df)
    return pd.DataFrame(
        {
            "DateTime": ohlc_df["DateTime"],
            "K": percent_k,
            "D": percent_d,
        }
    )


def _add_selected_trade_marker(fig: go.Figure, trade: pd.Series, marker_type: str) -> None:
    is_entry = marker_type == "entry"
    time_column = "EntryTime" if is_entry else "ExitTime"
    price_column = "EntryPrice" if is_entry else "ExitPrice"
    time_value = pd.to_datetime(trade.get(time_column), errors="coerce")
    price_value = trade.get(price_column)
    if pd.isna(time_value) or pd.isna(price_value):
        return
    direction = trade.get("Direction", "")
    marker_symbol = "triangle-up" if direction == "Long" else "triangle-down"
    marker_color = "#16a34a" if direction == "Long" else "#dc2626"
    if not is_entry:
        marker_symbol = "x"
        marker_color = "#2563eb"
    fig.add_trace(
        go.Scatter(
            x=[time_value],
            y=[price_value],
            mode="markers",
            name="Entry" if is_entry else "Exit",
            marker=dict(symbol=marker_symbol, color=marker_color, size=13),
            text=[_selected_trade_hover_text(trade)],
            hovertemplate="%{text}<extra></extra>",
        ),
        row=1,
        col=1,
    )


def _add_selected_trade_line(fig: go.Figure, trade: pd.Series) -> None:
    entry_time = pd.to_datetime(trade.get("EntryTime"), errors="coerce")
    exit_time = pd.to_datetime(trade.get("ExitTime"), errors="coerce")
    if pd.isna(entry_time) or pd.isna(exit_time):
        return
    fig.add_trace(
        go.Scatter(
            x=[entry_time, exit_time],
            y=[trade.get("EntryPrice"), trade.get("ExitPrice")],
            mode="lines",
            line=dict(color="#64748b", width=2, dash="dot"),
            name="Entry-Exit",
            hoverinfo="skip",
        ),
        row=1,
        col=1,
    )


def _add_sl_tp_lines(
    fig: go.Figure,
    trade: pd.Series,
    risk_settings: dict[str, Any],
) -> None:
    entry_price = trade.get("EntryPrice")
    direction = trade.get("Direction")
    stop_loss_points = risk_settings.get("stop_loss_points")
    take_profit_points = risk_settings.get("take_profit_points")
    if entry_price is None or direction not in {"Long", "Short"}:
        return
    if stop_loss_points is not None:
        sl = entry_price - stop_loss_points if direction == "Long" else entry_price + stop_loss_points
        fig.add_hline(y=sl, line_color="#dc2626", line_dash="dash", row=1, col=1, annotation_text="SL")
    if take_profit_points is not None:
        tp = entry_price + take_profit_points if direction == "Long" else entry_price - take_profit_points
        fig.add_hline(y=tp, line_color="#16a34a", line_dash="dash", row=1, col=1, annotation_text="TP")


def _selected_trade_hover_text(trade: pd.Series) -> str:
    return (
        f"TradeID: {trade.get('TradeID')}<br>"
        f"Direction: {trade.get('Direction')}<br>"
        f"EntryTime: {trade.get('EntryTime')}<br>"
        f"ExitTime: {trade.get('ExitTime')}<br>"
        f"EntryPrice: {trade.get('EntryPrice')}<br>"
        f"ExitPrice: {trade.get('ExitPrice')}<br>"
        f"NetPnL: {format_currency_full(trade.get('NetPnL'))}<br>"
        f"ExitReason: {trade.get('ExitReason')}"
    )


def build_backtest_price_figure(
    ohlc: pd.DataFrame,
    trades: pd.DataFrame,
    show_exit_markers: bool = True,
    show_entry_exit_lines: bool = True,
) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=ohlc["DateTime"],
                open=ohlc["Open"],
                high=ohlc["High"],
                low=ohlc["Low"],
                close=ohlc["Close"],
                name="OHLC",
            )
        ]
    )

    if not trades.empty:
        direction = trades["Direction"] if "Direction" in trades.columns else pd.Series("", index=trades.index)
        long_entries = trades[direction == "Long"]
        short_entries = trades[direction == "Short"]
        _add_trade_marker_trace(fig, long_entries, "EntryTime", "EntryPrice", "Long Entry", "triangle-up", "#16a34a")
        _add_trade_marker_trace(fig, short_entries, "EntryTime", "EntryPrice", "Short Entry", "triangle-down", "#dc2626")
        if show_exit_markers:
            _add_trade_marker_trace(fig, trades, "ExitTime", "ExitPrice", "Exit", "x", "#2563eb")
        if show_entry_exit_lines:
            for _, trade in trades.iterrows():
                if pd.isna(trade.get("EntryTime")) or pd.isna(trade.get("ExitTime")):
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=[trade.get("EntryTime"), trade.get("ExitTime")],
                        y=[trade.get("EntryPrice"), trade.get("ExitPrice")],
                        mode="lines",
                        line=dict(color="#64748b", width=1, dash="dot"),
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )

    fig.update_layout(
        title="Backtest Entries and Exits",
        xaxis_title="Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=650,
        margin=dict(l=20, r=20, t=45, b=20),
    )
    return fig


def _add_trade_marker_trace(
    fig: go.Figure,
    trades: pd.DataFrame,
    time_column: str,
    price_column: str,
    name: str,
    symbol: str,
    color: str,
) -> None:
    if trades.empty or time_column not in trades.columns or price_column not in trades.columns:
        return
    customdata = trades[
        [column for column in ["TradeID", "Direction", "NetPnL", "ExitReason"] if column in trades.columns]
    ].to_numpy()
    fig.add_trace(
        go.Scatter(
            x=trades[time_column],
            y=trades[price_column],
            mode="markers",
            name=name,
            marker=dict(symbol=symbol, color=color, size=10),
            customdata=customdata,
            hovertemplate=_trade_hover_template(customdata.shape[1]),
        )
    )


def _trade_hover_template(custom_columns: int) -> str:
    labels = ["TradeID", "Direction", "NetPnL", "ExitReason"]
    lines = ["%{x}", "Price: %{y:,.2f}"]
    for index in range(custom_columns):
        label = labels[index]
        value_format = "$%{customdata[" + str(index) + "]:,.2f}" if label == "NetPnL" else "%{customdata[" + str(index) + "]}"
        lines.append(f"{label}: {value_format}")
    return "<br>".join(lines) + "<extra></extra>"


def prepare_trade_pnl_chart_data(trades_df: pd.DataFrame) -> pd.DataFrame:
    data = trades_df.copy().reset_index(drop=True)
    data["NetPnL"] = pd.to_numeric(data.get("NetPnL", 0), errors="coerce").fillna(0.0)
    if "TradeID" in data.columns:
        data["TradeIndex"] = data["TradeID"]
    else:
        data["TradeIndex"] = range(1, len(data) + 1)
    data["CumulativeNetPnL"] = data["NetPnL"].cumsum()
    return data[["TradeIndex", "NetPnL", "CumulativeNetPnL"]]


def prepare_ohlc_for_chart(ohlc_df: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"DateTime", "Open", "High", "Low", "Close"}
    if ohlc_df.empty or not required_columns.issubset(ohlc_df.columns):
        return pd.DataFrame(columns=["DateTime", "Open", "High", "Low", "Close"])

    data = ohlc_df.copy()
    data["DateTime"] = pd.to_datetime(data["DateTime"], errors="coerce")
    for column in ["Open", "High", "Low", "Close"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return (
        data.dropna(subset=["DateTime", "Open", "High", "Low", "Close"])
        .sort_values("DateTime")
        .reset_index(drop=True)
    )


def filter_trades_for_chart(
    trades_df: pd.DataFrame,
    start_dt: Any,
    end_dt: Any,
    direction_filter: str = "All",
    max_trades: int = 100,
) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame()

    trades = trades_df.copy()
    for column in ["EntryTime", "ExitTime"]:
        if column in trades.columns:
            trades[column] = pd.to_datetime(trades[column], errors="coerce")

    if "EntryTime" not in trades.columns and "ExitTime" not in trades.columns:
        return pd.DataFrame()

    entry_time = trades.get("EntryTime", pd.Series(pd.NaT, index=trades.index))
    exit_time = trades.get("ExitTime", pd.Series(pd.NaT, index=trades.index))
    in_range = (
        entry_time.between(start_dt, end_dt, inclusive="both")
        | exit_time.between(start_dt, end_dt, inclusive="both")
    )
    trades = trades[in_range]

    if direction_filter == "Long only" and "Direction" in trades.columns:
        trades = trades[trades["Direction"] == "Long"]
    elif direction_filter == "Short only" and "Direction" in trades.columns:
        trades = trades[trades["Direction"] == "Short"]

    for column in ["EntryPrice", "ExitPrice", "NetPnL"]:
        if column in trades.columns:
            trades[column] = pd.to_numeric(trades[column], errors="coerce")

    sort_column = "EntryTime" if "EntryTime" in trades.columns else "ExitTime"
    return trades.sort_values(sort_column).head(max_trades).reset_index(drop=True)


def render_diagnostic_warnings(
    diagnostics: dict[str, Any],
    strategy_metrics: dict[str, Any],
) -> None:
    overtrading = diagnostics["overtrading"]
    costs = diagnostics["costs"]
    quality = diagnostics["quality"]
    insight_count = 0

    if overtrading["average_trades_per_day"] > 20:
        st.warning("High trading frequency detected. Costs may dominate results.")
        insight_count += 1
    if costs["total_cost"] > abs(costs["net_pnl"]) and costs["net_pnl"] < 0:
        st.warning(
            "Total trading costs are larger than the final net loss. Cost control is critical."
        )
        insight_count += 1
    if _numeric_value(strategy_metrics.get("profit_factor"), default=0.0) < 1:
        st.warning("Profit factor below 1.0 indicates the strategy lost money after costs.")
        insight_count += 1
    if strategy_metrics.get("total_trades", 0) < 30:
        st.warning("Small sample size. Strategy metrics may not be reliable.")
        insight_count += 1
    cost_ratio = costs["cost_as_percent_of_gross_profit"]
    if cost_ratio is not None and cost_ratio > 0.5:
        st.warning("Costs consumed more than 50% of gross profit.")
        insight_count += 1
    breakeven_win_rate = quality["breakeven_win_rate"]
    if breakeven_win_rate is not None and quality["win_rate"] < breakeven_win_rate:
        st.info("Current win rate is below breakeven win rate.")
        insight_count += 1
    if abs(quality["average_loser"]) > quality["average_winner"] > 0:
        st.info("Average loser is larger than average winner.")
        insight_count += 1
    if insight_count == 0:
        st.success("No major diagnostic warnings detected for this sample.")


def export_app_outputs(
    trades,
    strategy_metrics: dict[str, Any],
    business_metrics: dict[str, Any],
    bankroll_result: dict[str, Any] | None,
    streak_analysis: dict[str, Any],
    risk_result: dict[str, Any] | None,
    required_bankroll: dict[str, Any] | None,
    comparison_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "generated_trades": OUTPUT_DIR / "app_generated_trades.csv",
        "summary_metrics": OUTPUT_DIR / "app_summary_metrics.json",
    }
    trades.to_csv(files["generated_trades"], index=False)

    summary = {
        "strategy_metrics": strategy_metrics,
        "business_metrics": business_metrics,
        "bankroll_metrics": None if bankroll_result is None else bankroll_result["metrics"],
        "streak_analysis": streak_analysis,
        "risk_of_ruin_metrics": None if risk_result is None else risk_result["metrics"],
        "required_bankroll": required_bankroll,
        "comparison_rows": comparison_rows or [],
    }
    with files["summary_metrics"].open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, default=str)
    comparison_path = export_comparison_rows(comparison_rows or [], OUTPUT_DIR)
    if comparison_path is not None:
        files["preset_comparison"] = comparison_path
    return files


def export_comparison_rows(
    comparison_rows: list[dict[str, Any]],
    output_dir: Path = OUTPUT_DIR,
) -> Path | None:
    if not comparison_rows:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "app_preset_comparison.csv"
    comparison_rows_to_dataframe(comparison_rows).to_csv(output_path, index=False)
    return output_path


def build_trade_diagnostics(trades_df: pd.DataFrame) -> dict[str, Any]:
    if trades_df.empty:
        return {
            "overtrading": {},
            "costs": {},
            "quality": {},
            "exit_reason_table": pd.DataFrame(),
            "hourly_table": pd.DataFrame(),
            "daily_table": pd.DataFrame(),
            "best_day": None,
            "worst_day": None,
        }

    trades = trades_df.copy()
    net_pnl = _numeric_column(trades, "NetPnL")
    total_cost = _total_cost_series(trades)
    gross_pnl = _gross_pnl_series(trades, net_pnl, total_cost)
    exit_time = _datetime_column(trades, "ExitTime")
    entry_time = _datetime_column(trades, "EntryTime")
    holding_minutes = ((exit_time - entry_time).dt.total_seconds() / 60).dropna()
    trading_dates = exit_time.dt.date.dropna()
    trading_hour_buckets = exit_time.dt.floor("h").dropna()
    winning_trades = net_pnl[net_pnl > 0]
    losing_trades = net_pnl[net_pnl < 0]
    average_winner = float(winning_trades.mean()) if not winning_trades.empty else 0.0
    average_loser = float(losing_trades.mean()) if not losing_trades.empty else 0.0
    payoff_ratio = (
        average_winner / abs(average_loser)
        if average_winner > 0 and average_loser < 0
        else None
    )
    gross_profit = float(gross_pnl[gross_pnl > 0].sum())
    cost_as_percent_of_gross_profit = (
        float(total_cost.sum()) / gross_profit if gross_profit > 0 else None
    )

    daily_table = _daily_diagnostics_table(trades, exit_time, net_pnl, total_cost)
    best_day = None
    worst_day = None
    if not daily_table.empty:
        best_day = daily_table.loc[daily_table["NetPnL"].idxmax()].to_dict()
        worst_day = daily_table.loc[daily_table["NetPnL"].idxmin()].to_dict()

    return {
        "overtrading": {
            "total_trades": int(len(trades)),
            "unique_trading_days": int(trading_dates.nunique()),
            "average_trades_per_day": _safe_divide_number(
                len(trades),
                trading_dates.nunique(),
            ),
            "max_trades_in_one_day": _max_trades_in_one_day(trading_dates),
            "average_trades_per_hour": _safe_divide_optional(
                len(trades),
                trading_hour_buckets.nunique(),
            ),
            "median_holding_minutes": (
                float(holding_minutes.median()) if not holding_minutes.empty else None
            ),
        },
        "costs": {
            "gross_pnl": float(gross_pnl.sum()),
            "net_pnl": float(net_pnl.sum()),
            "total_cost": float(total_cost.sum()),
            "cost_as_percent_of_gross_profit": cost_as_percent_of_gross_profit,
            "average_cost_per_trade": _safe_divide_number(total_cost.sum(), len(trades)),
            "total_commission": float(_numeric_column(trades, "Commission").sum()),
            "total_slippage_cost": float(_numeric_column(trades, "SlippageCost").sum()),
            "total_spread_cost": float(_numeric_column(trades, "SpreadCost").sum()),
        },
        "quality": {
            "average_winner": average_winner,
            "average_loser": average_loser,
            "win_rate": _safe_divide_number(len(winning_trades), len(trades)),
            "payoff_ratio": payoff_ratio,
            "breakeven_win_rate": (
                1 / (1 + payoff_ratio) if payoff_ratio and payoff_ratio > 0 else None
            ),
            "expectancy_per_trade": float(net_pnl.mean()) if len(trades) else 0.0,
        },
        "exit_reason_table": _exit_reason_diagnostics_table(trades, net_pnl),
        "hourly_table": _hourly_diagnostics_table(trades, exit_time, net_pnl, total_cost),
        "daily_table": daily_table,
        "best_day": best_day,
        "worst_day": worst_day,
    }


def _exit_reason_diagnostics_table(
    trades: pd.DataFrame,
    net_pnl: pd.Series,
) -> pd.DataFrame:
    if "ExitReason" not in trades.columns:
        return pd.DataFrame(columns=["ExitReason", "Trades", "NetPnL", "AverageNetPnL"])

    table = (
        pd.DataFrame({"ExitReason": trades["ExitReason"], "NetPnL": net_pnl})
        .groupby("ExitReason", dropna=False)
        .agg(Trades=("NetPnL", "size"), NetPnL=("NetPnL", "sum"), AverageNetPnL=("NetPnL", "mean"))
        .reset_index()
        .sort_values("Trades", ascending=False)
    )
    return table


def _hourly_diagnostics_table(
    trades: pd.DataFrame,
    exit_time: pd.Series,
    net_pnl: pd.Series,
    total_cost: pd.Series,
) -> pd.DataFrame:
    if exit_time.isna().all():
        return pd.DataFrame(columns=["Hour", "Trades", "NetPnL", "TotalCost"])

    table = pd.DataFrame(
        {
            "Hour": exit_time.dt.hour,
            "NetPnL": net_pnl,
            "TotalCost": total_cost,
        }
    ).dropna(subset=["Hour"])
    if table.empty:
        return pd.DataFrame(columns=["Hour", "Trades", "NetPnL", "TotalCost"])

    table["Hour"] = table["Hour"].astype(int)
    return (
        table.groupby("Hour")
        .agg(Trades=("NetPnL", "size"), NetPnL=("NetPnL", "sum"), TotalCost=("TotalCost", "sum"))
        .reset_index()
        .sort_values("Hour")
    )


def _daily_diagnostics_table(
    trades: pd.DataFrame,
    exit_time: pd.Series,
    net_pnl: pd.Series,
    total_cost: pd.Series,
) -> pd.DataFrame:
    if exit_time.isna().all():
        return pd.DataFrame(columns=["Date", "Trades", "NetPnL", "TotalCost"])

    table = pd.DataFrame(
        {
            "Date": exit_time.dt.date.astype("string"),
            "NetPnL": net_pnl,
            "TotalCost": total_cost,
        }
    ).dropna(subset=["Date"])
    if table.empty:
        return pd.DataFrame(columns=["Date", "Trades", "NetPnL", "TotalCost"])

    return (
        table.groupby("Date")
        .agg(Trades=("NetPnL", "size"), NetPnL=("NetPnL", "sum"), TotalCost=("TotalCost", "sum"))
        .reset_index()
        .sort_values("Date")
    )


def _numeric_column(trades: pd.DataFrame, column: str) -> pd.Series:
    if column not in trades.columns:
        return pd.Series([0.0] * len(trades), index=trades.index, dtype=float)
    return pd.to_numeric(trades[column], errors="coerce").fillna(0.0)


def _datetime_column(trades: pd.DataFrame, column: str) -> pd.Series:
    if column not in trades.columns:
        return pd.Series(pd.NaT, index=trades.index, dtype="datetime64[ns]")
    return pd.to_datetime(trades[column], errors="coerce")


def _total_cost_series(trades: pd.DataFrame) -> pd.Series:
    if "TotalCost" in trades.columns:
        return _numeric_column(trades, "TotalCost")
    return (
        _numeric_column(trades, "Commission")
        + _numeric_column(trades, "SlippageCost")
        + _numeric_column(trades, "SpreadCost")
    )


def _gross_pnl_series(
    trades: pd.DataFrame,
    net_pnl: pd.Series,
    total_cost: pd.Series,
) -> pd.Series:
    if "GrossPnL" in trades.columns:
        return _numeric_column(trades, "GrossPnL")
    return net_pnl + total_cost


def _max_trades_in_one_day(trading_dates: pd.Series) -> int:
    if trading_dates.empty:
        return 0
    return int(trading_dates.value_counts().max())


def _safe_divide_number(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def _safe_divide_optional(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def format_account_size(size: Any) -> str:
    if size is None:
        return "Unknown"
    try:
        numeric_size = int(size)
    except (TypeError, ValueError):
        return str(size)

    if numeric_size % 1000 == 0:
        return f"{numeric_size // 1000}K"
    return f"{numeric_size:,}"


def preset_option_label(preset: dict[str, Any]) -> str:
    return (
        f"{preset.get('company') or 'Unknown'} | "
        f"{preset.get('plan') or 'Unknown'} | "
        f"{format_account_size(preset.get('account_size'))} | "
        f"{preset.get('preset_id')}"
    )


def get_runnable_preset_info(preset: dict[str, Any]) -> dict[str, Any]:
    is_runnable, missing_fields = validate_preset_is_runnable(preset)
    preset_info = dict(preset)
    preset_info["is_runnable"] = is_runnable
    preset_info["missing_fields"] = missing_fields
    return preset_info


def filter_presets_by_runnable(
    presets: list[dict[str, Any]],
    show_non_runnable: bool,
) -> list[dict[str, Any]]:
    preset_infos = [get_runnable_preset_info(preset) for preset in presets]
    if show_non_runnable:
        return preset_infos
    return [preset for preset in preset_infos if preset["is_runnable"]]


def select_funding_preset(presets: list[dict[str, Any]]) -> dict[str, Any]:
    if not presets:
        st.error("No presets are available with the current filter.")
        st.stop()

    companies = sorted({preset.get("company") or "Unknown" for preset in presets})
    if not companies:
        st.error("No preset companies are available.")
        st.stop()

    selected_company = st.selectbox(
        "Company",
        options=companies,
        index=_default_index(companies, DEFAULT_PRESET_COMPANY),
    )
    company_presets = [
        preset for preset in presets if (preset.get("company") or "Unknown") == selected_company
    ]

    plans = sorted({preset.get("plan") or "Unknown" for preset in company_presets})
    if not plans:
        st.error("No plans are available for the selected company.")
        st.stop()

    selected_plan = st.selectbox(
        "Plan",
        options=plans,
        index=_default_index(plans, DEFAULT_PRESET_PLAN),
    )
    plan_presets = [
        preset for preset in company_presets if (preset.get("plan") or "Unknown") == selected_plan
    ]

    sizes = sorted(
        {
            preset.get("account_size")
            for preset in plan_presets
            if preset.get("account_size") is not None
        },
        key=_account_size_sort_key,
    )
    if not sizes:
        st.error("No account sizes are available for the selected plan.")
        st.stop()

    selected_size = st.selectbox(
        "Account Size",
        options=sizes,
        index=_default_index(sizes, DEFAULT_PRESET_ACCOUNT_SIZE),
        format_func=format_account_size,
    )
    matches = [
        preset
        for preset in plan_presets
        if preset.get("account_size") == selected_size
    ]

    if not matches:
        st.error("No preset matches the selected company, plan and account size.")
        st.stop()
    if len(matches) > 1:
        st.warning("Multiple presets match this selection. Using the first match.")

    return matches[0]


def render_selected_preset_info(preset: dict[str, Any]) -> None:
    st.info(
        "\n".join(
            [
                f"preset_id: {preset.get('preset_id')}",
                f"company: {preset.get('company')}",
                f"plan: {preset.get('plan')}",
                f"account_name: {preset.get('account_name')}",
                f"account_size: {format_account_size(preset.get('account_size'))}",
                f"Runnable: {'Yes' if preset.get('is_runnable') else 'No'}",
                f"Verified: {'Yes' if preset.get('rules_verified') else 'No'}",
            ]
        )
    )

    missing_fields = preset.get("missing_fields", [])
    if missing_fields:
        shown_fields = ", ".join(missing_fields[:8])
        remaining = len(missing_fields) - 8
        suffix = f" and {remaining} more" if remaining > 0 else ""
        st.warning(f"Preset is not runnable. Missing fields: {shown_fields}{suffix}.")


def _account_size_sort_key(size: Any) -> float:
    try:
        return float(size)
    except (TypeError, ValueError):
        return float("inf")


def _default_index(options: list[Any], preferred_value: Any) -> int:
    try:
        return options.index(preferred_value)
    except ValueError:
        return 0


def _metric_row(items: list[tuple[str, Any]]) -> None:
    columns = st.columns(len(items))
    for column, (label, value) in zip(columns, items):
        column.metric(label, value)


def render_metric_grid(
    items: list[tuple[str, Any] | tuple[str, Any, str]],
    columns_per_row: int = 3,
) -> None:
    for start in range(0, len(items), columns_per_row):
        row_items = items[start : start + columns_per_row]
        columns = st.columns(columns_per_row)
        for column, item in zip(columns, row_items):
            label = item[0]
            value = item[1]
            help_text = item[2] if len(item) > 2 else None
            column.metric(label, value, help=help_text)


def _account_cost_from_config(config: dict[str, Any]) -> float | None:
    evaluation = config.get("evaluation", {})
    funded = config.get("funded", {})
    if evaluation.get("enabled", True):
        return evaluation.get("evaluation_cost")
    return funded.get("account_cost") or evaluation.get("evaluation_cost")


def _blank_to_none(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _money(value: float) -> str:
    return f"${value:,.2f}"


def format_currency_compact(value: Any) -> str:
    number = _numeric_value(value)
    sign = "-$" if number < 0 else "$"
    absolute = abs(number)
    if absolute >= 1_000_000:
        return f"{sign}{absolute / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{sign}{absolute / 1_000:.1f}K"
    return f"{sign}{absolute:,.2f}"


def format_currency_full(value: Any) -> str:
    number = _numeric_value(value)
    sign = "-$" if number < 0 else "$"
    return f"{sign}{abs(number):,.2f}"


def format_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2%}"


def format_number(value: Any) -> str:
    if value is None:
        return "N/A"
    number = float(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _format_diagnostic_money_columns(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    formatted = dataframe.copy()
    for column in columns:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(format_currency_full)
    return formatted


def _setup_summary_rows(analysis_state: dict[str, Any]) -> list[dict[str, Any]]:
    preset = analysis_state.get("selected_preset", {})
    input_config = analysis_state.get("input_configuration", {})
    risk_settings = analysis_state.get("risk_settings", {})
    return [
        {"Field": "Company", "Value": preset.get("company")},
        {"Field": "Plan", "Value": preset.get("plan")},
        {"Field": "Account size", "Value": format_account_size(preset.get("account_size"))},
        {"Field": "Strategy", "Value": analysis_state.get("selected_strategy_name")},
        {"Field": "Symbol", "Value": input_config.get("symbol")},
        {"Field": "Point value", "Value": input_config.get("point_value")},
        {"Field": "Contracts", "Value": risk_settings.get("contracts")},
        {
            "Field": "SL / TP",
            "Value": f"{risk_settings.get('stop_loss_points')} / {risk_settings.get('take_profit_points')}",
        },
        {"Field": "Bankroll", "Value": input_config.get("bankroll")},
    ]


def _configuration_rows(analysis_state: dict[str, Any]) -> list[dict[str, Any]]:
    preset = analysis_state.get("selected_preset", {})
    input_config = analysis_state.get("input_configuration", {})
    rows = [
        {"Setting": "Market data path", "Value": input_config.get("market_data_path")},
        {"Setting": "Preset ID", "Value": preset.get("preset_id")},
        {"Setting": "Company", "Value": preset.get("company")},
        {"Setting": "Plan", "Value": preset.get("plan")},
        {"Setting": "Account size", "Value": preset.get("account_size")},
        {"Setting": "Strategy", "Value": analysis_state.get("selected_strategy_name")},
    ]
    rows.extend(_dict_rows("Strategy", analysis_state.get("strategy_params", {})))
    rows.extend(_dict_rows("Risk", analysis_state.get("risk_settings", {})))
    rows.extend(_dict_rows("Costs", input_config.get("cost_settings", {})))
    rows.extend(_dict_rows("Time", input_config.get("time_filters", {})))
    rows.extend(
        [
            {"Setting": "Bankroll", "Value": input_config.get("bankroll")},
            {"Setting": "Monte Carlo runs", "Value": input_config.get("monte_carlo_runs")},
            {
                "Setting": "Monte Carlo max accounts",
                "Value": input_config.get("monte_carlo_max_accounts"),
            },
        ]
    )
    return rows


def _dict_rows(prefix: str, values: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"Setting": f"{prefix}: {key}", "Value": value}
        for key, value in values.items()
    ]


def _optional_decimal(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2f}"


def _optional_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2%}"


def _numeric_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_profit_factor(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(number):
        return "N/A"
    if math.isinf(number):
        return "∞"
    return f"{number:.2f}"


def _is_infinite_profit_factor(value: Any) -> bool:
    try:
        return math.isinf(float(value))
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    main()
