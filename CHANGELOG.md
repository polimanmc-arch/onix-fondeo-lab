# Changelog

All notable project changes should be recorded here.

The format is intentionally simple and practical. New entries should be added
under `Unreleased` until a stable tag is created.

## Unreleased

### Added

- Streamlit app improvement roadmap.
- Professional development workflow documentation.
- Local check script for compile, tests, and staged market-data safety.
- Streamlit run folders with unique experiment IDs and reproducible app artifacts.
- Full Streamlit run manifest with git, setup, strategy, risk, cost, and artifact metadata.
- Streamlit Long vs Short strategy diagnostics in the Backtest tab.

### Notes

- Real market data should stay out of git.
- Run `.\scripts\check.ps1` before commits.

## v1.6.0

### Current Stable Baseline

- Streamlit visual app with Dashboard, Backtest, Funding & Risk, and Data tabs.
- Funding presets for Lucid Trading and Tradeify.
- OHLC backtester and NinjaTrader-style Stochastic strategy.
- Trade costs, phase profiles, and account-aware exits.
- Bankroll engine, Monte Carlo risk of ruin, and streak analysis.
- Trade explorer with selected TradeID chart.
- Market data selector and validator.
- Saved analysis setups.
- Funding preset rules panel.
- Account summary and account event timeline.
- Improved bankroll chart.
- Streamlit preset comparison visuals.
