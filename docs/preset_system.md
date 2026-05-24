# Funding Preset System

## What Is a Preset?

A preset represents a funding account product/card.

For example:

```text
Lucid Trading - LucidFlex 50K
```

Presets let Onix Fondeo Lab show available funding account products and, when
their rules are complete and verified, convert those products into simulator
configuration.

## Current Preset Structure

Each preset is a JSON file with these top-level fields:

- `company`
- `plan`
- `account_name`
- `account_type`
- `account_size`
- `is_official`
- `rules_verified`
- `source_url`
- `last_verified_at`
- `notes`
- `evaluation`
- `funded`
- `simulation`

The `evaluation`, `funded`, and `simulation` objects match the structure used by
the simulator config.

## `is_official`

`is_official` means the rules came from an official company source.

Use `true` only when the values were taken from an official source, such as the
funding company's own website, dashboard, contract, rule page, or official
documentation.

## `rules_verified`

`rules_verified` means the preset values have been checked and are ready to be
used for simulation.

A preset can be unofficial but still verified if the team has confirmed the
rules from a trusted non-official workflow. However, `is_official` should only
be `true` when the source itself is official.

## Runnable Presets

A preset is runnable only if all required simulation fields are filled.

Template cards can appear in the HTML report even when they are not runnable.
This lets the project show the available product catalog without pretending that
unverified rules are ready for real simulation.

## Why Some Fields Are `null`

Some fields are `null` because we do not want to invent funding company rules.

`null` means:

- the value has not been verified yet
- the preset is a template/card only
- the preset should not be used for real simulation until completed

## How To Complete a Preset

To complete a preset:

1. Verify rules from an official company source.
2. Fill all missing required fields.
3. Set `source_url` to the rule source.
4. Set `last_verified_at` to the verification date.
5. Set `rules_verified` to `true`.
6. Keep `is_official` as `true` only if the source is official.

## Required Fields

If `evaluation.enabled` is `true`, these evaluation fields are required:

- `evaluation_cost`
- `profit_target`
- `max_drawdown`
- `minimum_trading_days`
- `daily_profit_cap`
- `consistency_enabled`
- `consistency_percent`

If `funded.enabled` is `true`, these funded fields are required:

- `max_drawdown`
- `minimum_withdrawable_profit`
- `payout_trigger_profit`
- `profit_split`
- `reset_after_payout`

## Completed Preset Snippet

Example only:

```json
{
  "preset_id": "lucid_trading_lucidflex_50k",
  "company": "Lucid Trading",
  "plan": "LucidFlex",
  "account_name": "LucidFlex 50K",
  "account_type": "LucidFlex",
  "account_size": 50000,
  "is_official": true,
  "rules_verified": true,
  "source_url": "https://example.com/official-rules",
  "last_verified_at": "2026-05-23",
  "notes": "Rules verified from official source.",
  "evaluation": {
    "enabled": true,
    "account_size": 50000,
    "evaluation_cost": 100,
    "profit_target": 3000,
    "max_drawdown": 2000,
    "max_daily_loss": null,
    "minimum_trading_days": 2,
    "daily_profit_cap": 1300,
    "consistency_enabled": true,
    "consistency_percent": 0.5
  },
  "funded": {
    "enabled": true,
    "max_drawdown": 2000,
    "max_daily_loss": null,
    "mll_freeze_profit": 2100,
    "minimum_withdrawable_profit": 2000,
    "payout_trigger_profit": 4100,
    "profit_split": 0.8,
    "reset_after_payout": false
  },
  "simulation": {
    "max_accounts": 100,
    "recycle_failed_accounts": true,
    "continue_after_pass": true
  }
}
```

The values above are illustrative. Real presets should only be marked verified
after the current rules have been checked.
