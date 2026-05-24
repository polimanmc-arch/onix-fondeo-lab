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

Compare multiple presets:

```bash
PYTHONPATH=src python -m onix_fondeo.main --compare tradeify_growth_50k tradeify_select_flex_50k tradeify_lightning_funded_50k
```

Compare Lucid Trading vs Tradeify:

```bash
PYTHONPATH=src python -m onix_fondeo.main --compare lucid_trading_lucidflex_50k tradeify_growth_50k
```

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
