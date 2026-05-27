# Development Workflow

This document defines the working process for Onix Fondeo Lab.
The goal is to keep the project reliable, reproducible, and easy to evolve.

## Branching

- Main development happens on `dev`.
- For large or risky features, use a short-lived feature branch.
- Keep `dev` runnable at all times.

## Feature Workflow

Each feature should follow this sequence:

1. Identify the roadmap number and feature name.
2. State the goal and acceptance criteria.
3. Inspect the existing code before editing.
4. Implement the smallest useful version.
5. Add or update tests.
6. Run the local check script.
7. Smoke test Streamlit if app behavior changed.
8. Update documentation or roadmap status if needed.
9. Commit with a clear message.
10. Push to `dev`.

## Required Checks Before Commit

Run:

```powershell
.\scripts\check.ps1
```

The check script should:

- Compile `app.py`.
- Run the full pytest suite with `PYTHONPATH=src`.
- Warn if real market data files are staged.

## Streamlit Smoke Test

When a feature changes the app UI or app state:

1. Start the app:

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

2. Verify:

- The app loads.
- The sidebar is usable.
- `Run Analysis` works with default sample data.
- The four main tabs appear:
  - Dashboard
  - Backtest
  - Funding & Risk
  - Data
- No `Analysis failed` error appears.

## Commit Guidelines

Use clear, meaningful commit messages:

- `Add Streamlit account summary table`
- `Fix trade explorer state reset`
- `Document app improvement roadmap`

Prefer one feature or fix per commit.

## Data Safety

Do not commit real market data.

Never commit:

- `data/market_data/*.csv`
- `data/market_data/*.txt`

Allowed sample files:

- `data/market_data/sample_NQ_1m.csv`
- `data/market_data/.gitkeep`

Local app setup JSON files are also ignored:

- `data/app_setups/*.json`

## Done Criteria

A task is done when:

- Code is implemented.
- Tests pass.
- Streamlit smoke test passes if relevant.
- Documentation is updated when needed.
- Commit is pushed.
- The final summary includes:
  - completed roadmap number
  - files changed
  - tests run
  - known limitations
  - next roadmap number
