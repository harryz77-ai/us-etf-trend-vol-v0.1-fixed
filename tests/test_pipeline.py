from us_etf_trend_vol.config import load_runtime_config
from us_etf_trend_vol.data.pipeline import compute_daily_returns, universe_to_asset_master, validate_prices
from us_etf_trend_vol.data.providers import SyntheticProvider
from us_etf_trend_vol.signals.engine import generate_monthly_signals
from us_etf_trend_vol.portfolio.construction import construct_target_weights


def test_end_to_end_components():
    cfg = load_runtime_config("configs/strategy_advisory.yaml")
    asset_master = universe_to_asset_master(cfg.strategy["universe"])
    symbols = asset_master["symbol"].tolist()
    prices = SyntheticProvider().get_daily_prices(symbols, start="2018-01-01", end="2021-12-31")
    prices, issues = validate_prices(prices)
    assert issues.empty
    returns = compute_daily_returns(prices)
    signals = generate_monthly_signals(prices, returns, cfg.strategy)
    assert not signals.empty
    signal_date = signals["signal_date"].max()
    tw = construct_target_weights(signal_date, signals, returns, asset_master, cfg.strategy)
    assert abs(tw["target_weight"].sum() - 1.0) < 1e-8
    assert tw["target_weight"].max() <= 1.0
