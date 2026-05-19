# US ETF Monthly Trend + Volatility Target v0.1

A research-grade, monthly multi-asset US-listed ETF framework for:

1. **Advisory mode**: generate reproducible backtests and monthly trade suggestions without broker API access.
2. **IBKR paper mode**: connect to Interactive Brokers TWS / IB Gateway paper environment and optionally submit paper orders, with a hard approval gate.

This project is designed for downstream AI coding agents: clear schemas, config-driven behavior, audit logs, reproducible run IDs, and explicit safety boundaries.

> Not investment advice. This framework is for research, education, and process automation. Always verify outputs manually before trading.

---

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]

# Run unit tests
pytest

# Run a synthetic-data smoke backtest without internet
python -m us_etf_trend_vol run-backtest \
  --config configs/strategy_advisory.yaml \
  --data-source synthetic \
  --start 2015-01-01 \
  --end 2024-12-31

# Generate monthly advisory orders from the latest available data
python -m us_etf_trend_vol suggest \
  --config configs/strategy_advisory.yaml \
  --data-source synthetic \
  --portfolio examples/current_portfolio.csv
```

To use live historical market data, choose a provider:

```bash
# Yahoo via yfinance, no API key, unofficial source
pip install yfinance
python -m us_etf_trend_vol run-backtest --config configs/strategy_advisory.yaml --data-source yahoo --start 2010-01-01

# Stooq CSV provider, no API key, basic US ETF daily bars
python -m us_etf_trend_vol run-backtest --config configs/strategy_advisory.yaml --data-source stooq --start 2010-01-01
```

---

## IBKR paper trading mode

IBKR mode is intentionally guarded. By default it only generates orders and prints them. It will not submit orders unless both flags are passed:

```bash
pip install -e .[ibkr]

python -m us_etf_trend_vol ibkr-paper \
  --config configs/strategy_ibkr_paper.yaml \
  --portfolio examples/current_portfolio.csv \
  --data-source yahoo \
  --dry-run
```

To submit to paper TWS / IB Gateway only after manual review:

```bash
python -m us_etf_trend_vol ibkr-paper \
  --config configs/strategy_ibkr_paper.yaml \
  --portfolio examples/current_portfolio.csv \
  --data-source yahoo \
  --submit \
  --i-understand-paper-trading
```

Expected defaults:

- Host: `127.0.0.1`
- Paper TWS port: `7497`
- Paper IB Gateway port often differs by setup. Check your own IBKR settings.
- Client ID: `77`

The tool requires TWS / IB Gateway to already be running and API connections to be enabled.

---

## Repository layout

```text
us_etf_trend_vol_v0_1/
  configs/
    universe_us_etf.yaml
    strategy_advisory.yaml
    strategy_ibkr_paper.yaml
    cost_model.yaml
    risk_limits.yaml
  examples/
    current_portfolio.csv
  src/us_etf_trend_vol/
    data/
    signals/
    portfolio/
    backtest/
    risk/
    execution/
    reporting/
    agents/
  tests/
  reports/
  logs/
  .github/workflows/ci.yml
```

---

## Core design

### Data layer

- Provider abstraction: `YahooFinanceProvider`, `StooqProvider`, `SyntheticProvider`, `LocalCsvProvider`.
- Daily schema: `date, symbol, open, high, low, close, adjusted_close, volume, dividend, split_factor, data_vendor, load_timestamp`.
- Return schema: `date, symbol, adjusted_return, log_return, valid_return`.
- Raw snapshots are never overwritten.

### Signal layer

- Monthly trend ensemble: 6 / 10 / 12-month moving average checks.
- Momentum: 6 and 12-month trailing return average.
- Realized volatility: 63 trading-day annualized volatility.
- All signals are timestamped at month-end.

### Portfolio layer

- Eligible assets must have positive trend and sufficient history.
- Inverse-volatility weighting.
- Single-asset and asset-class caps.
- Volatility targeting with `BIL` as cash proxy.
- Gross exposure cap defaults to 1.00.

### Backtest layer

- Signals generated at month-end.
- Trades execute on the next trading day.
- Cost model deducts spread + slippage + optional expense drag.
- Outputs daily NAV, trades, target weights, performance metrics, and Markdown reports.

### Reporting layer

- Reproducible run IDs and config hashes.
- Markdown report saved under `reports/backtests/`.
- Advisory order suggestions saved under `reports/advisory/`.

### Agent layer

- `agents/manifest.yaml` defines safe AI-agent responsibilities.
- Agents may propose configurations, run backtests, generate reports, and create order suggestions.
- Agents may not submit live orders, modify risk limits without review, overwrite raw data, or delete audit logs.

---

## Acceptance criteria coverage

- Project runs from command line.
- Config files are validated before execution.
- Every run produces a unique `run_id`.
- Logs are saved under `logs/`.
- No duplicated symbol-date rows allowed after validation.
- Missing adjusted closes and abnormal returns are reported.
- Assets with insufficient history are marked ineligible.
- Trades execute after signal date.
- Costs are deducted from NAV.
- Reports include required metrics and config hash.
- IBKR submission is disabled unless explicit approval flags are present.

---

## Common commands

```bash
python -m us_etf_trend_vol validate-config --config configs/strategy_advisory.yaml
python -m us_etf_trend_vol run-backtest --config configs/strategy_advisory.yaml --data-source synthetic
python -m us_etf_trend_vol suggest --config configs/strategy_advisory.yaml --data-source synthetic --portfolio examples/current_portfolio.csv
python -m us_etf_trend_vol ibkr-paper --config configs/strategy_ibkr_paper.yaml --portfolio examples/current_portfolio.csv --data-source synthetic --dry-run
```

---

## Next extension points

- Replace Yahoo/Stooq with a paid institutional feed.
- Add FRED risk-free series ingestion.
- Add benchmark baskets and factor ETFs.
- Add walk-forward testing.
- Add broker account read-only sync.
- Add portfolio-drift monitor.
- Add explicit tax-lot and wash-sale logic if needed.
