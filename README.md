# Onix Fondeo Lab

Onix Fondeo Lab is a Python simulator that takes backtest trades and evaluates
how a strategy would perform under funding account rules.

## What It Does

This project is not only a trading backtest. It simulates the business reality
of running strategies through funded trading accounts, including:

- evaluation costs
- passed accounts
- failed accounts
- funded accounts
- payouts
- real business PnL

## Current MVP Features

- Load trades from CSV
- Load funding rules from JSON
- Simulate evaluation accounts
- Simulate funded/payout phase
- Register evaluation costs
- Register payouts
- Export CSV and JSON reports
- Calculate business metrics
- Run automated tests

## Input File

The main input file is:

```text
data/input/sample_trades.csv
```

Expected columns:

```text
TradeID, EntryTime, ExitTime, Symbol, Direction, Quantity, NetPnL
```

## Config Files

The simulator uses these JSON configuration files:

- `config/evaluation_rules.json`: evaluation account rules such as profit target,
  drawdown, minimum trading days, daily profit cap, and consistency rule.
- `config/funded_rules.json`: funded account rules such as drawdown, payout
  trigger, profit split, and payout reset behavior.
- `config/simulation_settings.json`: simulation behavior such as account
  recycling, continuing after passed evaluations, and maximum accounts.

## Output Files

Simulation results are exported to:

- `data/output/account_summary.csv`
- `data/output/trade_log_simulated.csv`
- `data/output/payout_summary.csv`
- `data/output/business_events.csv`
- `data/output/business_metrics.json`

## OHLC Backtesting Layer

Onix Fondeo Lab can also generate trades from 1-minute OHLC market data before
passing those trades into the funding simulator.

The OHLC input format is documented in:

```text
docs/market_data_format.md
```

A practical guide for exporting/preparing real futures data from NinjaTrader or
another platform is available at:

```text
docs/ninjatrader_data_export.md
```

Real OHLC data can come from NinjaTrader or another futures data vendor as long
as it includes the required columns or one of the supported aliases documented
above.

Raw NinjaTrader historical exports in
`YYYYMMDD HHMMSS;Open;High;Low;Close;Volume` format can be converted to the
standard project CSV format with `convert_ninjatrader_export_to_csv` from
`onix_fondeo.market_data`.

Download full 1-minute futures data when possible. Use CLI time filters, such
as `--strategy-start-time` and `--strategy-end-time`, to decide when strategies
are allowed to trade.

Current strategies:

- Random Entry Strategy: a reproducible benchmark strategy that creates random
  long/short entries.
- Stochastic Level Strategy: a simple logic-based strategy using stochastic
  oscillator level crosses.

Generated trades use the same key columns as the existing trade CSV workflow:

```text
TradeID, EntryTime, ExitTime, Symbol, Direction, Quantity, NetPnL
```

That means OHLC-generated trades can be passed into the existing funding
simulator without changing the funding simulation engine.

When `--market-data` is used, the generated strategy trades are exported to:

- `data/output/generated_trades.csv`
- `data/output/strategy_metrics.json`

Strategy metrics describe the raw generated trades before funding rules are
applied. They are separate from funding metrics such as evaluation cost, pass
rate, payout rate, and business PnL. When trades are generated from market data,
`data/output/report.html` also includes a Strategy Summary section.

## How To Install

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

## How To Run

Run with the default config files:

```bash
PYTHONPATH=src python -m onix_fondeo.main
```

Run with a preset:

```bash
PYTHONPATH=src python -m onix_fondeo.main --preset tradeify_growth_50k
PYTHONPATH=src python -m onix_fondeo.main --preset lucid_trading_luciddirect_50k
```

List available presets:

```bash
PYTHONPATH=src python -m onix_fondeo.main --list-presets
```

Run with a custom trades CSV:

```bash
PYTHONPATH=src python -m onix_fondeo.main --trades data/input/sample_trades.csv --preset tradeify_select_flex_50k
```

Generate trades from OHLC data with the stochastic strategy:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/NQ_1m.csv --strategy stochastic --preset tradeify_growth_50k
```

Run a random strategy comparison from the same OHLC data:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/NQ_1m.csv --strategy random --compare tradeify_growth_50k lucid_trading_lucidflex_50k
```

Customize stop loss and take profit:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/NQ_1m.csv --strategy stochastic --preset tradeify_growth_50k --stop-loss-points 25 --take-profit-points 50
```

Run stochastic cross mode:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/sample_NQ_1m.csv --strategy stochastic --stoch-signal-mode cross --preset tradeify_growth_50k
```

Run stochastic zone mode with %D confirmation:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/sample_NQ_1m.csv --strategy stochastic --stoch-signal-mode zone --stoch-use-d-confirmation --stoch-min-k-d-gap 2 --stoch-cooldown-bars 5 --preset tradeify_growth_50k
```

Run stochastic entries during the morning and force close near market close:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/NQ_1m.csv --strategy stochastic --strategy-start-time 09:30 --strategy-end-time 11:30 --force-close-time 15:55 --preset tradeify_growth_50k
```

Run a custom evening window:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/NQ_1m.csv --strategy stochastic --strategy-start-time 16:35 --strategy-end-time 18:30 --force-close-time 22:55 --preset tradeify_growth_50k
```

Run stochastic optimization on one preset:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/sample_NQ_1m.csv --preset tradeify_growth_50k --max-optimization-runs 20
```

Run fast stochastic optimization on one week of MNQ data:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/MNQ_1m.csv --preset tradeify_growth_50k --optimization-grid fast --optimization-start-date 2026-03-12 --optimization-end-date 2026-03-19 --symbol MNQ --point-value 2
```

Limit optimization runs:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/MNQ_1m.csv --preset tradeify_growth_50k --optimization-grid fast --max-optimization-runs 10 --symbol MNQ --point-value 2
```

Run parallel fast optimization:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/MNQ_1m.csv --preset tradeify_growth_50k --optimization-grid fast --optimization-workers 4 --symbol MNQ --point-value 2
```

Run parallel optimization across presets:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/MNQ_1m.csv --compare tradeify_growth_50k lucid_trading_lucidflex_50k --optimization-grid fast --optimization-workers 4 --symbol MNQ --point-value 2
```

Run optimization report rankings with a minimum trades filter:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/MNQ_1m.csv --preset tradeify_growth_50k --optimization-grid fast --optimization-workers 4 --optimization-min-trades 30 --symbol MNQ --point-value 2
```

Compare presets with a minimum trades filter:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/MNQ_1m.csv --compare tradeify_growth_50k lucid_trading_lucidflex_50k --optimization-grid fast --optimization-workers 4 --optimization-min-trades 30 --symbol MNQ --point-value 2
```

Compare stochastic optimization across presets:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/sample_NQ_1m.csv --compare tradeify_growth_50k lucid_trading_lucidflex_50k --max-optimization-runs 20
```

After optimization, open:

```text
data/output/optimization_report.html
```

Compare multiple presets:

```bash
PYTHONPATH=src python -m onix_fondeo.main --compare tradeify_growth_50k tradeify_select_flex_50k tradeify_lightning_funded_50k
```

Compare Lucid Trading vs Tradeify:

```bash
PYTHONPATH=src python -m onix_fondeo.main --compare lucid_trading_lucidflex_50k tradeify_growth_50k
```

Run a single simulation with bankroll tracking:

```bash
PYTHONPATH=src python -m onix_fondeo.main --preset tradeify_growth_50k --bankroll 3000
```

Run an OHLC strategy with bankroll tracking:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/MNQ_1m.csv --strategy stochastic --preset tradeify_growth_50k --symbol MNQ --point-value 2 --bankroll 3000
```

Run MNQ with realistic trade costs:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/MNQ_1m.csv --strategy stochastic --preset tradeify_growth_50k --symbol MNQ --point-value 2 --contracts 1 --commission-per-side 1.24 --slippage-points 0.25 --spread-points 0.25
```

Run stochastic optimization with costs:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/MNQ_1m.csv --preset tradeify_growth_50k --optimization-grid fast --optimization-workers 4 --symbol MNQ --point-value 2 --contracts 1 --commission-per-side 1.24 --slippage-points 0.25 --spread-points 0.25
```

For futures, MNQ point value is typically `2` and NQ point value is typically
`20`. Commissions, slippage, and spread can materially change near-break-even
strategies, so include realistic costs before trusting optimization rankings.

Use phase risk profiles with aggressive evaluation and conservative funded
execution:

```bash
PYTHONPATH=src python -m onix_fondeo.main \
  --market-data data/market_data/MNQ_1m.csv \
  --strategy stochastic \
  --preset tradeify_growth_50k \
  --symbol MNQ \
  --point-value 2 \
  --use-phase-profiles \
  --evaluation-contracts 3 \
  --evaluation-stop-loss-points 30 \
  --evaluation-take-profit-points 45 \
  --funded-contracts 1 \
  --funded-stop-loss-points 20 \
  --funded-take-profit-points 30 \
  --commission-per-side 1.24 \
  --slippage-points 0.25 \
  --spread-points 0.25 \
  --bankroll 3000
```

Phase profiles use the same signal logic but different execution and risk
settings. Evaluation can be more aggressive to seek passing the account, while
funded can be more conservative to protect consistency and pursue payouts. This
is an initial approximation before fully account-aware intratrade exits.

## Account-Aware Exits

The funding simulator can clip trade PnL when an account-level rule is reached:

- evaluation profit target
- funded payout trigger
- max drawdown / max loss
- daily loss limit

This prevents unrealistic overshooting of funding rules in the simulation trade
log. The adjustment is based on trade-level `NetPnL`, not tick-by-tick
intratrade path data yet. A future version may integrate account-aware exits
directly into the OHLC backtester.

## Risk Of Ruin

Run Monte Carlo risk-of-ruin analysis from account-level historical outcomes:

```bash
PYTHONPATH=src python -m onix_fondeo.main --preset tradeify_growth_50k --bankroll 3000 --monte-carlo-runs 10000 --monte-carlo-max-accounts 100
```

Run OHLC strategy risk of ruin with realistic MNQ costs:

```bash
PYTHONPATH=src python -m onix_fondeo.main \
  --market-data data/market_data/MNQ_1m.csv \
  --strategy stochastic \
  --preset tradeify_growth_50k \
  --symbol MNQ \
  --point-value 2 \
  --contracts 1 \
  --commission-per-side 1.24 \
  --slippage-points 0.25 \
  --spread-points 0.25 \
  --bankroll 3000 \
  --monte-carlo-runs 10000 \
  --monte-carlo-max-accounts 100
```

This Monte Carlo engine samples observed account-level outcomes with
replacement. It is useful for estimating capital needs and ruin risk, but it is
not a guarantee of future performance.

## Streak Analysis and Z-score

Streak analysis helps understand bad streaks, payout droughts, and clustering in
account outcomes. It complements bankroll tracking and Monte Carlo risk of ruin
by showing sequence behavior directly.

Example:

```bash
PYTHONPATH=src python -m onix_fondeo.main --preset tradeify_growth_50k --bankroll 3000 --monte-carlo-runs 1000
```

The output includes:

- `data/output/streak_analysis.json`
- a Streak Analysis section in `data/output/report.html`

The Z-score is a runs-test style diagnostic. It can suggest unusual clustering
or alternation in binary outcome sequences, but it is not a guarantee of future
performance.

Compare presets with bankroll tracking:

```bash
PYTHONPATH=src python -m onix_fondeo.main --compare tradeify_growth_50k lucid_trading_lucidflex_50k --bankroll 3000
```

Bankroll tracking starts with the initial capital supplied by `--bankroll`.
Evaluation costs reduce bankroll, and net payouts increase bankroll. Ruin means
the bankroll went below zero at some point in the historical event path. This is
historical/path-based bankroll tracking, not Monte Carlo simulation yet.

After comparison, open:

```text
data/output/comparison_report.html
```

## How To Run Tests

```bash
PYTHONPATH=src pytest
```

## Roadmap

- Add HTML report
- Add better visual dashboard
- Add NinjaTrader CSV exporter
- Add support for multiple funding company presets
- Add Monte Carlo/randomized account simulations
- Add web app interface
