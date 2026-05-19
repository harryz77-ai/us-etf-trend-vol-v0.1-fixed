from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RuntimeConfig:
    path: Path
    raw: dict[str, Any]
    strategy: dict[str, Any]
    config_hash: str


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {p}")
    return data


def deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    out = dict(left)
    for k, v in right.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_runtime_config(path: str | Path) -> RuntimeConfig:
    p = Path(path)
    raw = load_yaml(p)
    if "strategy" not in raw:
        raise ValueError("Config requires top-level 'strategy' key")

    strategy = dict(raw["strategy"])
    base_dir = p.parent.parent if p.parent.name == "configs" else Path.cwd()

    # Merge external config files into strategy for deterministic downstream use.
    for external_key, target_key in [
        ("cost_model_file", "cost_model"),
        ("risk_limits_file", "risk_limits"),
    ]:
        external_file = strategy.get(external_key)
        if external_file:
            external = load_yaml(base_dir / external_file if not Path(external_file).is_absolute() else external_file)
            strategy[target_key] = external.get(target_key, external)

    universe_file = strategy.get("universe_file")
    if universe_file:
        universe = load_yaml(base_dir / universe_file if not Path(universe_file).is_absolute() else universe_file)
        strategy["universe"] = universe.get("universe", universe)

    validate_strategy_config(strategy)
    stable = json.dumps(strategy, sort_keys=True, default=str).encode("utf-8")
    config_hash = hashlib.sha256(stable).hexdigest()[:12]
    return RuntimeConfig(path=p, raw=raw, strategy=strategy, config_hash=config_hash)


def validate_strategy_config(strategy: dict[str, Any]) -> None:
    required = ["name", "version", "cash_asset", "signals", "portfolio_construction", "risk_limits", "universe"]
    missing = [k for k in required if k not in strategy]
    if missing:
        raise ValueError(f"Missing required strategy config keys: {missing}")
    if not isinstance(strategy["universe"], list) or not strategy["universe"]:
        raise ValueError("Universe must be a non-empty list")
    tickers = [row.get("symbol") for row in strategy["universe"]]
    if strategy["cash_asset"] not in tickers:
        raise ValueError("cash_asset must exist in universe")
    limits = strategy["risk_limits"]
    if limits.get("max_gross_exposure", 0) > 1.5:
        raise ValueError("max_gross_exposure above 1.5 is blocked in v0.1")
    if limits.get("target_annual_volatility", 0) <= 0:
        raise ValueError("target_annual_volatility must be positive")
