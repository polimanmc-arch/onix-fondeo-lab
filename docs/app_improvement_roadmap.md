# Onix Fondeo Lab App Improvement Roadmap

This document tracks product-quality improvements for the Streamlit app.
It is meant to be a practical checklist so each improvement can be implemented,
tested, committed, and shipped one at a time.

## Working Principles

- Keep the engine reusable and independent from the app.
- Prefer small, testable improvements.
- Preserve the current single-analysis workflow.
- Do not commit real market data.
- Run tests before every commit:

```powershell
$env:PYTHONPATH='src'; python -m pytest
```

## Completed App Improvements

### 1. Four Core Tabs

Status: Done

The app is organized into:

- Dashboard
- Backtest
- Funding & Risk
- Data

Acceptance criteria:

- Old scattered tabs are merged into the four core tabs.
- Analysis results persist when interacting with widgets.

### 2. Session State Persistence

Status: Done

Analysis results are stored in `st.session_state` so user interactions do not
erase the dashboard.

Acceptance criteria:

- Clicking filters, tabs, and trade controls does not require rerunning analysis.
- If no analysis exists, the app prompts the user to run one.

### 3. Trade Explorer

Status: Done

The Backtest tab includes a Trade Explorer with:

- Trade filters
- TradeID selector
- Candlestick chart around selected trade
- Entry and exit markers
- SL/TP levels
- Stochastic K/D panel when using stochastic strategy

Acceptance criteria:

- User can inspect individual trades without losing app state.
- Selected TradeID remains stable or resets safely when filters change.

### 4. Market Data Selector And Validator

Status: Done

The sidebar can list `.csv` files from `data/market_data` and validate an OHLC
file before running analysis.

Acceptance criteria:

- The user can select sample or real market data files from the UI.
- The validator reports whether the file passed loader checks.
- The Data tab shows market data quality after a run.

### 5. Saved Analysis Setups

Status: Done

The app supports local JSON setups in `data/app_setups`.

Acceptance criteria:

- User can save current sidebar settings.
- User can load saved settings.
- User can delete saved settings.
- Saved setup files are ignored by git.

### 6. Funding Preset Rules Panel

Status: Done

The app shows a human-readable rules panel for the selected funding preset.

Acceptance criteria:

- Sidebar exposes preset rules before running.
- Data tab preserves selected preset rules after running.
- Official, verified, runnable, evaluation, funded, metadata, source, and notes
  are visible.

### 7. Account Summary Table

Status: Done

Funding & Risk includes a compact account-level summary.

Acceptance criteria:

- Shows evaluation and funded rows separately.
- Includes pass/fail/active status, PnL, payouts, drawdown state, and dates.
- Supports basic filters and CSV download.

### 8. Account Event Timeline

Status: Done

Funding & Risk includes a timeline of account and business events.

Acceptance criteria:

- Shows account openings, costs, passes, fails, payouts, and important status
  reasons.
- Supports filtering by event type and account.
- Supports CSV download.

### 9. Improved Bankroll Chart

Status: Done

Bankroll chart includes event markers and annotated important events.

Acceptance criteria:

- Bankroll line is visible.
- Costs/losses and positive events are visually distinct.
- Bankroll curve table is formatted.

### 10. Streamlit Preset Comparison

Status: Done

The app can compare multiple runnable presets using the same generated trades.

Acceptance criteria:

- User can select multiple runnable presets.
- Backtest is generated once.
- Each preset is simulated against the same trades.
- Dashboard shows ranking cards, filtered comparison table, visual rankings,
  and CSV download.

## Next Improvements

### 11. Run Folder And Experiment ID

Status: Done

Create a reproducible run folder for each analysis.

Proposed behavior:

- Generate an `experiment_id` for each run.
- Create a folder like:

```text
data/runs/YYYYMMDD_HHMMSS_experiment_id/
```

- Save:
  - generated trades
  - strategy metrics
  - business metrics
  - account summary
  - account timeline
  - bankroll curve
  - risk of ruin metrics
  - selected setup/config snapshot

Acceptance criteria:

- Every run has a unique ID.
- Data tab shows the run folder.
- Outputs remain reproducible.
- `data/runs/` is ignored by git except optional `.gitkeep`.

### 12. Full Run Manifest

Status: Done

Save a machine-readable manifest for each run.

Manifest should include:

- experiment_id
- timestamp
- git commit hash if available
- market data path
- selected preset_id
- strategy parameters
- risk settings
- cost settings
- bankroll and Monte Carlo settings
- app/engine version if available

Acceptance criteria:

- A `manifest.json` exists inside each run folder.
- Data tab can show the manifest.

### 13. Strategy Long/Short Diagnostics

Status: Done

Split strategy metrics by direction.

Acceptance criteria:

- Backtest tab shows Long vs Short:
  - trade count
  - win rate
  - net PnL
  - average trade
  - total cost
- Works if only one direction exists.

### 14. Session And Time-Of-Day Diagnostics

Status: Done

Improve time diagnostics into product-quality sections.

Acceptance criteria:

- Show performance by hour.
- Show performance by date.
- Show performance by day of week.
- Optionally group by custom sessions such as morning, midday, afternoon, and
  overnight.

### 15. Cost Sensitivity View

Status: Done

Compare strategy results with and without trading costs.

Acceptance criteria:

- Show current net PnL after costs.
- Show hypothetical net PnL before costs.
- Show total cost drag.
- Warn when costs dominate the result.

### 16. Account Rule Audit Table

Status: Done

Show exactly which rules affected each account.

Acceptance criteria:

- Display account-aware exits.
- Display consistency blocks.
- Display winning-day blocks.
- Display daily-continuity blocks.
- Display EOD drawdown state when available.

### 17. Preset Comparison Detail View

Status: Done

Add a richer comparison section for presets.

Acceptance criteria:

- Filter by company, plan, account size.
- Rank by net PnL, ROI, payouts, final bankroll, and ruin probability.
- Show best/worst preset cards.
- Export comparison CSV.

### 18. Account Cycle Registry

Status: Done

Create a progressive registry for the complete run, inspired by account/cycle
research logs. Each row represents an account phase/cycle inside the run and
captures how the account moved through evaluation, funded, payout, failure, and
rule events.

Acceptance criteria:

- Export `account_cycle_registry.csv` in each run folder.
- Show Account Cycle Registry in Funding & Risk.
- Include preset identity, account identity, phase, status, start/end times,
  trades, wins/losses, PnL, target/drawdown distance, payouts, session PnL,
  rule event counts, and key strategy/risk/cost settings.
- Export the registry even for one-account runs.

### 19. Account Transition Wait Time

Status: Next

Add a configurable wait time between account transitions. For example, if an
evaluation passes, wait 60 minutes before the funded account can start taking
trades. This prevents unrealistic immediate trading on the next account.

Acceptance criteria:

- Sidebar input for account transition wait minutes.
- Simulation skips trades during the transition window.
- Works for evaluation-to-funded and failed-account-to-new-evaluation flows.
- Account Cycle Registry records transition timing.

### 20. Phase Risk Management Presets

Status: Planned

Allow different execution/risk profiles based on the stage of an account.
Examples:

- Evaluation first trade / first day.
- Evaluation continuation after a winning first day.
- Evaluation final push when only a small amount remains to target.
- Funded first day.
- Funded continuation days.

Acceptance criteria:

- UI can define named phase risk profiles.
- Profiles can override contracts, SL, TP, max holding, costs, and force close.
- Backtest/simulator can select the correct profile according to account state.
- Account Cycle Registry records which profile was used.

### 21. Strategy Configuration Workspace

Status: Planned

Move strategy configuration out of the sidebar into its own app area/tab so the
sidebar stays focused on high-level run controls.

Acceptance criteria:

- Dedicated strategy configuration tab or workspace.
- Random and Stochastic parameters are easier to read and edit.
- Current setup save/load still works.
- Dashboard shows a compact strategy summary.

### 22. Funding Preset Builder And Editor

Status: Planned

Allow creating and editing funding company presets from the app instead of only
using fixed JSON files.

Acceptance criteria:

- User can create a preset from scratch.
- User can edit a local custom preset.
- Custom presets are saved outside tracked official presets.
- App validates whether a custom preset is runnable.

### 23. Funding Preset Templates

Status: Planned

Provide templates for common account structures so new presets can be created
quickly and safely.

Acceptance criteria:

- Evaluation + funded template.
- Straight-to-funded template.
- Select-style payout template.
- Lightning-style direct funded template.
- Template output can be validated as runnable or show missing fields.

### 24. Risk Of Ruin Visuals

Status: Planned

Make Monte Carlo results easier to interpret.

Acceptance criteria:

- Plot histogram of final bankroll.
- Plot sample Monte Carlo paths.
- Show percentile bands.
- Show required bankroll grid visually.

### 25. Streak Diagnostics Visuals

Status: Planned

Improve sequence diagnostics.

Acceptance criteria:

- Show payout/no-payout sequence.
- Show net-positive/net-negative account sequence.
- Show max droughts clearly.
- Explain Z-score in the UI.

### 26. Data Quality Report

Status: Planned

Turn market-data validation into a fuller report.

Acceptance criteria:

- Detect date range.
- Detect duplicate DateTime rows.
- Detect likely missing candles.
- Show time-of-day coverage.
- Show symbol and price range.

### 27. NinjaTrader Converter UI

Status: Planned

Expose NinjaTrader raw export conversion from Streamlit.

Acceptance criteria:

- User can choose raw `.txt` or `.csv`.
- User can enter symbol.
- App writes standardized CSV to `data/market_data`.
- App validates converted output.

### 28. Strategy Presets

Status: Planned

Allow saving named strategy parameter presets separately from full app setups.

Acceptance criteria:

- User can save stochastic settings.
- User can load a strategy preset.
- Strategy presets are local and ignored by git.

### 29. Basic Optimization UI

Status: Planned

Expose existing stochastic optimization in the app.

Acceptance criteria:

- User can choose grid size.
- User can choose max runs.
- User can run against selected preset(s).
- Results show top rows and export paths.

### 30. Error Handling Pass

Status: Planned

Make app errors clearer and more actionable.

Acceptance criteria:

- Common errors produce friendly messages.
- Full traceback is hidden unless user expands details.
- Missing dependency and missing file messages are clear.

### 31. App Smoke Test Script

Status: Planned

Create a repeatable app smoke test.

Acceptance criteria:

- Script starts Streamlit.
- Loads the app.
- Runs the default analysis.
- Checks expected tab text.
- Stops Streamlit.
## Parking Lot

These are valuable but should wait until the app workflow is stable:

- PDF report export
- Cloud deployment
- Authentication
- Database-backed experiment history
- Live trading or live NinjaTrader integration
- Multi-user collaboration

