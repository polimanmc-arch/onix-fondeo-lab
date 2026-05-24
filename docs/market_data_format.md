# Market Data Format

Onix Fondeo Lab can generate simulated trades from 1-minute OHLC market data.

The expected input is a CSV file with one row per bar.

## Required Columns

- `DateTime`
- `Open`
- `High`
- `Low`
- `Close`

## Optional Columns

- `Volume`
- `Symbol`

## DateTime Format

Use this format:

```text
YYYY-MM-DD HH:MM:SS
```

Example:

```text
2026-05-20 09:30:00
```

## Price Fields

`Open`, `High`, `Low`, and `Close` must be numeric.

If `Volume` is provided, it must also be numeric.

## Example

```csv
DateTime,Open,High,Low,Close,Volume,Symbol
2026-05-20 09:30:00,19000.00,19010.00,18995.00,19005.00,1200,NQ
2026-05-20 09:31:00,19005.00,19012.00,19001.00,19008.00,980,NQ
```

Signals are generated at the current bar close. The backtester enters on the
next bar open to avoid lookahead bias.
