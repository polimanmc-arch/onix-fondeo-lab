# Market Data Format

Onix Fondeo Lab can generate simulated trades from 1-minute OHLC market data.

The expected input is a CSV file with one row per bar.

## Data Philosophy

When possible, export and store all available 1-minute futures trading hours.

- Store full ETH/session data.
- Do not pre-filter overnight, RTH, ETH, or custom session candles before saving.
- Apply trading time filters at strategy/backtest runtime.

This keeps the raw market data reusable. You can test RTH, ETH, overnight,
custom sessions, and funding-specific trading windows without downloading a new
file for every experiment. It also makes optimization more flexible.

Example runtime filters:

```bash
--strategy-start-time 09:30 --strategy-end-time 11:30
--strategy-start-time 16:35 --strategy-end-time 18:30
--strategy-start-time 18:00 --strategy-end-time 23:00
```

Use `--strategy-start-time` and `--strategy-end-time` to decide when strategies
are allowed to open trades. Use `--force-close-time` to close any still-open
trade before a risk or session cutoff:

```bash
--strategy-start-time 09:30 --strategy-end-time 11:30 --force-close-time 15:55
--strategy-start-time 16:35 --strategy-end-time 18:30 --force-close-time 22:55
```

## Required Columns

- `DateTime`
- `Open`
- `High`
- `Low`
- `Close`

## Optional Columns

- `Volume`
- `Symbol`

## Supported Column Aliases

The loader normalizes common vendor and NinjaTrader-style column names:

- `Time`, `Date`, `Datetime`, `Timestamp` -> `DateTime`
- `O` -> `Open`
- `H` -> `High`
- `L` -> `Low`
- `C`, `Last` -> `Close`
- `Vol` -> `Volume`

Column-name whitespace is stripped before alias matching. Unknown columns are
preserved.

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

## Data Quality Rules

Rows must satisfy basic OHLC consistency:

- `High` must be greater than or equal to both `Open` and `Close`.
- `Low` must be less than or equal to both `Open` and `Close`.
- `DateTime` must be parseable.
- Price fields must be numeric.

Duplicate `DateTime` rows are dropped by default when loading data, keeping the
last occurrence.

If a `timezone` is provided to the loader, it is stored in
`df.attrs["timezone"]`. Timezone conversion is not performed yet.

Futures session handling, such as official exchange session boundaries, will be
added later.

The loader does not remove candles by time of day. It reads, normalizes,
validates, sorts, and returns the full OHLC dataset.

## Example

```csv
DateTime,Open,High,Low,Close,Volume,Symbol
2026-05-20 09:30:00,19000.00,19010.00,18995.00,19005.00,1200,NQ
2026-05-20 09:31:00,19005.00,19012.00,19001.00,19008.00,980,NQ
```

Signals are generated at the current bar close. The backtester enters on the
next bar open to avoid lookahead bias.
