from us_etf_trend_vol.config import load_runtime_config


def test_load_config():
    cfg = load_runtime_config("configs/strategy_advisory.yaml")
    assert cfg.strategy["cash_asset"] == "BIL"
    assert len(cfg.config_hash) == 12
