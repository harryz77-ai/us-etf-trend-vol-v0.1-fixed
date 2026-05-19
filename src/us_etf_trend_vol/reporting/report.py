from __future__ import annotations

from pathlib import Path

import pandas as pd

from us_etf_trend_vol.utils import ensure_dir


def write_backtest_report(
    run_id: str,
    config_hash: str,
    metrics: dict,
    nav: pd.DataFrame,
    trades: pd.DataFrame,
    out_dir: str | Path,
) -> Path:
    out = ensure_dir(out_dir)
    path = out / f"{run_id}.md"
    lines = [
        f"# Backtest Report: {run_id}",
        "",
        f"Config hash: `{config_hash}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for k, v in metrics.items():
        if isinstance(v, float):
            lines.append(f"| {k} | {v:.6f} |")
        else:
            lines.append(f"| {k} | {v} |")
    lines.extend(["", "## Trade Summary", ""])
    if trades.empty:
        lines.append("No trades generated.")
    else:
        summary = trades.groupby("symbol").agg(trade_count=("symbol", "count"), abs_notional=("notional", lambda x: x.abs().sum()), total_cost=("cost", "sum")).reset_index()
        lines.append(summary.to_markdown(index=False))
    lines.extend(["", "## Final NAV", "", nav.tail(5).to_markdown(index=False)])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_advisory_report(run_id: str, orders: pd.DataFrame, target_weights: pd.DataFrame, out_dir: str | Path) -> tuple[Path, Path]:
    out = ensure_dir(out_dir)
    orders_path = out / f"{run_id}_orders.csv"
    weights_path = out / f"{run_id}_target_weights.csv"
    orders.to_csv(orders_path, index=False)
    target_weights.to_csv(weights_path, index=False)
    md_path = out / f"{run_id}_advisory.md"
    lines = [f"# Advisory Suggestions: {run_id}", "", "## Proposed Orders", ""]
    lines.append(orders.to_markdown(index=False) if not orders.empty else "No proposed orders.")
    lines.extend(["", "## Target Weights", "", target_weights.to_markdown(index=False)])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return orders_path, md_path
