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

    if not controls["run_analysis"]:
        st.info("Configure the sidebar and click Run Analysis.")
        return

    try:
        run_analysis(controls)
    except Exception as error:
        st.error(f"Analysis failed: {error}")


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
        "k_period": st.number_input("K period", min_value=1, value=20, step=1),
        "d_period": st.number_input("D period", min_value=1, value=5, step=1),
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

    exported_files = export_app_outputs(
        trades,
        strategy_metrics,
        business_metrics,
        bankroll_result,
        streak_analysis,
        risk_result,
        required_bankroll,
    )

    render_outputs(
        trades,
        strategy_metrics,
        business_metrics,
        bankroll_result,
        streak_analysis,
        risk_result,
        required_bankroll,
        exported_files,
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
        k_period=int(params["k_period"]),
        d_period=int(params["d_period"]),
        oversold_level=params["oversold"],
        overbought_level=params["overbought"],
        signal_mode=params["signal_mode"],
        use_d_confirmation=params["use_d_confirmation"],
        min_k_d_gap=params["min_k_d_gap"],
        cooldown_bars=int(params["cooldown_bars"]),
        start_time=controls["strategy_start_time"],
        end_time=controls["strategy_end_time"],
    )


def render_outputs(
    trades,
    strategy_metrics: dict[str, Any],
    business_metrics: dict[str, Any],
    bankroll_result: dict[str, Any] | None,
    streak_analysis: dict[str, Any],
    risk_result: dict[str, Any] | None,
    required_bankroll: dict[str, Any] | None,
    exported_files: dict[str, Path],
) -> None:
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

    if bankroll_result is not None:
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

    if risk_result is not None:
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

    st.subheader("Generated Trades")
    st.dataframe(trades.head(500), use_container_width=True)

    st.subheader("Exported Files")
    for label, path in exported_files.items():
        st.write(f"{label}: `{path}`")


def export_app_outputs(
    trades,
    strategy_metrics: dict[str, Any],
    business_metrics: dict[str, Any],
    bankroll_result: dict[str, Any] | None,
    streak_analysis: dict[str, Any],
    risk_result: dict[str, Any] | None,
    required_bankroll: dict[str, Any] | None,
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
    }
    with files["summary_metrics"].open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, default=str)
    return files


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
