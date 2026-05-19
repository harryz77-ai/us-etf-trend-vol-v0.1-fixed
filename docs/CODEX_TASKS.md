# Codex / AI Coding Agent Task Plan

Use this file as the agent-entry prompt. The project is already runnable. Future agents should work by small PRs with tests.

## Hard constraints

- Do not overwrite `data/raw` or `data/snapshots`.
- Do not remove approval gates from IBKR paper mode.
- Do not add live trading submission in v0.x.
- Every experiment must have a `run_id` and config hash.
- Every code change must preserve tests.

## Next issues

### 1. Add FRED risk-free provider

Deliverables:
- Add `FredProvider` for daily/weekly risk-free series.
- Store `risk_free_daily` table.
- Compute excess-return Sharpe.
- Tests use mock CSV; no network dependency in CI.

### 2. Add walk-forward validation

Deliverables:
- Add train/validation/out-of-sample splits.
- Generate per-period metrics.
- Report parameter stability.

### 3. Add benchmark basket backtest

Deliverables:
- Static 60/40 SPY/IEF benchmark.
- Equal-weight universe benchmark.
- Cash-proxy benchmark.

### 4. Add account read-only sync for IBKR

Deliverables:
- Read positions from IBKR paper account.
- Convert positions to current weights.
- Keep order submission gated.

### 5. Add pre-trade risk report

Deliverables:
- Check max single asset, asset-class caps, turnover, and missing prices.
- Output pass/fail JSON and Markdown.
