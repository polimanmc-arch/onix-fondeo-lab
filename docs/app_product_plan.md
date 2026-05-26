# Onix Fondeo Lab App Product Plan

## App Vision

Onix Fondeo Lab should become a visual analyzer for futures funding accounts.
The user should be able to choose a funding preset, strategy, market data file,
and risk settings, then run a full analysis from one interface.

The app should help answer practical business questions:

- Can this strategy pass evaluations?
- Does it create funded payouts?
- How much bankroll is needed?
- What is the risk of ruin?
- Where are the weak spots: costs, streaks, consistency, payouts, or drawdown?

## Current Engine Capabilities

The current CLI engine already supports:

- Funding presets
- Lucid Trading presets
- Tradeify presets
- OHLC backtester
- Random Entry Strategy
- Stochastic Level Strategy
- Strategy metrics
- Funding simulation
- Bankroll engine
- Monte Carlo risk of ruin
- Streak analysis
- Strategy optimization
- Static HTML reports

## MVP Visual App Scope

The first visual app should focus on one clean workflow: run a single analysis.

MVP features:

- Select funding company / preset
- Select OHLC file
- Select strategy
- Configure basic risk settings
- Configure trade costs
- Configure bankroll
- Run single analysis
- Show summary metrics
- Show generated trades table
- Link to exported files

## Not Included In MVP

The MVP should stay small and useful. These features are intentionally out of
scope for the first version:

- Full optimization UI
- Advanced charts
- Multi-run comparison
- Authentication
- Cloud deployment
- Live trading
- NinjaTrader live integration

## Recommended App Stack

Use Streamlit for the MVP.

Why Streamlit:

- Fast to build
- Good for data apps and internal tools
- Simple widgets for presets, files, strategy parameters, and tables
- Easy to call the existing Python engine directly

Later, if the product needs more complex workflows, collaboration, accounts, or
a more polished UI, the app could migrate to:

- FastAPI backend
- React frontend

## Main Screen Layout

### Sidebar

The sidebar should contain all inputs needed to run an analysis:

- Data file
- Funding preset
- Strategy
- Risk settings
- Costs
- Bankroll
- Run button

### Main Area

The main area should display results after a run:

- Strategy Summary
- Funding Summary
- Bankroll Summary
- Risk of Ruin Summary
- Streak Analysis
- Generated trades table
- Links to exported files

## Design Principle

The app should not replace the engine.

It should call existing functions from the engine:

- market data loading
- strategy construction
- backtesting
- funding simulation
- metrics
- bankroll analysis
- risk of ruin
- streak analysis
- report exports

This keeps the business logic testable, reusable, and available from both CLI
and UI.

## Future Roadmap

Potential future app features:

- Optimization UI
- Preset comparison UI
- Strategy library
- Saved experiment runs
- Charts
- Trade explorer
- Monte Carlo dashboard
- Export PDF/HTML reports
