from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime
from pathlib import Path
import sys
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import numpy as np
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
from onix_fondeo.strategy_presets import (
    delete_strategy_preset,
    list_strategy_presets,
    load_strategy_preset,
    save_strategy_preset,
)
from onix_fondeo.strategies.random_entry import RandomEntryStrategy
from onix_fondeo.strategies.stochastic_level import StochasticLevelStrategy
from onix_fondeo.streaks import calculate_streak_analysis


OUTPUT_DIR = Path("data/output")
RUNS_DIR = Path("data/runs")
MARKET_DATA_DIR = Path("data/market_data")
APP_SETUPS_DIR = Path("data/app_setups")
CUSTOM_MARKET_DATA_OPTION = "Custom path..."
DEFAULT_PRESET_COMPANY = "Lucid Trading"
DEFAULT_PRESET_PLAN = "LucidFlex"
DEFAULT_PRESET_ACCOUNT_SIZE = 50000
APP_VERSION = "v1.6.0-dev"


def main() -> None:
    st.set_page_config(page_title="Onix Fondeo Lab", layout="wide")
    st.title("Onix Fondeo Lab")
    st.caption("Funding account strategy analyzer")

    controls = sidebar_controls()

    if controls["run_analysis"] or st.session_state.pop("run_requested", False):
        try:
            run_analysis(controls)
        except Exception as error:
            st.error(f"Analysis failed: {error}")

    analysis_state = get_analysis_state()
    if analysis_state is None:
        render_empty_app_tabs()
        return

    render_outputs_from_state(analysis_state)


def sidebar_controls() -> dict[str, Any]:
    with st.sidebar:
        render_setup_loader()

        st.header("Market Data")
        symbol = st.text_input("Symbol", value="NQ", key="market_symbol")
        point_value = st.number_input(
            "Point value",
            min_value=0.0,
            value=20.0,
            key="point_value",
        )
        data_utc_offset = st.text_input(
            "Data UTC offset",
            value="UTC-5",
            help=(
                "Timezone of your OHLC file. Enter as UTC-5, UTC-4, UTC+0, etc. "
                "The data will be shifted so session filters work in local time."
            ),
            key="data_utc_offset",
        )
        market_data_path = market_data_file_selector()
        render_market_data_validator(market_data_path, symbol, data_utc_offset)

        st.header("Funding Preset")
        presets = list_presets()
        show_non_runnable = st.checkbox(
            "Show non-runnable presets",
            value=False,
            key="show_non_runnable_presets",
        )
        filtered_presets = filter_presets_by_runnable(presets, show_non_runnable)
        selected_preset = select_funding_preset(filtered_presets)
        selected_preset_id = selected_preset["preset_id"]
        selected_preset_runnable = selected_preset["is_runnable"]
        render_selected_preset_info(selected_preset)
        render_preset_rules_panel(selected_preset)
        comparison_enabled = st.checkbox(
            "Compare multiple presets",
            value=False,
            key="comparison_enabled",
        )
        comparison_preset_ids = []
        if comparison_enabled:
            runnable_presets = filter_presets_by_runnable(presets, show_non_runnable=False)
            comparison_options = {
                preset_option_label(preset): preset["preset_id"]
                for preset in runnable_presets
            }
            loaded_comparison_ids = st.session_state.pop("loaded_comparison_preset_ids", None)
            default_comparison_ids = loaded_comparison_ids or [selected_preset_id]
            default_labels = [
                label
                for label, preset_id in comparison_options.items()
                if preset_id in default_comparison_ids
            ]
            if (
                "comparison_preset_labels" not in st.session_state
                or loaded_comparison_ids is not None
            ):
                st.session_state["comparison_preset_labels"] = default_labels
            selected_comparison_labels = st.multiselect(
                "Presets to compare",
                options=list(comparison_options),
                key="comparison_preset_labels",
                help="Uses the same generated trades for every selected runnable preset.",
            )
            comparison_preset_ids = [
                comparison_options[label] for label in selected_comparison_labels
            ]
            if len(comparison_preset_ids) < 2:
                st.caption("Select at least two presets for a meaningful comparison.")

        st.header("Simulation Settings")
        pass_transition_wait_minutes = st.number_input(
            "Wait after PASS (min)",
            min_value=0,
            value=60,
            step=15,
            key="pass_transition_wait_minutes",
            help="Trades within this window after account transition are skipped.",
        )
        fail_transition_wait_minutes = st.number_input(
            "Wait after FAIL (min)",
            min_value=0,
            value=30,
            step=15,
            key="fail_transition_wait_minutes",
            help="Trades within this window after account transition are skipped.",
        )

        st.header("Bankroll / Risk")
        bankroll = st.number_input("Bankroll", min_value=0.0, value=3000.0, key="bankroll")
        monte_carlo_runs = st.number_input(
            "Monte Carlo runs",
            min_value=0,
            value=100,
            step=100,
            key="monte_carlo_runs",
        )
        monte_carlo_max_accounts = st.number_input(
            "Monte Carlo max accounts",
            min_value=1,
            value=100,
            step=1,
            key="monte_carlo_max_accounts",
        )

        render_setup_saver(current_controls_snapshot(locals()))

        run_analysis_button = st.button(
            "Run Analysis",
            type="primary",
            disabled=not selected_preset_runnable,
        )

    return {
        "market_data_path": market_data_path,
        "symbol": symbol,
        "point_value": point_value,
        "data_utc_offset": data_utc_offset,
        "preset_id": selected_preset_id,
        "comparison_enabled": comparison_enabled,
        "comparison_preset_ids": comparison_preset_ids,
        "pass_transition_wait_minutes": int(pass_transition_wait_minutes),
        "fail_transition_wait_minutes": int(fail_transition_wait_minutes),
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
                key="random_probability",
            ),
            "seed": st.number_input("Random seed", value=42, step=1, key="random_seed"),
        }

    return {
        "period_k": st.number_input("PeriodK", min_value=1, value=20, step=1, key="stoch_period_k"),
        "period_d": st.number_input("PeriodD", min_value=1, value=5, step=1, key="stoch_period_d"),
        "smooth": st.number_input("Smooth", min_value=1, value=3, step=1, key="stoch_smooth"),
        "oversold": st.number_input("Oversold", min_value=0.0, value=20.0, key="stoch_oversold"),
        "overbought": st.number_input("Overbought", min_value=0.0, value=80.0, key="stoch_overbought"),
        "signal_mode": st.selectbox(
            "Signal mode",
            options=["cross", "zone", "d_cross"],
            index=2,
            key="stoch_signal_mode",
        ),
        "use_d_confirmation": st.checkbox(
            "Use D confirmation",
            value=False,
            key="stoch_use_d_confirmation",
        ),
        "min_k_d_gap": st.number_input("Min K/D gap", min_value=0.0, value=0.0, key="stoch_min_k_d_gap"),
        "cooldown_bars": st.number_input(
            "Cooldown bars",
            min_value=0,
            value=0,
            step=1,
            key="stoch_cooldown_bars",
        ),
    }


def render_strategy_tab() -> None:
    st.subheader("Strategy Configuration Workspace")
    st.caption("Configure entry logic, time filters, risk per trade, and trading costs.")

    render_strategy_presets_section()

    entry_column, time_column = st.columns(2)
    with entry_column:
        st.subheader("Entry Strategy")
        strategy_name = st.selectbox(
            "Strategy",
            options=["random", "stochastic"],
            index=1,
            key="strategy_name",
        )
        _strategy_controls(strategy_name)

    with time_column:
        st.subheader("Time Filters")
        st.text_input("Strategy start time", value="09:45", key="strategy_start_time")
        st.text_input("Strategy end time", value="16:00", key="strategy_end_time")
        st.text_input("Force close time", value="16:00", key="force_close_time")

    risk_column, cost_column = st.columns(2)
    with risk_column:
        st.subheader("Risk per Trade")
        st.number_input("Contracts", min_value=0.0, value=1.0, key="contracts")
        st.number_input("Stop loss points", min_value=0.0, value=70.0, key="stop_loss_points")
        st.number_input("Take profit points", min_value=0.0, value=50.0, key="take_profit_points")
        st.number_input(
            "Max holding minutes",
            min_value=1,
            value=60,
            step=1,
            key="max_holding_minutes",
        )

    with cost_column:
        st.subheader("Costs")
        st.number_input("Commission per side", min_value=0.0, value=0.0, key="commission_per_side")
        st.number_input("Slippage points", min_value=0.0, value=0.0, key="slippage_points")
        st.number_input("Spread points", min_value=0.0, value=0.0, key="spread_points")

    update_strategy_dirty_state()
    if st.session_state.get("strategy_config_dirty", False):
        st.warning("Configuration changed - click Apply & Run to update results.")
    st.button(
        "Apply & Run Analysis",
        type="primary",
        on_click=trigger_run,
        use_container_width=True,
    )


def render_strategy_presets_section() -> None:
    with st.expander("Strategy Presets", expanded=False):
        presets = list_strategy_presets()
        preset_options = {"-- New --": None}
        for preset in presets:
            label = f"{preset.get('name', preset.get('_filename'))} ({preset.get('_filename')})"
            preset_options[label] = preset.get("_filename")

        selected_label = st.selectbox(
            "Saved strategy preset",
            options=list(preset_options),
            key="strategy_preset_selector",
        )
        selected_filename = preset_options[selected_label]
        action_columns = st.columns(2)
        load_disabled = selected_filename is None
        if action_columns[0].button("Load", disabled=load_disabled):
            preset = load_strategy_preset(selected_filename)
            apply_strategy_preset_to_session_state(preset)
            st.success("Loaded.")
            st.rerun()
        if action_columns[1].button("Delete", disabled=load_disabled):
            delete_strategy_preset(selected_filename)
            st.warning("Deleted.")
            st.rerun()

        if not presets:
            st.info("No saved presets.")

        st.divider()
        st.caption("Save current config as:")
        save_columns = st.columns([3, 1])
        preset_name = save_columns[0].text_input("Preset name", key="new_preset_name", label_visibility="collapsed")
        if save_columns[1].button("Save"):
            if not preset_name.strip():
                st.warning("Enter a preset name before saving.")
                return
            save_strategy_preset(
                preset_name.strip(),
                current_strategy_preset_config(preset_name.strip()),
            )
            st.success("Saved.")
            st.rerun()


def current_strategy_preset_config(name: str) -> dict[str, Any]:
    strategy_controls = get_strategy_controls_from_state()
    return {
        "name": name,
        "strategy_name": strategy_controls["strategy_name"],
        "strategy_params": strategy_controls["strategy_params"],
        "start_time": strategy_controls["strategy_start_time"],
        "end_time": strategy_controls["strategy_end_time"],
        "force_close_time": strategy_controls["force_close_time"],
        "contracts": strategy_controls["contracts"],
        "stop_loss_points": strategy_controls["stop_loss_points"],
        "take_profit_points": strategy_controls["take_profit_points"],
        "max_holding_minutes": strategy_controls["max_holding_minutes"],
        "commission_per_side": strategy_controls["commission_per_side"],
        "slippage_points": strategy_controls["slippage_points"],
        "spread_points": strategy_controls["spread_points"],
    }


def apply_strategy_preset_to_session_state(preset: dict[str, Any]) -> None:
    st.session_state["strategy_name"] = preset.get("strategy_name", "stochastic")
    apply_strategy_params_to_session_state(preset.get("strategy_params", {}))
    mapping = {
        "strategy_start_time": preset.get("start_time") or "",
        "strategy_end_time": preset.get("end_time") or "",
        "force_close_time": preset.get("force_close_time") or "",
        "contracts": preset.get("contracts"),
        "stop_loss_points": preset.get("stop_loss_points"),
        "take_profit_points": preset.get("take_profit_points"),
        "max_holding_minutes": preset.get("max_holding_minutes"),
        "commission_per_side": preset.get("commission_per_side"),
        "slippage_points": preset.get("slippage_points"),
        "spread_points": preset.get("spread_points"),
    }
    for key, value in mapping.items():
        if value is not None:
            st.session_state[key] = value
    st.session_state["strategy_config_dirty"] = True


def trigger_run() -> None:
    st.session_state["run_requested"] = True


def update_strategy_dirty_state() -> None:
    current_hash = strategy_config_hash(get_strategy_controls_from_state())
    last_run_hash = st.session_state.get("last_run_strategy_config_hash")
    if last_run_hash is not None and current_hash != last_run_hash:
        st.session_state["strategy_config_dirty"] = True


def strategy_config_hash(strategy_controls: dict[str, Any]) -> str:
    return json.dumps(strategy_controls, sort_keys=True, default=str)


def get_strategy_controls_from_state() -> dict[str, Any]:
    return {
        "strategy_name": st.session_state.get("strategy_name", "stochastic"),
        "strategy_params": _read_strategy_params_from_state(),
        "strategy_start_time": _blank_to_none(str(st.session_state.get("strategy_start_time", "09:45"))),
        "strategy_end_time": _blank_to_none(str(st.session_state.get("strategy_end_time", "16:00"))),
        "force_close_time": _blank_to_none(str(st.session_state.get("force_close_time", "16:00"))),
        "contracts": st.session_state.get("contracts", 1.0),
        "stop_loss_points": st.session_state.get("stop_loss_points", 70.0),
        "take_profit_points": st.session_state.get("take_profit_points", 50.0),
        "max_holding_minutes": int(st.session_state.get("max_holding_minutes", 60)),
        "commission_per_side": st.session_state.get("commission_per_side", 0.0),
        "slippage_points": st.session_state.get("slippage_points", 0.0),
        "spread_points": st.session_state.get("spread_points", 0.0),
    }


def _read_strategy_params_from_state() -> dict[str, Any]:
    strategy_name = st.session_state.get("strategy_name", "stochastic")
    if strategy_name == "random":
        return {
            "probability": st.session_state.get("random_probability", 0.005),
            "seed": st.session_state.get("random_seed", 42),
        }
    return {
        "period_k": st.session_state.get("stoch_period_k", 20),
        "period_d": st.session_state.get("stoch_period_d", 5),
        "smooth": st.session_state.get("stoch_smooth", 3),
        "oversold": st.session_state.get("stoch_oversold", 20.0),
        "overbought": st.session_state.get("stoch_overbought", 80.0),
        "signal_mode": st.session_state.get("stoch_signal_mode", "d_cross"),
        "use_d_confirmation": st.session_state.get("stoch_use_d_confirmation", False),
        "min_k_d_gap": st.session_state.get("stoch_min_k_d_gap", 0.0),
        "cooldown_bars": st.session_state.get("stoch_cooldown_bars", 0),
    }


def run_analysis(controls: dict[str, Any]) -> None:
    controls = {**controls, **get_strategy_controls_from_state()}
    if controls["preset_id"] is None:
        st.error("No preset selected.")
        return

    preset = load_preset(controls["preset_id"])
    is_runnable, missing_fields = validate_preset_is_runnable(preset)
    if not is_runnable:
        st.error("Selected preset is not runnable.")
        st.write(missing_fields)
        return

    ohlc = load_ohlc_data(
        controls["market_data_path"],
        symbol=controls["symbol"],
        timezone=controls.get("data_utc_offset"),
    )
    market_data_summary = build_market_data_summary(ohlc, controls["market_data_path"])
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
    apply_app_simulation_settings(config, controls)
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
            pass_transition_wait_minutes=controls.get("pass_transition_wait_minutes", 0),
            fail_transition_wait_minutes=controls.get("fail_transition_wait_minutes", 0),
        )
        if not comparison_rows:
            st.warning("No runnable presets were available for comparison.")
    account_event_timeline = build_account_event_timeline(results)
    account_summary = build_account_summary(results)
    account_rule_audit = build_account_rule_audit(results)
    account_cycle_registry = build_account_cycle_registry(
        results=results,
        preset=preset,
        controls=controls,
        config=config,
        account_rule_audit=account_rule_audit,
    )

    exported_files = export_app_outputs(
        trades,
        strategy_metrics,
        business_metrics,
        bankroll_result,
        streak_analysis,
        risk_result,
        required_bankroll,
        comparison_rows,
        controls,
        preset,
        config,
        market_data_summary,
        account_event_timeline,
        account_summary,
        account_rule_audit,
        account_cycle_registry,
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
        market_data_summary,
        account_event_timeline,
        account_summary,
        account_rule_audit,
        account_cycle_registry,
    )
    st.session_state["last_run_strategy_config_hash"] = strategy_config_hash(
        get_strategy_controls_from_state()
    )
    st.session_state["strategy_config_dirty"] = False


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


def apply_app_simulation_settings(config: dict[str, Any], controls: dict[str, Any]) -> None:
    simulation = config.setdefault("simulation", {})
    simulation["pass_transition_wait_minutes"] = controls.get("pass_transition_wait_minutes", 0)
    simulation["fail_transition_wait_minutes"] = controls.get("fail_transition_wait_minutes", 0)


def render_setup_loader() -> None:
    st.header("Setups")
    with st.expander("Load saved setup", expanded=False):
        setup_paths = saved_setup_files()
        if not setup_paths:
            st.info("No saved setups yet.")
            return
        selected_path = st.selectbox(
            "Saved setup",
            options=setup_paths,
            format_func=lambda path: path.stem,
            key="saved_setup_path",
        )
        columns = st.columns(2)
        if columns[0].button("Load setup"):
            setup = load_app_setup(selected_path)
            apply_setup_to_session_state(setup)
            st.success(f"Loaded setup: {selected_path.stem}")
            st.rerun()
        if columns[1].button("Delete setup"):
            selected_path.unlink(missing_ok=True)
            st.warning(f"Deleted setup: {selected_path.stem}")
            st.rerun()


def render_setup_saver(controls_snapshot: dict[str, Any]) -> None:
    with st.expander("Save current setup", expanded=False):
        setup_name = st.text_input("Setup name", value="", key="setup_save_name")
        if st.button("Save setup"):
            if not setup_name.strip():
                st.warning("Enter a setup name before saving.")
                return
            output_path = save_app_setup(setup_name, controls_snapshot)
            st.success(f"Saved setup: {output_path.name}")


def current_controls_snapshot(local_values: dict[str, Any]) -> dict[str, Any]:
    bankroll = local_values.get("bankroll")
    strategy_values = get_strategy_controls_from_state()
    return {
        "version": 1,
        "market_data_path": local_values.get("market_data_path"),
        "symbol": local_values.get("symbol"),
        "point_value": local_values.get("point_value"),
        "data_utc_offset": local_values.get("data_utc_offset"),
        "preset_id": local_values.get("selected_preset_id"),
        "comparison_enabled": local_values.get("comparison_enabled"),
        "comparison_preset_ids": local_values.get("comparison_preset_ids", []),
        "strategy_name": strategy_values.get("strategy_name"),
        "strategy_params": strategy_values.get("strategy_params", {}),
        "strategy_start_time": strategy_values.get("strategy_start_time"),
        "strategy_end_time": strategy_values.get("strategy_end_time"),
        "force_close_time": strategy_values.get("force_close_time"),
        "contracts": strategy_values.get("contracts"),
        "stop_loss_points": strategy_values.get("stop_loss_points"),
        "take_profit_points": strategy_values.get("take_profit_points"),
        "max_holding_minutes": int(strategy_values.get("max_holding_minutes", 60)),
        "pass_transition_wait_minutes": int(local_values.get("pass_transition_wait_minutes", 0)),
        "fail_transition_wait_minutes": int(local_values.get("fail_transition_wait_minutes", 0)),
        "commission_per_side": strategy_values.get("commission_per_side"),
        "slippage_points": strategy_values.get("slippage_points"),
        "spread_points": strategy_values.get("spread_points"),
        "bankroll": bankroll if bankroll and bankroll > 0 else None,
        "monte_carlo_runs": int(local_values.get("monte_carlo_runs", 0)),
        "monte_carlo_max_accounts": int(local_values.get("monte_carlo_max_accounts", 100)),
    }


def saved_setup_files(directory: Path = APP_SETUPS_DIR) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"), key=lambda path: path.stem.lower())


def save_app_setup(
    setup_name: str,
    controls_snapshot: dict[str, Any],
    directory: Path = APP_SETUPS_DIR,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / f"{slugify_setup_name(setup_name)}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(controls_snapshot, file, indent=2, default=str)
    return output_path


def load_app_setup(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def apply_setup_to_session_state(setup: dict[str, Any]) -> None:
    market_data_path = setup.get("market_data_path")
    if market_data_path:
        file_options = market_data_file_options()
        if market_data_path in file_options:
            st.session_state["market_data_file_option"] = market_data_path
        else:
            st.session_state["market_data_file_option"] = CUSTOM_MARKET_DATA_OPTION
            st.session_state["custom_market_data_path"] = market_data_path

    direct_widget_values = {
        "market_symbol": setup.get("symbol"),
        "point_value": setup.get("point_value"),
        "data_utc_offset": setup.get("data_utc_offset"),
        "comparison_enabled": setup.get("comparison_enabled"),
        "strategy_name": setup.get("strategy_name"),
        "strategy_start_time": setup.get("strategy_start_time") or "",
        "strategy_end_time": setup.get("strategy_end_time") or "",
        "force_close_time": setup.get("force_close_time") or "",
        "contracts": setup.get("contracts"),
        "stop_loss_points": setup.get("stop_loss_points"),
        "take_profit_points": setup.get("take_profit_points"),
        "max_holding_minutes": setup.get("max_holding_minutes"),
        "pass_transition_wait_minutes": setup.get("pass_transition_wait_minutes"),
        "fail_transition_wait_minutes": setup.get("fail_transition_wait_minutes"),
        "commission_per_side": setup.get("commission_per_side"),
        "slippage_points": setup.get("slippage_points"),
        "spread_points": setup.get("spread_points"),
        "bankroll": setup.get("bankroll") or 0.0,
        "monte_carlo_runs": setup.get("monte_carlo_runs"),
        "monte_carlo_max_accounts": setup.get("monte_carlo_max_accounts"),
    }
    for key, value in direct_widget_values.items():
        if value is not None:
            st.session_state[key] = value

    apply_strategy_params_to_session_state(setup.get("strategy_params", {}))
    apply_preset_to_session_state(setup.get("preset_id"))
    st.session_state["loaded_comparison_preset_ids"] = setup.get(
        "comparison_preset_ids",
        [],
    )


def apply_strategy_params_to_session_state(strategy_params: dict[str, Any]) -> None:
    mapping = {
        "probability": "random_probability",
        "seed": "random_seed",
        "period_k": "stoch_period_k",
        "period_d": "stoch_period_d",
        "smooth": "stoch_smooth",
        "oversold": "stoch_oversold",
        "overbought": "stoch_overbought",
        "signal_mode": "stoch_signal_mode",
        "use_d_confirmation": "stoch_use_d_confirmation",
        "min_k_d_gap": "stoch_min_k_d_gap",
        "cooldown_bars": "stoch_cooldown_bars",
    }
    for param_name, widget_key in mapping.items():
        if param_name in strategy_params:
            st.session_state[widget_key] = strategy_params[param_name]


def apply_preset_to_session_state(preset_id: str | None) -> None:
    if not preset_id:
        return
    try:
        preset = load_preset(preset_id)
    except ValueError:
        return
    st.session_state["preset_company"] = preset.get("company") or DEFAULT_PRESET_COMPANY
    st.session_state["preset_plan"] = preset.get("plan") or DEFAULT_PRESET_PLAN
    st.session_state["preset_account_size"] = preset.get("account_size") or DEFAULT_PRESET_ACCOUNT_SIZE


def slugify_setup_name(name: str) -> str:
    slug = "".join(
        character.lower() if character.isalnum() else "_"
        for character in name.strip()
    ).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "setup"


def market_data_file_selector() -> str:
    file_options = market_data_file_options()
    default_path = str(MARKET_DATA_DIR / "sample_NQ_1m.csv")
    default_option = default_path if default_path in file_options else CUSTOM_MARKET_DATA_OPTION
    options = file_options + [CUSTOM_MARKET_DATA_OPTION]
    _ensure_widget_choice("market_data_file_option", options, default_option)
    selected_option = st.selectbox(
        "OHLC file",
        options=options,
        index=_default_index(options, default_option),
        format_func=market_data_option_label,
        key="market_data_file_option",
    )
    if selected_option == CUSTOM_MARKET_DATA_OPTION:
        return st.text_input(
            "Custom OHLC CSV path",
            value=default_path,
            key="custom_market_data_path",
        )
    st.caption(selected_option)
    return selected_option


def market_data_file_options(directory: Path = MARKET_DATA_DIR) -> list[str]:
    if not directory.exists():
        return []
    return [
        str(path.as_posix())
        for path in sorted(directory.glob("*.csv"), key=lambda item: item.name.lower())
        if path.is_file()
    ]


def market_data_option_label(option: str) -> str:
    if option == CUSTOM_MARKET_DATA_OPTION:
        return option
    try:
        path = Path(option)
        return f"{path.name} ({path.parent.as_posix()})"
    except TypeError:
        return str(option)


def render_market_data_validator(file_path: str, symbol: str, timezone: str | None = None) -> None:
    with st.expander("Validate market data", expanded=False):
        st.caption("Checks format, numeric prices and OHLC integrity before running.")
        if st.button("Validate OHLC file"):
            st.session_state["market_data_validation"] = validate_market_data_file(
                file_path,
                symbol,
                timezone,
            )
        validation = st.session_state.get("market_data_validation")
        if not validation:
            return
        if validation["ok"]:
            st.success("OHLC file is valid.")
            st.dataframe(
                pd.DataFrame(_market_data_summary_rows(validation["summary"])),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.error(validation["error"])


def validate_market_data_file(
    file_path: str,
    symbol: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    try:
        ohlc = load_ohlc_data(file_path, symbol=symbol, timezone=timezone)
    except Exception as error:
        return {"ok": False, "error": str(error), "summary": None}
    return {
        "ok": True,
        "error": None,
        "summary": build_market_data_summary(ohlc, file_path),
    }


def build_market_data_summary(ohlc: pd.DataFrame, file_path: str | None = None) -> dict[str, Any]:
    if ohlc.empty:
        return {
            "file_path": file_path,
            "rows": 0,
            "start": None,
            "end": None,
            "trading_days": 0,
            "symbols": "",
            "time_start": None,
            "time_end": None,
            "close_min": None,
            "close_max": None,
            "timezone": ohlc.attrs.get("timezone"),
        }

    data = ohlc.copy()
    date_time = pd.to_datetime(data["DateTime"], errors="coerce")
    symbols = ""
    if "Symbol" in data.columns:
        symbols = ", ".join(sorted({str(value) for value in data["Symbol"].dropna().unique()}))

    return {
        "file_path": file_path,
        "rows": int(len(data)),
        "start": date_time.min(),
        "end": date_time.max(),
        "trading_days": int(date_time.dt.date.nunique()),
        "symbols": symbols,
        "time_start": None if date_time.dropna().empty else str(date_time.dt.time.min()),
        "time_end": None if date_time.dropna().empty else str(date_time.dt.time.max()),
        "close_min": float(pd.to_numeric(data["Close"], errors="coerce").min()),
        "close_max": float(pd.to_numeric(data["Close"], errors="coerce").max()),
        "timezone": ohlc.attrs.get("timezone"),
    }


def _market_data_summary_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"Metric": "File", "Value": summary.get("file_path")},
        {"Metric": "Rows", "Value": format_number(summary.get("rows"))},
        {"Metric": "Start", "Value": _optional_datetime(summary.get("start"))},
        {"Metric": "End", "Value": _optional_datetime(summary.get("end"))},
        {"Metric": "Trading days", "Value": format_number(summary.get("trading_days"))},
        {"Metric": "Symbols", "Value": summary.get("symbols") or "N/A"},
        {
            "Metric": "Time range",
            "Value": f"{summary.get('time_start') or 'N/A'} - {summary.get('time_end') or 'N/A'}",
        },
        {
            "Metric": "Close range",
            "Value": (
                f"{_optional_decimal(summary.get('close_min'))} - "
                f"{_optional_decimal(summary.get('close_max'))}"
            ),
        },
        {"Metric": "Timezone", "Value": summary.get("timezone") or "N/A"},
    ]


def run_app_preset_comparison(
    trades: pd.DataFrame,
    preset_ids: list[str],
    bankroll: float | None,
    monte_carlo_runs: int,
    monte_carlo_max_accounts: int,
    pass_transition_wait_minutes: int = 0,
    fail_transition_wait_minutes: int = 0,
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
        apply_app_simulation_settings(
            config,
            {
                "pass_transition_wait_minutes": pass_transition_wait_minutes,
                "fail_transition_wait_minutes": fail_transition_wait_minutes,
            },
        )
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


def build_account_event_timeline(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    accounts_by_id_phase = {
        (account.account_id, account.phase): account
        for account in results.get("accounts", [])
    }

    for account in results.get("accounts", []):
        rows.append(
            account_timeline_row(
                time=account.started_at,
                account_id=account.account_id,
                phase=account.phase,
                event_type="ACCOUNT_OPENED",
                status=account.status,
                pnl=account.pnl,
            )
        )
        if account.status != "ACTIVE" or account.ended_at is not None:
            event_type = "ACCOUNT_PASSED" if account.status == "PASSED" else "ACCOUNT_FAILED"
            rows.append(
                account_timeline_row(
                    time=account.ended_at,
                    account_id=account.account_id,
                    phase=account.phase,
                    event_type=event_type,
                    status=account.status,
                    pnl=account.pnl,
                    reason=account.result_reason,
                )
            )

    payout_lookup = {
        (payout.account_id, str(payout.payout_time)): payout
        for payout in results.get("payouts", [])
    }
    for event in results.get("business_events", []):
        payout = payout_lookup.get((event.get("account_id"), str(event.get("time"))))
        rows.append(
            account_timeline_row(
                time=event.get("time"),
                account_id=event.get("account_id"),
                phase=account_phase_for_event(event, accounts_by_id_phase),
                event_type=event.get("type"),
                amount=event.get("amount"),
                reason=payout_reason(payout),
            )
        )

    seen_reasons: set[tuple[Any, Any, str]] = set()
    for trade_event in results.get("trade_log", []):
        reason = trade_event.get("StatusReason")
        if not reason:
            continue
        key = (
            trade_event.get("AccountID"),
            trade_event.get("TradeID"),
            str(reason),
        )
        if key in seen_reasons:
            continue
        seen_reasons.add(key)
        rows.append(
            account_timeline_row(
                time=trade_event.get("TradeTime"),
                account_id=trade_event.get("AccountID"),
                phase=trade_event.get("Phase"),
                event_type=trade_log_event_type(reason),
                trade_id=trade_event.get("TradeID"),
                status=trade_event.get("StatusAfterTrade"),
                amount=trade_event.get("AppliedNetPnL"),
                pnl=trade_event.get("AccountPnL"),
                reason=reason,
            )
        )

    rows = sorted(rows, key=account_event_sort_key)
    for index, row in enumerate(rows, start=1):
        row["Step"] = index
    return rows


def build_account_summary(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for account in results.get("accounts", []):
        payouts = account.payouts
        total_gross_payout = sum(payout.gross_payout for payout in payouts)
        total_net_payout = sum(payout.net_payout for payout in payouts)
        rows.append(
            {
                "AccountID": account.account_id,
                "Phase": account.phase,
                "Status": account.status,
                "FinalPnL": account.pnl,
                "HighWatermark": account.high_watermark,
                "TradingDays": len(account.trading_days),
                "TradesCount": account.trades_count,
                "StartedAt": account.started_at,
                "EndedAt": account.ended_at,
                "ResultReason": account.result_reason,
                "PayoutsCount": len(payouts),
                "TotalGrossPayout": total_gross_payout,
                "TotalNetPayout": total_net_payout,
                "DrawdownFloor": account.trailing_drawdown_floor,
                "EODHighPnL": account.eod_high_pnl,
                "DrawdownLocked": account.drawdown_locked,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["AccountID"],
            0 if row["Phase"] == "EVALUATION" else 1,
        ),
    )


def build_account_rule_audit(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade_event in results.get("trade_log", []):
        reason = trade_event.get("StatusReason") or trade_event.get("AccountAwareExitReason")
        if not reason:
            continue
        for rule_type in rule_types_for_reason(str(reason)):
            rows.append(
                account_rule_audit_row(
                    time=trade_event.get("TradeTime"),
                    account_id=trade_event.get("AccountID"),
                    phase=trade_event.get("Phase"),
                    rule_type=rule_type,
                    rule_group=account_rule_group(rule_type),
                    trade_id=trade_event.get("TradeID"),
                    status=trade_event.get("StatusAfterTrade"),
                    original_net_pnl=trade_event.get("OriginalNetPnL"),
                    applied_net_pnl=trade_event.get("AppliedNetPnL"),
                    account_pnl=trade_event.get("AccountPnL"),
                    reason=reason,
                    severity=account_rule_severity(rule_type),
                )
            )

    for account in results.get("accounts", []):
        if account.result_reason:
            rule_type = trade_log_event_type(str(account.result_reason))
            if rule_type == "STATUS_REASON":
                rule_type = "ACCOUNT_RESULT"
            rows.append(
                account_rule_audit_row(
                    time=account.ended_at,
                    account_id=account.account_id,
                    phase=account.phase,
                    rule_type=rule_type,
                    rule_group=account_rule_group(rule_type),
                    status=account.status,
                    account_pnl=account.pnl,
                    reason=account.result_reason,
                    severity=account_rule_severity(rule_type),
                )
            )

    rows = sorted(rows, key=account_rule_audit_sort_key)
    for index, row in enumerate(rows, start=1):
        row["Step"] = index
    return rows


def build_account_cycle_registry(
    results: dict[str, Any],
    preset: dict[str, Any],
    controls: dict[str, Any],
    config: dict[str, Any],
    account_rule_audit: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    trade_log = pd.DataFrame(results.get("trade_log", []))
    rule_audit = pd.DataFrame(account_rule_audit)
    rows: list[dict[str, Any]] = []
    for cycle_number, account in enumerate(
        sorted(
            results.get("accounts", []),
            key=lambda item: (item.account_id, 0 if item.phase == "EVALUATION" else 1),
        ),
        start=1,
    ):
        account_trades = _account_phase_rows(trade_log, account.account_id, account.phase)
        account_rules = _account_phase_rows(rule_audit, account.account_id, account.phase)
        rows.append(
            account_cycle_registry_row(
                cycle_number=cycle_number,
                account=account,
                account_trades=account_trades,
                account_rules=account_rules,
                preset=preset,
                controls=controls,
                config=config,
            )
        )
    return rows


def account_cycle_registry_row(
    cycle_number: int,
    account: Any,
    account_trades: pd.DataFrame,
    account_rules: pd.DataFrame,
    preset: dict[str, Any],
    controls: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    phase_rules = config.get("evaluation", {}) if account.phase == "EVALUATION" else config.get("funded", {})
    target_or_trigger = (
        phase_rules.get("profit_target")
        if account.phase == "EVALUATION"
        else phase_rules.get("payout_trigger_profit")
    )
    max_drawdown = phase_rules.get("max_drawdown")
    applied_pnl = _numeric_column(account_trades, "AppliedNetPnL")
    original_pnl = _numeric_column(account_trades, "OriginalNetPnL")
    wins = int((applied_pnl > 0).sum())
    losses = int((applied_pnl < 0).sum())
    payouts = getattr(account, "payouts", [])
    daily_pnl = getattr(account, "daily_pnl", {})
    session_stats = account_cycle_session_stats(account_trades)
    rule_counts = account_cycle_rule_counts(account_rules)
    row = {
        "CycleNumber": cycle_number,
        "PresetID": preset.get("preset_id"),
        "Company": preset.get("company"),
        "Plan": preset.get("plan"),
        "AccountName": preset.get("account_name"),
        "AccountSize": preset.get("account_size"),
        "AccountID": account.account_id,
        "Phase": account.phase,
        "Status": account.status,
        "ResultReason": account.result_reason,
        "StartedAt": account.started_at,
        "EarliestTradeTime": getattr(account, "earliest_trade_time", None),
        "EndedAt": account.ended_at,
        "CalendarDays": calendar_days_between(account.started_at, account.ended_at),
        "TradingDays": len(getattr(account, "trading_days", set())),
        "TradesCount": int(len(account_trades)) if not account_trades.empty else account.trades_count,
        "Wins": wins,
        "Losses": losses,
        "WinRate": _safe_divide_number(wins, wins + losses),
        "OriginalNetPnL": float(original_pnl.sum()) if not original_pnl.empty else 0.0,
        "AppliedNetPnL": float(applied_pnl.sum()) if not applied_pnl.empty else 0.0,
        "FinalPnL": account.pnl,
        "HighWatermark": account.high_watermark,
        "TargetOrPayoutTrigger": target_or_trigger,
        "DistanceToTarget": distance_to_target(account.pnl, target_or_trigger),
        "DistanceToDrawdown": distance_to_drawdown(account.pnl, max_drawdown, account.trailing_drawdown_floor),
        "DrawdownFloor": account.trailing_drawdown_floor,
        "EODHighPnL": account.eod_high_pnl,
        "DrawdownLocked": account.drawdown_locked,
        "BestDayPnL": max(daily_pnl.values()) if daily_pnl else 0.0,
        "WorstDayPnL": min(daily_pnl.values()) if daily_pnl else 0.0,
        "BestTradePnL": float(applied_pnl.max()) if not applied_pnl.empty else 0.0,
        "WorstTradePnL": float(applied_pnl.min()) if not applied_pnl.empty else 0.0,
        "PayoutsCount": len(payouts),
        "TotalGrossPayout": sum(payout.gross_payout for payout in payouts),
        "TotalNetPayout": sum(payout.net_payout for payout in payouts),
        "Strategy": controls.get("strategy_name"),
        "StrategyParams": json.dumps(controls.get("strategy_params", {}), default=str),
        "Contracts": controls.get("contracts"),
        "StopLossPoints": controls.get("stop_loss_points"),
        "TakeProfitPoints": controls.get("take_profit_points"),
        "MaxHoldingMinutes": controls.get("max_holding_minutes"),
        "CommissionPerSide": controls.get("commission_per_side"),
        "SlippagePoints": controls.get("slippage_points"),
        "SpreadPoints": controls.get("spread_points"),
        "MarketDataPath": controls.get("market_data_path"),
        "Symbol": controls.get("symbol"),
        "PointValue": controls.get("point_value"),
        "DataUTCOffset": controls.get("data_utc_offset"),
    }
    row.update(rule_counts)
    row.update(session_stats)
    return row


def _account_phase_rows(dataframe: pd.DataFrame, account_id: Any, phase: str) -> pd.DataFrame:
    if dataframe.empty or "AccountID" not in dataframe.columns or "Phase" not in dataframe.columns:
        return pd.DataFrame()
    return dataframe[
        (dataframe["AccountID"] == account_id)
        & (dataframe["Phase"].astype(str) == str(phase))
    ].copy()


def account_cycle_rule_counts(account_rules: pd.DataFrame) -> dict[str, int]:
    rule_types = account_rules.get("RuleType", pd.Series(dtype=str)).astype(str)
    return {
        "AccountAwareExitsCount": int(rule_types.isin([
            "EVALUATION_TARGET_REACHED",
            "FUNDED_PAYOUT_TRIGGER_REACHED",
            "ACCOUNT_MAX_LOSS",
            "ACCOUNT_DAILY_LOSS",
        ]).sum()),
        "EvaluationTargetReachedCount": int((rule_types == "EVALUATION_TARGET_REACHED").sum()),
        "FundedPayoutTriggerReachedCount": int((rule_types == "FUNDED_PAYOUT_TRIGGER_REACHED").sum()),
        "MaxLossEventsCount": int((rule_types == "ACCOUNT_MAX_LOSS").sum()),
        "DailyLossEventsCount": int((rule_types == "ACCOUNT_DAILY_LOSS").sum()),
        "ConsistencyBlocksCount": int((rule_types == "PAYOUT_BLOCKED_CONSISTENCY").sum()),
        "WinningDaysBlocksCount": int((rule_types == "PAYOUT_BLOCKED_WINNING_DAYS").sum()),
        "DailyContinuityBlocksCount": int((rule_types == "PAYOUT_BLOCKED_DAILY_CONTINUITY").sum()),
    }


def account_cycle_session_stats(account_trades: pd.DataFrame) -> dict[str, float | int]:
    stats: dict[str, float | int] = {}
    sessions = ["Morning", "Midday", "Afternoon", "Evening", "Overnight"]
    for session in sessions:
        key = session.replace(" ", "")
        stats[f"{key}Trades"] = 0
        stats[f"{key}NetPnL"] = 0.0
    if account_trades.empty:
        return stats

    trade_time = _datetime_column(account_trades, "TradeTime")
    pnl = _numeric_column(account_trades, "AppliedNetPnL")
    session_frame = pd.DataFrame(
        {
            "Session": trade_time.dt.hour.apply(classify_session_hour),
            "AppliedNetPnL": pnl,
        }
    ).dropna(subset=["Session"])
    for session, group in session_frame.groupby("Session"):
        key = session.replace(" ", "")
        stats[f"{key}Trades"] = int(len(group))
        stats[f"{key}NetPnL"] = float(group["AppliedNetPnL"].sum())
    return stats


def distance_to_target(current_pnl: float, target: Any) -> float | None:
    if target is None:
        return None
    return max(0.0, float(target) - float(current_pnl))


def distance_to_drawdown(
    current_pnl: float,
    max_drawdown: Any,
    drawdown_floor: Any,
) -> float | None:
    if drawdown_floor is not None and not pd.isna(drawdown_floor):
        return float(current_pnl) - float(drawdown_floor)
    if max_drawdown is None:
        return None
    return float(current_pnl) + abs(float(max_drawdown))


def calendar_days_between(started_at: Any, ended_at: Any) -> int | None:
    if started_at is None or ended_at is None:
        return None
    start = pd.to_datetime(started_at, errors="coerce")
    end = pd.to_datetime(ended_at, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return None
    return max(0, int((end.date() - start.date()).days) + 1)


def account_rule_audit_row(
    time: Any,
    account_id: Any,
    phase: Any,
    rule_type: str,
    rule_group: str,
    trade_id: Any = None,
    status: Any = None,
    original_net_pnl: Any = None,
    applied_net_pnl: Any = None,
    account_pnl: Any = None,
    reason: Any = None,
    severity: str = "Info",
) -> dict[str, Any]:
    return {
        "Step": None,
        "Time": time,
        "AccountID": account_id,
        "Phase": phase,
        "RuleGroup": rule_group,
        "RuleType": rule_type,
        "Severity": severity,
        "TradeID": trade_id,
        "OriginalNetPnL": original_net_pnl,
        "AppliedNetPnL": applied_net_pnl,
        "AccountPnL": account_pnl,
        "Status": status,
        "Reason": reason,
    }


def rule_types_for_reason(reason: str) -> list[str]:
    candidates = [
        "EVALUATION_TARGET_REACHED",
        "FUNDED_PAYOUT_TRIGGER_REACHED",
        "ACCOUNT_MAX_LOSS",
        "ACCOUNT_DAILY_LOSS",
    ]
    rule_types = [candidate for candidate in candidates if candidate in reason]
    lower_reason = reason.lower()
    if "consistency" in lower_reason:
        rule_types.append("PAYOUT_BLOCKED_CONSISTENCY")
    if "Winning days" in reason:
        rule_types.append("PAYOUT_BLOCKED_WINNING_DAYS")
    if "Daily continuity" in reason:
        rule_types.append("PAYOUT_BLOCKED_DAILY_CONTINUITY")
    return rule_types or [trade_log_event_type(reason)]


def account_rule_group(rule_type: str) -> str:
    if rule_type in {"EVALUATION_TARGET_REACHED", "FUNDED_PAYOUT_TRIGGER_REACHED"}:
        return "Target / Payout Trigger"
    if rule_type in {"ACCOUNT_MAX_LOSS", "ACCOUNT_DAILY_LOSS"}:
        return "Loss Limit"
    if rule_type.startswith("PAYOUT_BLOCKED"):
        return "Payout Eligibility"
    if rule_type in {"ACCOUNT_RESULT", "ACCOUNT_FAILED"}:
        return "Account Result"
    return "Status"


def account_rule_severity(rule_type: str) -> str:
    if rule_type in {"ACCOUNT_MAX_LOSS", "ACCOUNT_DAILY_LOSS", "ACCOUNT_FAILED"}:
        return "Critical"
    if rule_type.startswith("PAYOUT_BLOCKED"):
        return "Warning"
    if rule_type in {"EVALUATION_TARGET_REACHED", "FUNDED_PAYOUT_TRIGGER_REACHED"}:
        return "Positive"
    return "Info"


def account_rule_audit_sort_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    time_value = row.get("Time")
    sort_time = pd.to_datetime(time_value, errors="coerce")
    if pd.isna(sort_time):
        sort_time = pd.Timestamp.min
    account_id = row.get("AccountID")
    account_id = -1 if account_id is None or pd.isna(account_id) else account_id
    return (sort_time, account_id, str(row.get("RuleType")))


def account_timeline_row(
    time: Any,
    account_id: Any,
    phase: Any,
    event_type: Any,
    amount: Any = None,
    pnl: Any = None,
    status: Any = None,
    reason: Any = None,
    trade_id: Any = None,
) -> dict[str, Any]:
    return {
        "Step": None,
        "Time": time,
        "AccountID": account_id,
        "Phase": phase,
        "EventType": event_type,
        "TradeID": trade_id,
        "Amount": amount,
        "AccountPnL": pnl,
        "Status": status,
        "Reason": reason,
    }


def account_phase_for_event(
    event: dict[str, Any],
    accounts_by_id_phase: dict[tuple[Any, str], Any],
) -> str | None:
    account_id = event.get("account_id")
    event_type = event.get("type")
    if event_type == "EVALUATION_COST":
        return "EVALUATION"
    if event_type == "PAYOUT":
        return "FUNDED"
    for phase in ["EVALUATION", "FUNDED"]:
        if (account_id, phase) in accounts_by_id_phase:
            return phase
    return None


def payout_reason(payout: Any | None) -> str | None:
    if payout is None:
        return None
    return (
        f"Gross payout {format_currency_full(payout.gross_payout)}; "
        f"net payout {format_currency_full(payout.net_payout)}"
    )


def trade_log_event_type(reason: str) -> str:
    if "EVALUATION_TARGET_REACHED" in reason:
        return "EVALUATION_TARGET_REACHED"
    if "FUNDED_PAYOUT_TRIGGER_REACHED" in reason:
        return "FUNDED_PAYOUT_TRIGGER_REACHED"
    if "ACCOUNT_MAX_LOSS" in reason:
        return "ACCOUNT_MAX_LOSS"
    if "ACCOUNT_DAILY_LOSS" in reason:
        return "ACCOUNT_DAILY_LOSS"
    if "consistency" in reason.lower():
        return "PAYOUT_BLOCKED_CONSISTENCY"
    if "Winning days" in reason:
        return "PAYOUT_BLOCKED_WINNING_DAYS"
    if "Daily continuity" in reason:
        return "PAYOUT_BLOCKED_DAILY_CONTINUITY"
    return "STATUS_REASON"


def account_event_sort_key(row: dict[str, Any]) -> tuple[int, Any, Any, str]:
    time_value = row.get("Time")
    if time_value is None or pd.isna(time_value):
        sort_time = pd.Timestamp.min
    else:
        sort_time = pd.to_datetime(time_value, errors="coerce")
        if pd.isna(sort_time):
            sort_time = pd.Timestamp.min
    account_id = row.get("AccountID")
    account_id = -1 if account_id is None or pd.isna(account_id) else account_id
    return (0, sort_time, account_id, str(row.get("EventType")))


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
    market_data_summary: dict[str, Any] | None = None,
    account_event_timeline: list[dict[str, Any]] | None = None,
    account_summary: list[dict[str, Any]] | None = None,
    account_rule_audit: list[dict[str, Any]] | None = None,
    account_cycle_registry: list[dict[str, Any]] | None = None,
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
        "market_data_summary": market_data_summary,
        "account_event_timeline": account_event_timeline or [],
        "account_summary": account_summary or [],
        "account_rule_audit": account_rule_audit or [],
        "account_cycle_registry": account_cycle_registry or [],
        "exported_files": exported_files,
        "selected_preset": {
            "preset_id": preset.get("preset_id"),
            "company": preset.get("company"),
            "plan": preset.get("plan"),
            "account_name": preset.get("account_name"),
            "account_size": preset.get("account_size"),
            "is_official": preset.get("is_official"),
            "rules_verified": preset.get("rules_verified"),
            "source_url": preset.get("source_url"),
            "last_verified_at": preset.get("last_verified_at"),
            "notes": preset.get("notes"),
        },
        "selected_preset_rules": build_preset_rules_summary(preset),
        "selected_strategy_name": controls.get("strategy_name"),
        "strategy_params": controls.get("strategy_params", {}),
        "input_configuration": {
            "market_data_path": controls.get("market_data_path"),
            "symbol": controls.get("symbol"),
            "point_value": controls.get("point_value"),
            "data_utc_offset": controls.get("data_utc_offset"),
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
            "simulation_settings": {
                "pass_transition_wait_minutes": controls.get("pass_transition_wait_minutes"),
                "fail_transition_wait_minutes": controls.get("fail_transition_wait_minutes"),
            },
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


def render_empty_app_tabs() -> None:
    active_tab = render_results_tab_selector()
    if active_tab == "Dashboard":
        st.info("Configure the sidebar and Strategy tab, then click Run Analysis.")
    elif active_tab == "Strategy":
        render_strategy_tab()
    elif active_tab == "Backtest":
        st.info("Run an analysis to explore trades and charts.")
    elif active_tab == "Funding & Risk":
        st.info("Run an analysis to review funding, bankroll, and risk results.")
    elif active_tab == "Data":
        st.info("Run an analysis to inspect configuration, outputs, and data previews.")


def render_results_tab_selector() -> str:
    tab_options = ["Dashboard", "Strategy", "Backtest", "Funding & Risk", "Data"]
    _ensure_widget_choice("active_results_tab", tab_options, "Dashboard")
    active_tab = st.segmented_control(
        "Results tabs",
        options=tab_options,
        default=st.session_state.get("active_results_tab", "Dashboard"),
        key="active_results_tab",
        width="stretch",
        label_visibility="collapsed",
    )
    st.divider()
    return active_tab or "Dashboard"


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
    state = analysis_state or {}
    active_tab = render_results_tab_selector()
    if active_tab == "Dashboard":
        render_dashboard_tab(state)
    elif active_tab == "Strategy":
        render_strategy_tab()
    elif active_tab == "Backtest":
        render_backtest_tab(state)
    elif active_tab == "Funding & Risk":
        render_funding_risk_tab(state)
    elif active_tab == "Data":
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
    filtered_df = render_comparison_filters(comparison_df)
    if filtered_df.empty:
        st.warning("No comparison rows match the selected filters.")
        return
    render_comparison_rankings(filtered_df)
    render_comparison_best_worst_cards(filtered_df)
    render_comparison_visual_rankings(filtered_df)
    render_comparison_detail_view(filtered_df)
    st.dataframe(
        format_comparison_dataframe(filtered_df),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Download comparison CSV",
        data=comparison_df.to_csv(index=False),
        file_name="app_preset_comparison.csv",
        mime="text/csv",
    )


def render_comparison_filters(comparison_df: pd.DataFrame) -> pd.DataFrame:
    columns = st.columns(3)
    company_options = sorted(comparison_df["company"].dropna().astype(str).unique())
    plan_options = sorted(comparison_df["plan"].dropna().astype(str).unique())
    size_options = sorted(pd.to_numeric(comparison_df["account_size"], errors="coerce").dropna().astype(int).unique())
    _ensure_multiselect_choices("comparison_company_filter", company_options)
    _ensure_multiselect_choices("comparison_plan_filter", plan_options)
    _ensure_multiselect_choices("comparison_size_filter", list(size_options))
    selected_companies = columns[0].multiselect(
        "Filter companies",
        options=company_options,
        default=company_options,
        key="comparison_company_filter",
    )
    selected_plans = columns[1].multiselect(
        "Filter plans",
        options=plan_options,
        default=plan_options,
        key="comparison_plan_filter",
    )
    selected_sizes = columns[2].multiselect(
        "Filter account sizes",
        options=list(size_options),
        default=list(size_options),
        format_func=format_account_size,
        key="comparison_size_filter",
    )
    return filter_comparison_dataframe(
        comparison_df,
        companies=selected_companies,
        plans=selected_plans,
        account_sizes=selected_sizes,
    )


def filter_comparison_dataframe(
    comparison_df: pd.DataFrame,
    companies: list[str] | None = None,
    plans: list[str] | None = None,
    account_sizes: list[int] | None = None,
) -> pd.DataFrame:
    filtered = comparison_df.copy()
    if companies is not None:
        filtered = filtered[filtered["company"].astype(str).isin(companies)]
    if plans is not None:
        filtered = filtered[filtered["plan"].astype(str).isin(plans)]
    if account_sizes is not None and "account_size" in filtered.columns:
        numeric_size = pd.to_numeric(filtered["account_size"], errors="coerce")
        filtered = filtered[numeric_size.isin(account_sizes)]
    return filtered


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


def render_comparison_best_worst_cards(comparison_df: pd.DataFrame) -> None:
    with st.expander("Best / Worst Presets", expanded=True):
        metrics = [
            ("Net Business PnL", "net_business_pnl", format_currency_compact, True),
            ("ROI", "roi", format_percent, True),
            ("Total Net Payout", "total_net_payout", format_currency_compact, True),
            ("Final Bankroll", "final_bankroll", format_currency_compact, True),
            ("Risk of Ruin", "ruin_probability", format_percent, False),
        ]
        rows = []
        for label, column, formatter, higher_is_better in metrics:
            summary = comparison_metric_extremes(
                comparison_df,
                column,
                formatter,
                higher_is_better=higher_is_better,
            )
            if summary is not None:
                rows.extend(summary)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("No comparable numeric metrics are available.")


def render_comparison_visual_rankings(comparison_df: pd.DataFrame) -> None:
    chart_metrics = [
        ("Net Business PnL", "net_business_pnl"),
        ("ROI", "roi"),
        ("Final Bankroll", "final_bankroll"),
        ("Risk-Adjusted Score", "risk_adjusted_score"),
    ]
    with st.expander("Visual Rankings", expanded=True):
        for title, metric in chart_metrics:
            chart_df = comparison_chart_dataframe(comparison_df, metric)
            if chart_df.empty:
                continue
            st.caption(title)
            st.bar_chart(chart_df.set_index("Preset")[metric])


def render_comparison_detail_view(comparison_df: pd.DataFrame) -> None:
    with st.expander("Comparison Detail View", expanded=False):
        metric_options = [
            "net_business_pnl",
            "roi",
            "total_net_payout",
            "final_bankroll",
            "ruin_probability",
            "risk_adjusted_score",
            "pass_rate",
            "payout_rate",
        ]
        available_metrics = [metric for metric in metric_options if metric in comparison_df.columns]
        if not available_metrics:
            st.info("No comparison metrics are available for detail ranking.")
            return
        selected_metric = st.selectbox(
            "Rank by",
            options=available_metrics,
            index=0,
            key="comparison_detail_rank_metric",
        )
        ascending = selected_metric == "ruin_probability"
        detail = comparison_df.copy()
        detail[selected_metric] = pd.to_numeric(detail[selected_metric], errors="coerce")
        detail = detail.sort_values(selected_metric, ascending=ascending, na_position="last")
        st.dataframe(
            format_comparison_dataframe(detail),
            hide_index=True,
            use_container_width=True,
        )


def comparison_metric_extremes(
    comparison_df: pd.DataFrame,
    metric: str,
    formatter,
    higher_is_better: bool = True,
) -> list[dict[str, str]] | None:
    if metric not in comparison_df.columns:
        return None
    numeric_values = pd.to_numeric(comparison_df[metric], errors="coerce")
    if numeric_values.dropna().empty:
        return None
    best_index = numeric_values.idxmax() if higher_is_better else numeric_values.idxmin()
    worst_index = numeric_values.idxmin() if higher_is_better else numeric_values.idxmax()
    best_row = comparison_df.loc[best_index]
    worst_row = comparison_df.loc[worst_index]
    return [
        {
            "Metric": metric,
            "Rank": "Best",
            "Preset": comparison_preset_label(best_row),
            "Value": formatter(best_row[metric]),
        },
        {
            "Metric": metric,
            "Rank": "Worst",
            "Preset": comparison_preset_label(worst_row),
            "Value": formatter(worst_row[metric]),
        },
    ]


def comparison_chart_dataframe(
    comparison_df: pd.DataFrame,
    metric: str,
    top_n: int = 10,
) -> pd.DataFrame:
    if metric not in comparison_df.columns:
        return pd.DataFrame(columns=["Preset", metric])
    chart_df = comparison_df.copy()
    chart_df[metric] = pd.to_numeric(chart_df[metric], errors="coerce")
    chart_df = chart_df.dropna(subset=[metric])
    if chart_df.empty:
        return pd.DataFrame(columns=["Preset", metric])
    chart_df["Preset"] = chart_df.apply(comparison_preset_label, axis=1)
    return chart_df[["Preset", metric]].sort_values(metric, ascending=False).head(top_n)


def comparison_preset_label(row: pd.Series) -> str:
    return (
        f"{row.get('company')} | {row.get('plan')} | "
        f"{format_account_size(row.get('account_size'))}"
    )


def comparison_rows_to_dataframe(comparison_rows: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(comparison_rows)
    if dataframe.empty:
        return dataframe
    ordered_columns = [
        "company",
        "plan",
        "account_name",
        "account_size",
        "pass_rate",
        "payout_rate",
        "payout_rate_on_passed",
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
    return format_comparison_dataframe(comparison_rows_to_dataframe(comparison_rows))


def format_comparison_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
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
        "payout_rate_on_passed",
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
    strategy_metrics = analysis_state["strategy_metrics"]
    st.subheader("Backtest Summary")
    _metric_row(
        [
            ("Total Trades", strategy_metrics["total_trades"]),
            ("Win Rate", f"{strategy_metrics['win_rate']:.2%}"),
            ("Net PnL", _money(strategy_metrics["net_pnl"])),
            ("Profit Factor", format_profit_factor(strategy_metrics["profit_factor"])),
        ]
    )
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
    with st.expander("Account Summary", expanded=True):
        render_account_summary(analysis_state.get("account_summary", []))
    with st.expander("Account Rule Audit", expanded=True):
        render_account_rule_audit(analysis_state.get("account_rule_audit", []))
    with st.expander("Account Cycle Registry", expanded=True):
        render_account_cycle_registry(analysis_state.get("account_cycle_registry", []))
    with st.expander("Account Event Timeline", expanded=True):
        render_account_event_timeline(analysis_state.get("account_event_timeline", []))
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
    st.subheader("Run Folder")
    exported_files = analysis_state.get("exported_files", {})
    run_folder = exported_files.get("run_folder")
    if run_folder:
        st.success("This analysis was saved as a reproducible run folder.")
        st.code(str(run_folder))
    else:
        st.info("Run folder information is available after running a new analysis.")

    st.subheader("Input Configuration")
    st.dataframe(
        pd.DataFrame(_configuration_rows(analysis_state)),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Selected Preset Rules")
    preset_rules = analysis_state.get("selected_preset_rules")
    if preset_rules:
        render_preset_rules_summary(preset_rules)
    else:
        st.info("Preset rule details are available after running a new analysis.")

    st.subheader("Market Data Quality")
    market_data_summary = analysis_state.get("market_data_summary")
    if market_data_summary:
        st.success("Loaded OHLC data passed validation.")
        st.dataframe(
            pd.DataFrame(_market_data_summary_rows(market_data_summary)),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Run an analysis or use the sidebar validator to inspect market data quality.")

    st.subheader("Generated Outputs")
    output_rows = [
        {"Output": label, "Path": str(path), "Exists": Path(path).exists()}
        for label, path in exported_files.items()
    ]
    st.dataframe(pd.DataFrame(output_rows), hide_index=True, use_container_width=True)
    manifest_path = exported_files.get("run_manifest")
    if manifest_path and Path(manifest_path).exists():
        with st.expander("Run Manifest", expanded=False):
            st.json(load_json_file(Path(manifest_path)))

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
                "market_data_summary": market_data_summary,
                "account_summary": analysis_state.get("account_summary", []),
                "account_rule_audit": analysis_state.get("account_rule_audit", []),
                "account_cycle_registry": analysis_state.get("account_cycle_registry", []),
                "account_event_timeline": analysis_state.get("account_event_timeline", []),
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


def render_account_summary(account_rows: list[dict[str, Any]]) -> None:
    if not account_rows:
        st.info("No account summary is available for this run.")
        return

    summary = account_summary_dataframe(account_rows)
    columns = st.columns(3)
    phase_options = ["All"] + sorted(summary["Phase"].dropna().astype(str).unique())
    status_options = ["All"] + sorted(summary["Status"].dropna().astype(str).unique())
    selected_phase = columns[0].selectbox(
        "Phase",
        options=phase_options,
        key="account_summary_phase_filter",
    )
    selected_status = columns[1].selectbox(
        "Status",
        options=status_options,
        key="account_summary_status_filter",
    )
    show_active_only = columns[2].checkbox(
        "Active only",
        value=False,
        key="account_summary_active_only",
    )

    filtered = summary.copy()
    if selected_phase != "All":
        filtered = filtered[filtered["Phase"].astype(str) == selected_phase]
    if selected_status != "All":
        filtered = filtered[filtered["Status"].astype(str) == selected_status]
    if show_active_only:
        filtered = filtered[filtered["Status"].astype(str) == "ACTIVE"]

    st.dataframe(
        format_account_summary_dataframe(filtered),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Download account summary CSV",
        data=summary.to_csv(index=False),
        file_name="account_summary_streamlit.csv",
        mime="text/csv",
    )


def account_summary_dataframe(account_rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "AccountID",
        "Phase",
        "Status",
        "FinalPnL",
        "HighWatermark",
        "TradingDays",
        "TradesCount",
        "StartedAt",
        "EndedAt",
        "ResultReason",
        "PayoutsCount",
        "TotalGrossPayout",
        "TotalNetPayout",
        "DrawdownFloor",
        "EODHighPnL",
        "DrawdownLocked",
    ]
    return pd.DataFrame(account_rows, columns=columns)


def format_account_summary_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    formatted = dataframe.copy()
    for column in [
        "FinalPnL",
        "HighWatermark",
        "TotalGrossPayout",
        "TotalNetPayout",
        "DrawdownFloor",
        "EODHighPnL",
    ]:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(
                lambda value: "N/A" if pd.isna(value) else format_currency_full(value)
            )
    for column in ["StartedAt", "EarliestTradeTime", "EndedAt"]:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(_optional_datetime)
    if "DrawdownLocked" in formatted.columns:
        formatted["DrawdownLocked"] = formatted["DrawdownLocked"].apply(
            lambda value: "Yes" if bool(value) else "No"
        )
    return formatted


def render_account_rule_audit(rule_rows: list[dict[str, Any]]) -> None:
    if not rule_rows:
        st.info("No account rule events were triggered in this run.")
        return

    audit = account_rule_audit_dataframe(rule_rows)
    columns = st.columns(4)
    group_options = ["All"] + sorted(audit["RuleGroup"].dropna().astype(str).unique())
    severity_options = ["All"] + sorted(audit["Severity"].dropna().astype(str).unique())
    phase_options = ["All"] + sorted(audit["Phase"].dropna().astype(str).unique())
    selected_group = columns[0].selectbox("Rule group", options=group_options, key="rule_audit_group")
    selected_severity = columns[1].selectbox(
        "Severity",
        options=severity_options,
        key="rule_audit_severity",
    )
    selected_phase = columns[2].selectbox("Rule phase", options=phase_options, key="rule_audit_phase")
    max_rows = columns[3].number_input(
        "Rule rows",
        min_value=25,
        max_value=1000,
        value=200,
        step=25,
        key="rule_audit_max_rows",
    )

    filtered = audit.copy()
    if selected_group != "All":
        filtered = filtered[filtered["RuleGroup"].astype(str) == selected_group]
    if selected_severity != "All":
        filtered = filtered[filtered["Severity"].astype(str) == selected_severity]
    if selected_phase != "All":
        filtered = filtered[filtered["Phase"].astype(str) == selected_phase]

    st.dataframe(
        format_account_rule_audit_dataframe(filtered.head(int(max_rows))),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Download account rule audit CSV",
        data=audit.to_csv(index=False),
        file_name="account_rule_audit.csv",
        mime="text/csv",
    )


def account_rule_audit_dataframe(rule_rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "Step",
        "Time",
        "AccountID",
        "Phase",
        "RuleGroup",
        "RuleType",
        "Severity",
        "TradeID",
        "OriginalNetPnL",
        "AppliedNetPnL",
        "AccountPnL",
        "Status",
        "Reason",
    ]
    return pd.DataFrame(rule_rows, columns=columns)


def format_account_rule_audit_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    formatted = dataframe.copy()
    for column in ["OriginalNetPnL", "AppliedNetPnL", "AccountPnL"]:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(
                lambda value: "N/A" if pd.isna(value) else format_currency_full(value)
            )
    if "Time" in formatted.columns:
        formatted["Time"] = formatted["Time"].apply(_optional_datetime)
    return formatted


def render_account_cycle_registry(cycle_rows: list[dict[str, Any]]) -> None:
    if not cycle_rows:
        st.info("No account cycle registry is available for this run.")
        return

    registry = account_cycle_registry_dataframe(cycle_rows)
    st.caption(
        "One registry for the complete run. Each row is an account phase/cycle "
        "in chronological simulation order."
    )
    columns = st.columns(4)
    phase_options = ["All"] + sorted(registry["Phase"].dropna().astype(str).unique())
    status_options = ["All"] + sorted(registry["Status"].dropna().astype(str).unique())
    selected_phase = columns[0].selectbox("Cycle phase", options=phase_options, key="cycle_registry_phase")
    selected_status = columns[1].selectbox("Cycle status", options=status_options, key="cycle_registry_status")
    only_rule_events = columns[2].checkbox("Only cycles with rule events", value=False, key="cycle_registry_rules_only")
    max_rows = columns[3].number_input(
        "Cycle rows",
        min_value=25,
        max_value=1000,
        value=200,
        step=25,
        key="cycle_registry_max_rows",
    )

    filtered = registry.copy()
    if selected_phase != "All":
        filtered = filtered[filtered["Phase"].astype(str) == selected_phase]
    if selected_status != "All":
        filtered = filtered[filtered["Status"].astype(str) == selected_status]
    if only_rule_events:
        filtered = filtered[pd.to_numeric(filtered["AccountAwareExitsCount"], errors="coerce").fillna(0) > 0]

    st.dataframe(
        format_account_cycle_registry_dataframe(filtered.head(int(max_rows))),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Download account cycle registry CSV",
        data=registry.to_csv(index=False),
        file_name="account_cycle_registry.csv",
        mime="text/csv",
    )


def account_cycle_registry_dataframe(cycle_rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(cycle_rows)


def format_account_cycle_registry_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    formatted = dataframe.copy()
    currency_columns = [
        "OriginalNetPnL",
        "AppliedNetPnL",
        "FinalPnL",
        "HighWatermark",
        "TargetOrPayoutTrigger",
        "DistanceToTarget",
        "DistanceToDrawdown",
        "DrawdownFloor",
        "EODHighPnL",
        "BestDayPnL",
        "WorstDayPnL",
        "BestTradePnL",
        "WorstTradePnL",
        "TotalGrossPayout",
        "TotalNetPayout",
        "MorningNetPnL",
        "MiddayNetPnL",
        "AfternoonNetPnL",
        "EveningNetPnL",
        "OvernightNetPnL",
    ]
    for column in currency_columns:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(
                lambda value: "N/A" if pd.isna(value) else format_currency_full(value)
            )
    if "WinRate" in formatted.columns:
        formatted["WinRate"] = formatted["WinRate"].apply(format_percent)
    for column in ["StartedAt", "EndedAt"]:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(_optional_datetime)
    return formatted


def render_account_event_timeline(timeline_rows: list[dict[str, Any]]) -> None:
    if not timeline_rows:
        st.info("No account events are available for this run.")
        return

    timeline = account_event_timeline_dataframe(timeline_rows)
    event_types = ["All"] + sorted(timeline["EventType"].dropna().astype(str).unique())
    account_ids = ["All"] + [
        str(value)
        for value in sorted(timeline["AccountID"].dropna().unique())
    ]

    columns = st.columns(3)
    selected_event_type = columns[0].selectbox(
        "Event type",
        options=event_types,
        key="timeline_event_type_filter",
    )
    selected_account_id = columns[1].selectbox(
        "Account",
        options=account_ids,
        key="timeline_account_filter",
    )
    max_rows = columns[2].number_input(
        "Max rows",
        min_value=25,
        max_value=1000,
        value=200,
        step=25,
        key="timeline_max_rows",
    )

    filtered = timeline.copy()
    if selected_event_type != "All":
        filtered = filtered[filtered["EventType"].astype(str) == selected_event_type]
    if selected_account_id != "All":
        filtered = filtered[filtered["AccountID"].astype(str) == selected_account_id]

    st.dataframe(
        format_account_event_timeline_dataframe(filtered.head(int(max_rows))),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Download account timeline CSV",
        data=timeline.to_csv(index=False),
        file_name="account_event_timeline.csv",
        mime="text/csv",
    )


def account_event_timeline_dataframe(timeline_rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "Step",
        "Time",
        "AccountID",
        "Phase",
        "EventType",
        "TradeID",
        "Amount",
        "AccountPnL",
        "Status",
        "Reason",
    ]
    return pd.DataFrame(timeline_rows, columns=columns)


def format_account_event_timeline_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    formatted = dataframe.copy()
    for column in ["Amount", "AccountPnL"]:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(
                lambda value: "N/A" if pd.isna(value) else format_currency_full(value)
            )
    if "Time" in formatted.columns:
        formatted["Time"] = formatted["Time"].apply(_optional_datetime)
    return formatted


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
    curve_df["EventLabel"] = curve_df.apply(bankroll_event_label, axis=1)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve_df[x_column],
            y=curve_df["bankroll"],
            mode="lines",
            name="Bankroll",
            line=dict(color="#2563eb", width=2),
            hovertemplate="Step: %{x}<br>Bankroll: $%{y:,.2f}<extra></extra>",
        )
    )
    if "event_type" in curve_df.columns:
        event_type = curve_df["event_type"].astype(str)
        payouts = curve_df[event_type == "PAYOUT"].copy()
        costs = curve_df[event_type == "EVALUATION_COST"].copy()
        initial = curve_df[event_type == "INITIAL"].copy()
    else:
        payouts = curve_df.head(0).copy()
        costs = curve_df.head(0).copy()
        initial = curve_df.head(0).copy()

    if not payouts.empty:
        fig.add_trace(
            go.Scatter(
                x=payouts[x_column],
                y=payouts["bankroll"],
                mode="markers",
                name="PAYOUT",
                marker=dict(color="#4caf50", symbol="circle", size=10),
                customdata=payouts["amount"].abs(),
                hovertemplate="PAYOUT<br>+$%{customdata:,.2f}<br>%{x}<extra></extra>",
            )
        )
    if not costs.empty:
        fig.add_trace(
            go.Scatter(
                x=costs[x_column],
                y=costs["bankroll"],
                mode="markers",
                name="Account Cost",
                marker=dict(color="#e05c5c", symbol="triangle-down", size=10),
                customdata=costs["amount"].abs(),
                hovertemplate="Account Cost<br>-$%{customdata:,.2f}<br>%{x}<extra></extra>",
            )
        )
    if not initial.empty:
        fig.add_trace(
            go.Scatter(
                x=initial[x_column],
                y=initial["bankroll"],
                mode="markers",
                name="Start",
                marker=dict(
                    color="#ffffff",
                    symbol="diamond",
                    size=8,
                    line=dict(color="#111827", width=1),
                ),
                hovertemplate="Start<br>$%{y:,.2f}<br>%{x}<extra></extra>",
            )
        )

    initial_bankroll = bankroll_result.get("metrics", {}).get("initial_bankroll")
    if initial_bankroll is not None and not curve_df.empty:
        x_min = curve_df[x_column].iloc[0]
        x_max = curve_df[x_column].iloc[-1]
        fig.add_shape(
            type="line",
            x0=x_min,
            x1=x_max,
            y0=initial_bankroll,
            y1=initial_bankroll,
            line=dict(color="#555", width=1, dash="dot"),
        )
        fig.add_annotation(
            x=x_min,
            y=initial_bankroll,
            text=f"Start {format_currency_full(initial_bankroll)}",
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            font=dict(size=11, color="#555"),
        )
    fig.update_layout(
        title="Bankroll Evolution",
        xaxis_title="Event",
        yaxis_title="Bankroll",
        height=380,
        margin=dict(l=20, r=20, t=45, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(format_bankroll_curve_dataframe(curve_df), use_container_width=True)


def add_bankroll_event_markers(
    fig: go.Figure,
    events: pd.DataFrame,
    x_column: str,
    name: str,
    color: str,
) -> None:
    if events.empty:
        return
    fig.add_trace(
        go.Scatter(
            x=events[x_column],
            y=events["bankroll"],
            mode="markers",
            name=name,
            marker=dict(size=11, color=color, line=dict(width=1, color="white")),
            text=events["EventLabel"],
            hovertemplate="%{text}<extra></extra>",
        )
    )


def important_bankroll_events(events: pd.DataFrame, max_events: int = 6) -> pd.DataFrame:
    if events.empty or "bankroll" not in events.columns:
        return events.head(0)
    selected_indexes = set()
    selected_indexes.add(events["bankroll"].idxmin())
    selected_indexes.add(events["bankroll"].idxmax())
    if "amount" in events.columns:
        amount = pd.to_numeric(events["amount"], errors="coerce")
        if amount.notna().any():
            selected_indexes.update(amount.abs().sort_values(ascending=False).head(max_events).index)
    return events.loc[list(selected_indexes)].sort_values("step").head(max_events)


def bankroll_event_label(row: pd.Series) -> str:
    amount = row.get("amount")
    amount_text = "N/A" if pd.isna(amount) else format_currency_full(amount)
    return (
        f"Step {row.get('step')}<br>"
        f"Event: {row.get('event_type')}<br>"
        f"Amount: {amount_text}<br>"
        f"Bankroll: {format_currency_full(row.get('bankroll'))}<br>"
        f"Account: {row.get('account_id')}"
    )


def format_bankroll_curve_dataframe(curve_df: pd.DataFrame) -> pd.DataFrame:
    formatted = curve_df.copy()
    for column in ["amount", "bankroll"]:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(
                lambda value: "N/A" if pd.isna(value) else format_currency_full(value)
            )
    if "time" in formatted.columns:
        formatted["time"] = formatted["time"].apply(_optional_datetime)
    if "EventLabel" in formatted.columns:
        formatted = formatted.drop(columns=["EventLabel"])
    return formatted


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
    _metric_row(
        [
            ("Mean Final Bankroll", _money(metrics["mean_final_bankroll"])),
            ("Worst Lowest Bankroll", _money(metrics["worst_lowest_bankroll"])),
            ("Avg Max Drawdown", _money(metrics["average_max_drawdown"])),
            ("Worst Max Drawdown", _money(metrics["worst_max_drawdown"])),
        ]
    )
    st.divider()
    render_ruin_probability_curve(required_bankroll)
    st.divider()
    render_ruin_paths_charts(risk_result.get("paths"))


def render_ruin_probability_curve(required_bankroll: dict[str, Any] | None) -> None:
    if required_bankroll is None:
        return
    grid_results = required_bankroll.get("grid_results", [])
    if not grid_results:
        return

    dataframe = pd.DataFrame(grid_results)
    if dataframe.empty or not {"bankroll", "ruin_probability"}.issubset(dataframe.columns):
        return

    target = float(required_bankroll.get("target_ruin_probability", 0.05) or 0.05)
    recommended = required_bankroll.get("recommended_bankroll")
    y_values = pd.to_numeric(dataframe["ruin_probability"], errors="coerce") * 100
    x_values = pd.to_numeric(dataframe["bankroll"], errors="coerce")
    y_max = max(float(y_values.max() or 0), target * 100, 1)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="lines+markers",
            name="Ruin Probability",
            line=dict(color="#e05c5c", width=3),
            marker=dict(size=8),
        )
    )
    fig.add_hline(
        y=target * 100,
        line_dash="dash",
        line_color="#aaaaaa",
        annotation_text=f"Target {target:.0%}",
        annotation_position="top right",
    )
    if recommended is not None:
        fig.add_vline(
            x=recommended,
            line_dash="dash",
            line_color="#2196f3",
            annotation_text=f"Recommended ${recommended:,.0f}",
            annotation_position="top right",
        )
    fig.update_layout(
        title="Ruin Probability vs Starting Bankroll",
        xaxis_title="Starting Bankroll ($)",
        yaxis_title="Ruin Probability (%)",
        yaxis_range=[0, y_max * 1.1],
        height=320,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_ruin_paths_charts(paths: list[dict[str, Any]] | None) -> None:
    if not paths:
        return
    dataframe = pd.DataFrame(paths)
    required_columns = {"final_bankroll", "ruined", "max_drawdown"}
    if dataframe.empty or not required_columns.issubset(dataframe.columns):
        return

    dataframe["final_bankroll"] = pd.to_numeric(dataframe["final_bankroll"], errors="coerce")
    dataframe["max_drawdown"] = pd.to_numeric(dataframe["max_drawdown"], errors="coerce")
    dataframe = dataframe.dropna(subset=["final_bankroll", "max_drawdown"])
    if dataframe.empty:
        return

    left_column, right_column = st.columns([1, 1])
    with left_column:
        st.plotly_chart(build_final_bankroll_distribution_figure(dataframe), use_container_width=True)
    with right_column:
        st.plotly_chart(build_max_drawdown_distribution_figure(dataframe), use_container_width=True)


def build_final_bankroll_distribution_figure(dataframe: pd.DataFrame) -> go.Figure:
    ruined_mask = dataframe["ruined"].apply(_truthy_value)
    survived = dataframe.loc[~ruined_mask, "final_bankroll"]
    ruined = dataframe.loc[ruined_mask, "final_bankroll"]

    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=survived,
            marker_color="#4caf50",
            name="Survived",
            opacity=0.7,
        )
    )
    fig.add_trace(
        go.Histogram(
            x=ruined,
            marker_color="#e05c5c",
            name="Ruined",
            opacity=0.7,
        )
    )

    quantiles = [
        ("P5", dataframe["final_bankroll"].quantile(0.05), "#ff9800", "dot"),
        ("Median", dataframe["final_bankroll"].median(), "#2196f3", "dash"),
        ("P95", dataframe["final_bankroll"].quantile(0.95), "#4caf50", "dot"),
    ]
    for label, value, color, dash in quantiles:
        fig.add_vline(
            x=value,
            line_color=color,
            line_dash=dash,
            annotation_text=label,
            annotation_position="top",
        )

    fig.update_layout(
        title="Final Bankroll Distribution",
        xaxis_title="Final Bankroll ($)",
        yaxis_title="Runs",
        barmode="overlay",
        height=300,
        margin=dict(l=40, r=30, t=40, b=40),
    )
    return fig


def _truthy_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def build_max_drawdown_distribution_figure(dataframe: pd.DataFrame) -> go.Figure:
    mean_drawdown = dataframe["max_drawdown"].mean()
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=dataframe["max_drawdown"],
            marker_color="#e57c35",
            name="Max Drawdown",
            opacity=0.8,
        )
    )
    fig.add_vline(
        x=mean_drawdown,
        line_color="#333",
        line_dash="dash",
        annotation_text="Mean",
        annotation_position="top",
    )
    fig.update_layout(
        title="Max Drawdown Distribution",
        xaxis_title="Max Drawdown ($)",
        yaxis_title="Runs",
        height=300,
        margin=dict(l=40, r=30, t=40, b=40),
    )
    return fig


def render_streak_summary(streak_analysis: dict[str, Any]) -> None:
    st.subheader("Streak Analysis")
    _metric_row(
        [
            (
                "Max Consec. No-Payout",
                streak_analysis["max_consecutive_no_payout_accounts"],
            ),
            (
                "Max Consec. Negative",
                streak_analysis["max_consecutive_negative_accounts"],
            ),
            (
                "Max Consec. Failed Eval",
                streak_analysis["max_consecutive_failed_evaluations"],
            ),
        ]
    )
    _metric_row(
        [
            (
                "Max Consec. Payout",
                streak_analysis["max_consecutive_payout_accounts"],
            ),
            (
                "Max Consec. Positive",
                streak_analysis["max_consecutive_positive_accounts"],
            ),
            (
                "Max Consec. Passed Eval",
                streak_analysis["max_consecutive_passed_evaluations"],
            ),
        ]
    )

    if has_streak_sequences(streak_analysis):
        st.divider()
        render_streak_sequence_chart(streak_analysis)
    if has_streak_zscores(streak_analysis):
        st.divider()
        render_streak_zscore_chart(streak_analysis)


def has_streak_sequences(streak_analysis: dict[str, Any]) -> bool:
    return any(
        streak_analysis.get(key)
        for key in [
            "funded_payout_sequence",
            "net_positive_sequence",
            "passed_evaluation_sequence",
        ]
    )


def has_streak_zscores(streak_analysis: dict[str, Any]) -> bool:
    return any(
        streak_analysis.get(key, {}).get("z_score") is not None
        for key in [
            "z_score_funded_payout",
            "z_score_net_positive",
            "z_score_passed_evaluation",
        ]
    )


def render_streak_sequence_chart(streak_analysis: dict[str, Any]) -> None:
    sequences = {
        "Passed Eval": streak_analysis.get("passed_evaluation_sequence", []),
        "Net Positive": streak_analysis.get("net_positive_sequence", []),
        "Got Payout": streak_analysis.get("funded_payout_sequence", []),
    }
    non_empty_sequences = [sequence for sequence in sequences.values() if sequence]
    if not non_empty_sequences:
        return

    max_len = max(len(sequence) for sequence in non_empty_sequences)
    z_matrix = []
    for sequence in sequences.values():
        padded = list(sequence) + [None] * (max_len - len(sequence))
        z_matrix.append(padded)

    fig = go.Figure(
        go.Heatmap(
            z=z_matrix,
            x=list(range(1, max_len + 1)),
            y=list(sequences.keys()),
            colorscale=[[0, "#ef5350"], [1, "#26a69a"]],
            zmin=0,
            zmax=1,
            showscale=False,
            hovertemplate="Account %{x}<br>%{y}: %{z}<extra></extra>",
            xgap=1,
            ygap=3,
        )
    )
    fig.update_layout(
        title="Account Outcome Sequences",
        xaxis_title="Account #",
        height=180,
        margin=dict(l=10, r=10, t=40, b=30),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Green = success, red = failure. Each column is one account in chronological order."
    )


def render_streak_zscore_chart(streak_analysis: dict[str, Any]) -> None:
    labels = ["Payout", "Net Positive", "Passed Eval"]
    zscores = [
        streak_analysis.get("z_score_funded_payout", {}).get("z_score"),
        streak_analysis.get("z_score_net_positive", {}).get("z_score"),
        streak_analysis.get("z_score_passed_evaluation", {}).get("z_score"),
    ]
    if all(zscore is None for zscore in zscores):
        return

    plot_values = [0 if zscore is None else zscore for zscore in zscores]
    colors = [zscore_color(zscore) for zscore in zscores]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=[
                f"z={zscore:.2f}" if zscore is not None else "N/A"
                for zscore in zscores
            ],
            textposition="outside",
            hovertemplate="%{y}: z=%{x:.3f}<extra></extra>",
        )
    )
    for x_value, label, dash in [
        (1.96, "95%", "dash"),
        (-1.96, "", "dash"),
        (2.58, "99%", "dot"),
        (-2.58, "", "dot"),
    ]:
        fig.add_vline(
            x=x_value,
            line_color="#aaa",
            line_dash=dash,
            line_width=1,
            annotation_text=label,
            annotation_position="top",
        )
    fig.update_layout(
        title="Runs Test Z-Score (randomness of sequences)",
        xaxis_title="Z-Score",
        height=220,
        margin=dict(l=10, r=60, t=40, b=30),
        xaxis=dict(range=[-4, 4]),
    )
    st.caption(
        "Z-score measures whether winning/losing streaks are random. "
        "|z| < 1.96 = likely random (green). "
        "|z| > 1.96 = possible pattern (yellow/red)."
    )
    st.plotly_chart(fig, use_container_width=True)


def zscore_color(zscore: float | None) -> str:
    if zscore is None:
        return "#888"
    if abs(zscore) < 1.96:
        return "#26a69a"
    if abs(zscore) < 2.58:
        return "#ff9800"
    return "#ef5350"


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

    st.subheader("Cost Sensitivity")
    st.caption("Compare current results with reduced-cost and no-cost scenarios.")
    render_cost_sensitivity(diagnostics)

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

    st.subheader("Long vs Short")
    st.caption("Directional diagnostics help reveal whether one side carries the edge or the costs.")
    render_direction_diagnostics(diagnostics["direction_table"])

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
                _format_diagnostic_money_columns(
                    hourly_table,
                    ["NetPnL", "AverageNetPnL", "TotalCost"],
                ),
                use_container_width=True,
            )
            st.caption("Trades by hour")
            st.bar_chart(hourly_table.set_index("Hour")["Trades"])
            st.caption("Net PnL by hour")
            st.bar_chart(hourly_table.set_index("Hour")["NetPnL"])

    session_table = diagnostics["session_table"]
    if not session_table.empty:
        with st.expander("Session Diagnostics", expanded=False):
            st.caption(
                "Sessions are diagnostic buckets based on trade ExitTime. "
                "If a UTC offset is configured, diagnostics use the shifted local timestamps."
            )
            st.dataframe(
                _format_diagnostic_money_columns(
                    session_table,
                    ["NetPnL", "AverageNetPnL", "TotalCost"],
                ),
                use_container_width=True,
            )
            st.caption("Trades by session")
            st.bar_chart(session_table.set_index("Session")["Trades"])
            st.caption("Net PnL by session")
            st.bar_chart(session_table.set_index("Session")["NetPnL"])

    weekday_table = diagnostics["weekday_table"]
    if not weekday_table.empty:
        with st.expander("Day-of-Week Diagnostics", expanded=False):
            st.dataframe(
                _format_diagnostic_money_columns(
                    weekday_table,
                    ["NetPnL", "AverageNetPnL", "TotalCost"],
                ),
                use_container_width=True,
            )
            st.caption("Trades by weekday")
            st.bar_chart(weekday_table.set_index("Weekday")["Trades"])
            st.caption("Net PnL by weekday")
            st.bar_chart(weekday_table.set_index("Weekday")["NetPnL"])

    daily_table = diagnostics["daily_table"]
    if not daily_table.empty:
        with st.expander("Daily Diagnostics", expanded=False):
            st.dataframe(
                _format_diagnostic_money_columns(
                    daily_table,
                    ["NetPnL", "AverageNetPnL", "TotalCost"],
                ),
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


def render_cost_sensitivity(diagnostics: dict[str, Any]) -> None:
    sensitivity = diagnostics.get("cost_sensitivity", {})
    if not sensitivity:
        st.info("Cost sensitivity requires NetPnL and cost columns.")
        return

    render_metric_grid(
        [
            ("Current Net PnL", format_currency_compact(sensitivity["current_net_pnl"])),
            ("No-Cost Net PnL", format_currency_compact(sensitivity["no_cost_net_pnl"])),
            ("Total Cost Drag", format_currency_compact(sensitivity["total_cost_drag"])),
            ("Cost Drag / No-Cost PnL", format_percent(sensitivity["cost_drag_percent"])),
        ],
        columns_per_row=4,
    )

    sensitivity_table = diagnostics.get("cost_sensitivity_table", pd.DataFrame())
    if not sensitivity_table.empty:
        st.dataframe(format_cost_sensitivity_table(sensitivity_table), hide_index=True, use_container_width=True)


def format_cost_sensitivity_table(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    formatted = table.copy()
    for column in ["ProjectedNetPnL", "CostApplied", "PnLImprovement"]:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(format_currency_full)
    if "CostLevel" in formatted.columns:
        formatted["CostLevel"] = formatted["CostLevel"].apply(format_percent)
    return formatted


def render_direction_diagnostics(direction_table: pd.DataFrame) -> None:
    if direction_table.empty:
        st.info("Direction diagnostics require a Direction column in the trades.")
        return

    metric_items = []
    for _, row in direction_table.iterrows():
        direction = row["Direction"]
        metric_items.extend(
            [
                (f"{direction} Trades", format_number(row["Trades"])),
                (f"{direction} Win Rate", format_percent(row["WinRate"])),
                (f"{direction} Net PnL", format_currency_compact(row["NetPnL"])),
            ]
        )
    render_metric_grid(metric_items, columns_per_row=3)
    st.dataframe(format_direction_diagnostics_table(direction_table), hide_index=True, use_container_width=True)


def format_direction_diagnostics_table(direction_table: pd.DataFrame) -> pd.DataFrame:
    if direction_table.empty:
        return direction_table
    formatted = direction_table.copy()
    currency_columns = [
        "NetPnL",
        "AverageTrade",
        "TotalCost",
        "AverageWinner",
        "AverageLoser",
    ]
    for column in currency_columns:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(format_currency_full)
    if "WinRate" in formatted.columns:
        formatted["WinRate"] = formatted["WinRate"].apply(format_percent)
    if "ProfitFactor" in formatted.columns:
        formatted["ProfitFactor"] = formatted["ProfitFactor"].apply(format_profit_factor)
    if "PayoffRatio" in formatted.columns:
        formatted["PayoffRatio"] = formatted["PayoffRatio"].apply(format_number)
    return formatted


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
    filtered_trades = add_trade_risk_price_columns(
        filtered_trades,
        analysis_state.get("risk_settings", {}),
    )

    display_columns = [
        column
        for column in [
            "TradeID",
            "EntryTime",
            "ExitTime",
            "Direction",
            "EntryPrice",
            "SLPrice",
            "TPPrice",
            "ExitPrice",
            "Commission",
            "NetPnL",
            "ExitReason",
            "PhaseProfile",
        ]
        if column in filtered_trades.columns
    ]
    st.dataframe(filtered_trades[display_columns].head(5), use_container_width=True)

    # Future: replace selectbox with interactive row selection / double-click using streamlit-aggrid.
    trade_ids = filtered_trades["TradeID"].tolist()
    st.session_state["explorer_selected_trade_id"] = stable_selected_trade_id(
        trade_ids,
        st.session_state.get("explorer_selected_trade_id"),
    )
    selected_trade_id = st.selectbox(
        "Select TradeID to inspect",
        options=trade_ids,
        key="explorer_selected_trade_id",
    )
    selected_trade = filtered_trades[filtered_trades["TradeID"] == selected_trade_id].iloc[0]
    context_minutes = st.number_input(
        "Context minutes before/after",
        min_value=5,
        max_value=240,
        value=60,
        step=5,
        key="explorer_context_minutes",
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
    selected_date = st.selectbox(
        "Entry date",
        options=date_values,
        key="explorer_date_filter",
    )

    return {
        "direction": direction_filter,
        "exit_reason": exit_reason_filter,
        "phase_profile": phase_filter,
        "entry_date": selected_date,
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


def add_trade_risk_price_columns(
    trades: pd.DataFrame,
    risk_settings: dict[str, Any],
) -> pd.DataFrame:
    if trades.empty or "EntryPrice" not in trades.columns or "Direction" not in trades.columns:
        return trades
    stop_loss_points = risk_settings.get("stop_loss_points")
    take_profit_points = risk_settings.get("take_profit_points")
    if stop_loss_points is None or take_profit_points is None:
        return trades

    enriched = trades.copy()
    entry_price = pd.to_numeric(enriched["EntryPrice"], errors="coerce")
    is_long = enriched["Direction"] == "Long"
    enriched["SLPrice"] = np.where(
        is_long,
        entry_price - float(stop_loss_points),
        entry_price + float(stop_loss_points),
    )
    enriched["TPPrice"] = np.where(
        is_long,
        entry_price + float(take_profit_points),
        entry_price - float(take_profit_points),
    )
    return enriched


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

    return {
        "direction": direction_filter,
        "exit_reason": exit_reason_filter,
        "phase_profile": phase_filter,
        "entry_date": selected_date,
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
    return trades.sort_values("EntryTime").reset_index(drop=True)


def stable_selected_trade_id(trade_ids: list[Any], current_trade_id: Any) -> Any:
    if not trade_ids:
        return None
    if current_trade_id in trade_ids:
        return current_trade_id
    return trade_ids[0]


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
    fig = build_selected_trade_figure(
        ohlc_window,
        selected_trade,
        strategy_context,
        context_minutes=context_minutes,
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "modeBarButtonsToRemove": ["autoScale2d", "lasso2d", "select2d"],
            "modeBarButtonsToAdd": ["drawline", "eraseshape"],
            "toImageButtonOptions": {"format": "png", "scale": 2},
        },
    )


def build_selected_trade_figure(
    ohlc_window: pd.DataFrame,
    selected_trade: pd.Series,
    strategy_context: dict[str, Any],
    context_minutes: int,
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
            increasing_line_color="#26a69a",
            increasing_fillcolor="#26a69a",
            decreasing_line_color="#ef5350",
            decreasing_fillcolor="#ef5350",
        ),
        row=1,
        col=1,
    )

    _add_selected_trade_marker(fig, selected_trade, "entry")
    _add_selected_trade_marker(fig, selected_trade, "exit")
    _add_selected_trade_line(fig, selected_trade)
    _add_sl_tp_lines(
        fig,
        selected_trade,
        strategy_context.get("risk_settings", {}),
        context_minutes=context_minutes,
    )

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
        hovermode="x unified",
        hoverdistance=100,
        spikedistance=1000,
        height=760 if show_stochastic else 500,
        margin=dict(l=20, r=20, t=55, b=20),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_xaxes(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="#888",
        spikethickness=1,
        spikedash="dot",
    )
    fig.update_yaxes(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="#888",
        spikethickness=1,
        spikedash="dot",
        row=1,
        col=1,
    )
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
    context_minutes: int,
) -> None:
    entry_price = trade.get("EntryPrice")
    direction = trade.get("Direction")
    stop_loss_points = risk_settings.get("stop_loss_points")
    take_profit_points = risk_settings.get("take_profit_points")
    if entry_price is None or direction not in {"Long", "Short"}:
        return
    entry_time = pd.to_datetime(trade.get("EntryTime"), errors="coerce")
    exit_time = pd.to_datetime(trade.get("ExitTime"), errors="coerce")
    if pd.isna(entry_time) or pd.isna(exit_time):
        return
    x0 = entry_time - pd.Timedelta(minutes=context_minutes)
    x1 = exit_time + pd.Timedelta(minutes=context_minutes)
    if stop_loss_points is not None:
        sl = entry_price - stop_loss_points if direction == "Long" else entry_price + stop_loss_points
        fig.add_shape(
            type="line",
            x0=x0,
            x1=x1,
            y0=sl,
            y1=sl,
            line=dict(color="#ef5350", dash="dash", width=1),
            row=1,
            col=1,
        )
        fig.add_annotation(
            x=x1,
            y=sl,
            text="SL",
            showarrow=False,
            font=dict(color="#ef5350", size=11),
            xanchor="left",
            row=1,
            col=1,
        )
    if take_profit_points is not None:
        tp = entry_price + take_profit_points if direction == "Long" else entry_price - take_profit_points
        fig.add_shape(
            type="line",
            x0=x0,
            x1=x1,
            y0=tp,
            y1=tp,
            line=dict(color="#26a69a", dash="dash", width=1),
            row=1,
            col=1,
        )
        fig.add_annotation(
            x=x1,
            y=tp,
            text="TP",
            showarrow=False,
            font=dict(color="#26a69a", size=11),
            xanchor="left",
            row=1,
            col=1,
        )


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
                increasing_line_color="#26a69a",
                increasing_fillcolor="#26a69a",
                decreasing_line_color="#ef5350",
                decreasing_fillcolor="#ef5350",
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
    controls: dict[str, Any] | None = None,
    preset: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    market_data_summary: dict[str, Any] | None = None,
    account_event_timeline: list[dict[str, Any]] | None = None,
    account_summary: list[dict[str, Any]] | None = None,
    account_rule_audit: list[dict[str, Any]] | None = None,
    account_cycle_registry: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    experiment_id = generate_experiment_id()
    run_dir = create_run_output_dir(experiment_id)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "run_folder": run_dir,
        "generated_trades": OUTPUT_DIR / "app_generated_trades.csv",
        "summary_metrics": OUTPUT_DIR / "app_summary_metrics.json",
        "run_generated_trades": run_dir / "generated_trades.csv",
        "run_strategy_metrics": run_dir / "strategy_metrics.json",
        "run_business_metrics": run_dir / "business_metrics.json",
        "run_summary_metrics": run_dir / "summary_metrics.json",
        "run_selected_setup": run_dir / "selected_setup.json",
        "run_config_snapshot": run_dir / "config_snapshot.json",
    }
    trades.to_csv(files["generated_trades"], index=False)
    trades.to_csv(files["run_generated_trades"], index=False)

    summary = {
        "experiment_id": experiment_id,
        "run_folder": str(run_dir),
        "strategy_metrics": strategy_metrics,
        "business_metrics": business_metrics,
        "bankroll_metrics": None if bankroll_result is None else bankroll_result["metrics"],
        "streak_analysis": streak_analysis,
        "risk_of_ruin_metrics": None if risk_result is None else risk_result["metrics"],
        "required_bankroll": required_bankroll,
        "comparison_rows": comparison_rows or [],
        "market_data_summary": market_data_summary,
        "account_summary": account_summary or [],
        "account_rule_audit": account_rule_audit or [],
        "account_cycle_registry": account_cycle_registry or [],
        "account_event_timeline": account_event_timeline or [],
    }
    with files["summary_metrics"].open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, default=str)
    write_json_file(files["run_summary_metrics"], summary)
    write_json_file(files["run_strategy_metrics"], strategy_metrics)
    write_json_file(files["run_business_metrics"], business_metrics)
    write_json_file(
        files["run_selected_setup"],
        {
            "experiment_id": experiment_id,
            "controls": controls or {},
            "preset": preset or {},
        },
    )
    write_json_file(files["run_config_snapshot"], config or {})

    if account_summary:
        files["run_account_summary"] = run_dir / "account_summary.csv"
        pd.DataFrame(account_summary).to_csv(files["run_account_summary"], index=False)
    if account_rule_audit:
        files["run_account_rule_audit"] = run_dir / "account_rule_audit.csv"
        pd.DataFrame(account_rule_audit).to_csv(files["run_account_rule_audit"], index=False)
    if account_cycle_registry:
        files["run_account_cycle_registry"] = run_dir / "account_cycle_registry.csv"
        pd.DataFrame(account_cycle_registry).to_csv(
            files["run_account_cycle_registry"],
            index=False,
        )
    if account_event_timeline:
        files["run_account_event_timeline"] = run_dir / "account_event_timeline.csv"
        pd.DataFrame(account_event_timeline).to_csv(
            files["run_account_event_timeline"],
            index=False,
        )
    if bankroll_result is not None:
        files["run_bankroll_curve"] = run_dir / "bankroll_curve.csv"
        pd.DataFrame(bankroll_result.get("curve", [])).to_csv(
            files["run_bankroll_curve"],
            index=False,
        )
        files["run_bankroll_metrics"] = run_dir / "bankroll_metrics.json"
        write_json_file(files["run_bankroll_metrics"], bankroll_result.get("metrics", {}))
    if risk_result is not None:
        files["run_risk_of_ruin_metrics"] = run_dir / "risk_of_ruin_metrics.json"
        write_json_file(files["run_risk_of_ruin_metrics"], risk_result.get("metrics", {}))
        paths = risk_result.get("paths", [])
        if paths:
            files["run_risk_of_ruin_paths"] = run_dir / "risk_of_ruin_paths.csv"
            pd.DataFrame(paths).to_csv(files["run_risk_of_ruin_paths"], index=False)
    if required_bankroll is not None:
        files["run_required_bankroll_grid"] = run_dir / "required_bankroll_grid.csv"
        pd.DataFrame(required_bankroll.get("grid_results", [])).to_csv(
            files["run_required_bankroll_grid"],
            index=False,
        )
    if streak_analysis:
        files["run_streak_analysis"] = run_dir / "streak_analysis.json"
        write_json_file(files["run_streak_analysis"], streak_analysis)

    comparison_path = export_comparison_rows(comparison_rows or [], OUTPUT_DIR)
    run_comparison_path = export_comparison_rows(
        comparison_rows or [],
        run_dir,
        filename="preset_comparison.csv",
    )
    if comparison_path is not None:
        files["preset_comparison"] = comparison_path
    if run_comparison_path is not None:
        files["run_preset_comparison"] = run_comparison_path
    files["run_manifest"] = run_dir / "manifest.json"
    manifest = build_run_manifest(
        experiment_id=experiment_id,
        run_dir=run_dir,
        controls=controls or {},
        preset=preset or {},
        config=config or {},
        market_data_summary=market_data_summary,
        exported_files=files,
    )
    write_json_file(files["run_manifest"], manifest)
    return files


def build_run_manifest(
    experiment_id: str,
    run_dir: Path,
    controls: dict[str, Any],
    preset: dict[str, Any],
    config: dict[str, Any],
    market_data_summary: dict[str, Any] | None,
    exported_files: dict[str, Path],
) -> dict[str, Any]:
    input_config = {
        "market_data_path": controls.get("market_data_path"),
        "symbol": controls.get("symbol"),
        "point_value": controls.get("point_value"),
        "data_utc_offset": controls.get("data_utc_offset"),
        "time_filters": {
            "strategy_start_time": controls.get("strategy_start_time"),
            "strategy_end_time": controls.get("strategy_end_time"),
            "force_close_time": controls.get("force_close_time"),
        },
    }
    return {
        "manifest_version": 1,
        "experiment_id": experiment_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_folder": str(run_dir),
        "git": {
            "commit": get_git_commit_hash(),
            "dirty": get_git_dirty_state(),
        },
        "app": {
            "name": "Onix Fondeo Lab",
            "version": APP_VERSION,
        },
        "preset": {
            "preset_id": preset.get("preset_id"),
            "company": preset.get("company"),
            "plan": preset.get("plan"),
            "account_name": preset.get("account_name"),
            "account_size": preset.get("account_size"),
            "is_official": preset.get("is_official"),
            "rules_verified": preset.get("rules_verified"),
        },
        "input": input_config,
        "strategy": {
            "name": controls.get("strategy_name"),
            "parameters": controls.get("strategy_params", {}),
        },
        "risk_settings": {
            "contracts": controls.get("contracts"),
            "stop_loss_points": controls.get("stop_loss_points"),
            "take_profit_points": controls.get("take_profit_points"),
            "max_holding_minutes": controls.get("max_holding_minutes"),
        },
        "cost_settings": {
            "commission_per_side": controls.get("commission_per_side"),
            "slippage_points": controls.get("slippage_points"),
            "spread_points": controls.get("spread_points"),
        },
        "bankroll": {
            "initial_bankroll": controls.get("bankroll"),
            "monte_carlo_runs": controls.get("monte_carlo_runs"),
            "monte_carlo_max_accounts": controls.get("monte_carlo_max_accounts"),
        },
        "simulation_settings": {
            "pass_transition_wait_minutes": controls.get("pass_transition_wait_minutes"),
            "fail_transition_wait_minutes": controls.get("fail_transition_wait_minutes"),
        },
        "comparison": {
            "enabled": controls.get("comparison_enabled"),
            "preset_ids": controls.get("comparison_preset_ids", []),
        },
        "config_summary": {
            "evaluation_enabled": config.get("evaluation", {}).get("enabled"),
            "funded_enabled": config.get("funded", {}).get("enabled"),
            "metadata_keys": sorted(config.get("metadata", {}).keys()),
        },
        "market_data_summary": market_data_summary,
        "artifacts": {
            label: str(path)
            for label, path in exported_files.items()
            if label != "run_folder"
        },
    }


def get_git_commit_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def get_git_dirty_state() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    return bool(result.stdout.strip())


def generate_experiment_id(timestamp: datetime | None = None) -> str:
    timestamp = timestamp or datetime.now()
    return f"{timestamp:%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"


def create_run_output_dir(
    experiment_id: str,
    runs_dir: Path | None = None,
) -> Path:
    runs_dir = runs_dir or RUNS_DIR
    run_dir = runs_dir / experiment_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=str)


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def export_comparison_rows(
    comparison_rows: list[dict[str, Any]],
    output_dir: Path = OUTPUT_DIR,
    filename: str = "app_preset_comparison.csv",
) -> Path | None:
    if not comparison_rows:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    comparison_rows_to_dataframe(comparison_rows).to_csv(output_path, index=False)
    return output_path


def build_trade_diagnostics(trades_df: pd.DataFrame) -> dict[str, Any]:
    if trades_df.empty:
        return {
            "overtrading": {},
            "costs": {},
            "cost_sensitivity": {},
            "cost_sensitivity_table": pd.DataFrame(),
            "quality": {},
            "direction_table": pd.DataFrame(),
            "exit_reason_table": pd.DataFrame(),
            "hourly_table": pd.DataFrame(),
            "daily_table": pd.DataFrame(),
            "weekday_table": pd.DataFrame(),
            "session_table": pd.DataFrame(),
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
    cost_sensitivity = build_cost_sensitivity_summary(net_pnl, gross_pnl, total_cost)

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
        "cost_sensitivity": cost_sensitivity,
        "cost_sensitivity_table": build_cost_sensitivity_table(cost_sensitivity),
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
        "direction_table": build_direction_diagnostics_table(trades),
        "exit_reason_table": _exit_reason_diagnostics_table(trades, net_pnl),
        "hourly_table": _hourly_diagnostics_table(trades, exit_time, net_pnl, total_cost),
        "daily_table": daily_table,
        "weekday_table": _weekday_diagnostics_table(trades, exit_time, net_pnl, total_cost),
        "session_table": _session_diagnostics_table(trades, exit_time, net_pnl, total_cost),
        "best_day": best_day,
        "worst_day": worst_day,
    }


def build_direction_diagnostics_table(trades: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Direction",
        "Trades",
        "WinRate",
        "NetPnL",
        "AverageTrade",
        "TotalCost",
        "AverageWinner",
        "AverageLoser",
        "ProfitFactor",
        "PayoffRatio",
    ]
    if trades.empty or "Direction" not in trades.columns:
        return pd.DataFrame(columns=columns)

    rows = []
    for direction in ["Long", "Short"]:
        direction_trades = trades[trades["Direction"].astype(str) == direction]
        if direction_trades.empty:
            rows.append(_empty_direction_diagnostics_row(direction))
            continue

        net_pnl = _numeric_column(direction_trades, "NetPnL")
        total_cost = _total_cost_series(direction_trades)
        winners = net_pnl[net_pnl > 0]
        losers = net_pnl[net_pnl < 0]
        gross_profit = float(winners.sum())
        gross_loss = float(losers.sum())
        average_winner = float(winners.mean()) if not winners.empty else 0.0
        average_loser = float(losers.mean()) if not losers.empty else 0.0
        payoff_ratio = (
            average_winner / abs(average_loser)
            if average_winner > 0 and average_loser < 0
            else None
        )
        rows.append(
            {
                "Direction": direction,
                "Trades": int(len(direction_trades)),
                "WinRate": _safe_divide_number(len(winners), len(direction_trades)),
                "NetPnL": float(net_pnl.sum()),
                "AverageTrade": float(net_pnl.mean()),
                "TotalCost": float(total_cost.sum()),
                "AverageWinner": average_winner,
                "AverageLoser": average_loser,
                "ProfitFactor": _profit_factor_from_gross(gross_profit, gross_loss),
                "PayoffRatio": payoff_ratio,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_cost_sensitivity_summary(
    net_pnl: pd.Series,
    gross_pnl: pd.Series,
    total_cost: pd.Series,
) -> dict[str, float | None]:
    current_net_pnl = float(net_pnl.sum())
    no_cost_net_pnl = float(gross_pnl.sum())
    total_cost_drag = float(total_cost.sum())
    return {
        "current_net_pnl": current_net_pnl,
        "no_cost_net_pnl": no_cost_net_pnl,
        "total_cost_drag": total_cost_drag,
        "pnl_improvement_without_costs": no_cost_net_pnl - current_net_pnl,
        "cost_drag_percent": _safe_divide_optional(total_cost_drag, abs(no_cost_net_pnl)),
    }


def build_cost_sensitivity_table(cost_sensitivity: dict[str, float | None]) -> pd.DataFrame:
    if not cost_sensitivity:
        return pd.DataFrame(columns=["Scenario", "CostLevel", "ProjectedNetPnL", "CostApplied", "PnLImprovement"])

    no_cost_net_pnl = float(cost_sensitivity["no_cost_net_pnl"] or 0.0)
    total_cost_drag = float(cost_sensitivity["total_cost_drag"] or 0.0)
    current_net_pnl = float(cost_sensitivity["current_net_pnl"] or 0.0)
    rows = []
    for label, cost_level in [
        ("Current costs", 1.0),
        ("Half costs", 0.5),
        ("No costs", 0.0),
    ]:
        cost_applied = total_cost_drag * cost_level
        projected_net_pnl = no_cost_net_pnl - cost_applied
        rows.append(
            {
                "Scenario": label,
                "CostLevel": cost_level,
                "ProjectedNetPnL": projected_net_pnl,
                "CostApplied": cost_applied,
                "PnLImprovement": projected_net_pnl - current_net_pnl,
            }
        )
    return pd.DataFrame(rows)


def _empty_direction_diagnostics_row(direction: str) -> dict[str, Any]:
    return {
        "Direction": direction,
        "Trades": 0,
        "WinRate": 0.0,
        "NetPnL": 0.0,
        "AverageTrade": 0.0,
        "TotalCost": 0.0,
        "AverageWinner": 0.0,
        "AverageLoser": 0.0,
        "ProfitFactor": 0.0,
        "PayoffRatio": None,
    }


def _profit_factor_from_gross(gross_profit: float, gross_loss: float) -> float:
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / abs(gross_loss)


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
        .agg(
            Trades=("NetPnL", "size"),
            NetPnL=("NetPnL", "sum"),
            AverageNetPnL=("NetPnL", "mean"),
            TotalCost=("TotalCost", "sum"),
        )
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
        .agg(
            Trades=("NetPnL", "size"),
            NetPnL=("NetPnL", "sum"),
            AverageNetPnL=("NetPnL", "mean"),
            TotalCost=("TotalCost", "sum"),
        )
        .reset_index()
        .sort_values("Date")
    )


def _weekday_diagnostics_table(
    trades: pd.DataFrame,
    exit_time: pd.Series,
    net_pnl: pd.Series,
    total_cost: pd.Series,
) -> pd.DataFrame:
    columns = ["Weekday", "Trades", "NetPnL", "AverageNetPnL", "TotalCost"]
    if exit_time.isna().all():
        return pd.DataFrame(columns=columns)

    table = pd.DataFrame(
        {
            "Weekday": exit_time.dt.day_name(),
            "WeekdayNumber": exit_time.dt.dayofweek,
            "NetPnL": net_pnl,
            "TotalCost": total_cost,
        }
    ).dropna(subset=["Weekday"])
    if table.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        table.groupby(["WeekdayNumber", "Weekday"])
        .agg(
            Trades=("NetPnL", "size"),
            NetPnL=("NetPnL", "sum"),
            AverageNetPnL=("NetPnL", "mean"),
            TotalCost=("TotalCost", "sum"),
        )
        .reset_index()
        .sort_values("WeekdayNumber")
    )
    return grouped[columns]


def _session_diagnostics_table(
    trades: pd.DataFrame,
    exit_time: pd.Series,
    net_pnl: pd.Series,
    total_cost: pd.Series,
) -> pd.DataFrame:
    columns = ["Session", "Trades", "NetPnL", "AverageNetPnL", "TotalCost"]
    if exit_time.isna().all():
        return pd.DataFrame(columns=columns)

    table = pd.DataFrame(
        {
            "Session": exit_time.dt.hour.apply(classify_session_hour),
            "SessionOrder": exit_time.dt.hour.apply(session_sort_order),
            "NetPnL": net_pnl,
            "TotalCost": total_cost,
        }
    ).dropna(subset=["Session"])
    if table.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        table.groupby(["SessionOrder", "Session"])
        .agg(
            Trades=("NetPnL", "size"),
            NetPnL=("NetPnL", "sum"),
            AverageNetPnL=("NetPnL", "mean"),
            TotalCost=("TotalCost", "sum"),
        )
        .reset_index()
        .sort_values("SessionOrder")
    )
    return grouped[columns]


def classify_session_hour(hour: Any) -> str:
    if pd.isna(hour):
        return "Unknown"
    hour = int(hour)
    if 9 <= hour < 12:
        return "Morning"
    if 12 <= hour < 14:
        return "Midday"
    if 14 <= hour < 17:
        return "Afternoon"
    if 17 <= hour < 20:
        return "Evening"
    return "Overnight"


def session_sort_order(hour: Any) -> int:
    order = {
        "Overnight": 0,
        "Morning": 1,
        "Midday": 2,
        "Afternoon": 3,
        "Evening": 4,
        "Unknown": 5,
    }
    return order[classify_session_hour(hour)]


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

    _ensure_widget_choice("preset_company", companies, DEFAULT_PRESET_COMPANY)
    selected_company = st.selectbox(
        "Company",
        options=companies,
        index=_default_index(companies, DEFAULT_PRESET_COMPANY),
        key="preset_company",
    )
    company_presets = [
        preset for preset in presets if (preset.get("company") or "Unknown") == selected_company
    ]

    plans = sorted({preset.get("plan") or "Unknown" for preset in company_presets})
    if not plans:
        st.error("No plans are available for the selected company.")
        st.stop()

    _ensure_widget_choice("preset_plan", plans, DEFAULT_PRESET_PLAN)
    selected_plan = st.selectbox(
        "Plan",
        options=plans,
        index=_default_index(plans, DEFAULT_PRESET_PLAN),
        key="preset_plan",
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

    _ensure_widget_choice("preset_account_size", sizes, DEFAULT_PRESET_ACCOUNT_SIZE)
    selected_size = st.selectbox(
        "Account Size",
        options=sizes,
        index=_default_index(sizes, DEFAULT_PRESET_ACCOUNT_SIZE),
        format_func=format_account_size,
        key="preset_account_size",
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
    missing_fields = preset.get("missing_fields", [])
    if missing_fields:
        shown_fields = ", ".join(missing_fields[:8])
        remaining = len(missing_fields) - 8
        suffix = f" and {remaining} more" if remaining > 0 else ""
        st.warning(f"Preset is not runnable. Missing fields: {shown_fields}{suffix}.")


def render_preset_rules_panel(preset: dict[str, Any]) -> None:
    with st.expander("Preset rules", expanded=False):
        render_preset_rules_summary(build_preset_rules_summary(preset))


def render_preset_rules_summary(summary: dict[str, Any]) -> None:
    render_metric_grid(
        [
            ("Official", "Yes" if summary["identity"].get("is_official") else "No"),
            ("Verified", "Yes" if summary["identity"].get("rules_verified") else "No"),
            ("Runnable", "Yes" if summary["identity"].get("is_runnable") else "No"),
            ("Account Size", format_account_size(summary["identity"].get("account_size"))),
        ],
        columns_per_row=4,
    )
    st.dataframe(
        pd.DataFrame(preset_rules_rows(summary)),
        hide_index=True,
        use_container_width=True,
    )
    notes = summary["identity"].get("notes")
    if notes:
        st.caption(notes)
    source_url = summary["identity"].get("source_url")
    if source_url:
        st.caption(f"Source: {source_url}")
    missing_fields = summary["identity"].get("missing_fields", [])
    if missing_fields:
        st.warning(f"Missing runnable fields: {', '.join(missing_fields[:12])}")


def build_preset_rules_summary(preset: dict[str, Any]) -> dict[str, Any]:
    is_runnable = preset.get("is_runnable")
    missing_fields = preset.get("missing_fields")
    if is_runnable is None or missing_fields is None:
        is_runnable, missing_fields = validate_preset_is_runnable(preset)

    return {
        "identity": {
            "preset_id": preset.get("preset_id"),
            "company": preset.get("company"),
            "plan": preset.get("plan"),
            "account_name": preset.get("account_name"),
            "account_size": preset.get("account_size"),
            "is_official": preset.get("is_official"),
            "rules_verified": preset.get("rules_verified"),
            "is_runnable": is_runnable,
            "missing_fields": missing_fields,
            "source_url": preset.get("source_url"),
            "last_verified_at": preset.get("last_verified_at"),
            "notes": preset.get("notes"),
        },
        "evaluation": preset_rule_section(
            preset.get("evaluation", {}),
            [
                "enabled",
                "evaluation_cost",
                "profit_target",
                "max_drawdown",
                "max_daily_loss",
                "minimum_trading_days",
                "daily_profit_cap",
                "consistency_enabled",
                "consistency_percent",
            ],
        ),
        "funded": preset_rule_section(
            preset.get("funded", {}),
            [
                "enabled",
                "max_drawdown",
                "max_daily_loss",
                "minimum_withdrawable_profit",
                "payout_trigger_profit",
                "profit_split",
                "reset_after_payout",
            ],
        ),
        "metadata": preset_rule_section(
            preset.get("metadata", {}),
            [
                "drawdown_type",
                "drawdown_breach_type",
                "funded_payout_policy",
                "payout_style",
                "funded_consistency_enabled",
                "funded_consistency_percent",
                "funded_minimum_trading_days_with_profit",
                "minimum_winning_days",
                "winning_day_threshold",
                "minimum_daily_profit",
                "minimum_daily_profit_for_payout_day",
                "payout_minimum",
                "payout_cap",
                "payout_tiers",
                "daily_loss_limit_is_soft_breach",
                "no_activation_fees",
                "close_positions_before",
                "no_overnight_positions",
                "supported_markets",
                "max_sim_funded_accounts",
                "simulation_approximation",
            ],
        ),
    }


def preset_rule_section(source: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: source.get(key) for key in keys if key in source}


def preset_rules_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for section_name in ["identity", "evaluation", "funded", "metadata"]:
        section = summary.get(section_name, {})
        for key, value in section.items():
            if key in {"notes", "source_url", "missing_fields"}:
                continue
            rows.append(
                {
                    "Section": section_name.title(),
                    "Rule": key,
                    "Value": format_rule_value(key, value),
                }
            )
    return rows


def format_rule_value(key: str, value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    if key.endswith("percent") or key in {"profit_split"}:
        try:
            return format_percent(value)
        except (TypeError, ValueError):
            return str(value)
    money_like_fragments = [
        "cost",
        "target",
        "drawdown",
        "loss",
        "profit",
        "payout",
        "balance",
        "cap",
    ]
    if any(fragment in key for fragment in money_like_fragments):
        try:
            return format_currency_full(value)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


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


def _ensure_widget_choice(key: str, options: list[Any], preferred_value: Any) -> None:
    if not options:
        return
    if st.session_state.get(key) in options:
        return
    st.session_state[key] = preferred_value if preferred_value in options else options[0]


def _ensure_multiselect_choices(key: str, options: list[Any]) -> None:
    current = st.session_state.get(key)
    if current is None:
        return
    st.session_state[key] = [value for value in current if value in options]


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
        {"Setting": "Run folder", "Value": analysis_state.get("exported_files", {}).get("run_folder")},
        {"Setting": "Market data path", "Value": input_config.get("market_data_path")},
        {"Setting": "Data UTC offset", "Value": input_config.get("data_utc_offset")},
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
    rows.extend(_dict_rows("Simulation", input_config.get("simulation_settings", {})))
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


def _optional_datetime(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return str(value)


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
