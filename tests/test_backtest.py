from us_etf_trend_vol.backtest.engine import run_backtest
from us_etf_trend_vol.config import load_runtime_config
from us_etf_trend_vol.data.pipeline import compute_daily_returns, universe_to_asset_master, validate_prices
from us_etf_trend_vol.data.providers import SyntheticProvider
from us_etf_trend_vol.signals.engine import generate_monthly_signals


def test_backtest_runs():
    cfg = load_runtime_config("configs/strategy_advisory.yaml")
    asset_master = universe_to_asset_master(cfg.strategy["universe"])
    prices = SyntheticProvider().get_daily_prices(asset_master["symbol"].tolist(), "2018-01-01", "2022-12-31")
    prices, _ = validate_prices(prices)
    returns = compute_daily_returns(prices)
    signals = generate_monthly_signals(prices, returns, cfg.strategy)
    result = run_backtest(prices, returns, signals, asset_master, cfg.strategy, "test_run")
    assert not result.nav.empty
    assert result.metrics["ending_nav"] > 0
