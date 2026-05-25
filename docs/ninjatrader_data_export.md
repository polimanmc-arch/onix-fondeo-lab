# Importing Real Futures OHLC Data

This guide explains how to prepare real 1-minute futures OHLC data for Onix
Fondeo Lab.

## Purpose

Onix Fondeo Lab can backtest strategies from OHLC market data and then pass the
generated trades into the funding account simulator. This lets you test both:

- raw strategy behavior
- funding-account business outcomes

## Recommended File Location

Place real market data files in:

```text
data/market_data/
```

Example file names:

- `NQ_1m.csv`
- `MNQ_1m.csv`
- `ES_1m.csv`
- `MES_1m.csv`

## Recommended Data Philosophy

When possible, export/download all available 1-minute futures trading hours.

- Store full ETH/session data.
- Do not pre-filter overnight, RTH, ETH, or custom session candles before saving.
- Apply trading filters later inside Onix Fondeo Lab.

Why this matters:

- You can test RTH, ETH, overnight, custom sessions, and funding-specific
  trading windows from the same raw file.
- You avoid re-downloading data for every new test.
- Optimization runs can compare different trading windows more flexibly.

Example runtime filters:

```bash
--strategy-start-time 09:30 --strategy-end-time 11:30
--strategy-start-time 16:35 --strategy-end-time 18:30
--strategy-start-time 18:00 --strategy-end-time 23:00
```

## Required Columns

The preferred column names are:

- `DateTime`
- `Open`
- `High`
- `Low`
- `Close`

Optional columns:

- `Volume`
- `Symbol`

## Accepted Aliases

The loader also supports common aliases from trading platforms and data vendors:

- `Time`, `Date`, `Datetime`, `Timestamp` -> `DateTime`
- `O` -> `Open`
- `H` -> `High`
- `L` -> `Low`
- `C`, `Last` -> `Close`
- `Vol` -> `Volume`

Column-name whitespace is stripped automatically.

## Recommended Final Format

```csv
DateTime,Open,High,Low,Close,Volume,Symbol
2024-01-02 09:30:00,16800.25,16810.50,16795.75,16805.25,1234,NQ
```

## NinjaTrader Workflow

NinjaTrader versions, data providers, and enabled features can vary, so treat
this as a practical high-level workflow rather than exact menu-by-menu
instructions.

1. Open NinjaTrader.
2. Use the platform's historical data or export tools, if available.
3. Select the futures instrument, for example `NQ` or `MNQ`.
4. Select minute data.
5. Choose the date range you want to test.
6. Export the data as CSV. When possible, export all available trading hours
   rather than only RTH.
7. Rename the file, for example `NQ_1m.csv`.
8. Move it to:

```text
data/market_data/
```

If the exported columns use aliases such as `Time`, `O`, `H`, `L`, `C`, or
`Vol`, the project loader can normalize them automatically.

## Data Quality Checklist

Before running a backtest, check that:

- There is one row per 1-minute candle.
- `DateTime` is present and not missing.
- Prices are numeric.
- `High` is greater than or equal to both `Open` and `Close`.
- `Low` is less than or equal to both `Open` and `Close`.
- Duplicate `DateTime` rows are removed, or understand that the loader drops
  duplicates by default and keeps the last occurrence.
- Timezone is known and consistent across the file.

Timezone conversion and official futures session handling will be added later.

## Test The File

Run a stochastic strategy against the file and simulate funding outcomes:

```bash
PYTHONPATH=src python -m onix_fondeo.main --market-data data/market_data/NQ_1m.csv --strategy stochastic --preset tradeify_growth_50k
```

Generated trades will be exported to:

```text
data/output/generated_trades.csv
```

Strategy metrics will be exported to:

```text
data/output/strategy_metrics.json
```

## Optimize With Real Data

Run a small stochastic optimization:

```bash
PYTHONPATH=src python -m onix_fondeo.main --optimize-strategy stochastic --market-data data/market_data/NQ_1m.csv --preset tradeify_growth_50k --max-optimization-runs 20
```

Optimization results are exported to:

```text
data/output/optimization_results.csv
data/output/optimization_report.html
```
