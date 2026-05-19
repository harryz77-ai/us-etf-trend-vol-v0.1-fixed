from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from io import StringIO
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

from us_etf_trend_vol.utils import utc_now


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def get_daily_prices(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        """Return daily OHLCV rows matching the project's price schema."""


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"

    def get_daily_prices(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance or use --data-source synthetic/stooq") from exc

        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            df = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False)
            if df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            out = pd.DataFrame(
                {
                    "date": pd.to_datetime(df.index).date,
                    "symbol": symbol,
                    "open": df["Open"].astype(float).to_numpy(),
                    "high": df["High"].astype(float).to_numpy(),
                    "low": df["Low"].astype(float).to_numpy(),
                    "close": df["Close"].astype(float).to_numpy(),
                    "adjusted_close": df.get("Adj Close", df["Close"]).astype(float).to_numpy(),
                    "volume": df["Volume"].astype(float).to_numpy(),
                    "dividend": 0.0,
                    "split_factor": 1.0,
                    "data_vendor": self.name,
                    "load_timestamp": utc_now().isoformat(),
                }
            )
            frames.append(out)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class StooqProvider(MarketDataProvider):
    name = "stooq"

    def get_daily_prices(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end) if end else pd.Timestamp.utcnow().tz_localize(None)
        for symbol in symbols:
            # Stooq uses lower-case US tickers with .us suffix.
            url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
            try:
                text = urlopen(url, timeout=30).read().decode("utf-8")
            except Exception as exc:
                raise RuntimeError(f"Failed to fetch {symbol} from Stooq: {exc}") from exc
            df = pd.read_csv(StringIO(text))
            if df.empty or "Date" not in df.columns:
                continue
            df["Date"] = pd.to_datetime(df["Date"])
            df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]
            if df.empty:
                continue
            out = pd.DataFrame(
                {
                    "date": df["Date"].dt.date,
                    "symbol": symbol,
                    "open": df["Open"].astype(float),
                    "high": df["High"].astype(float),
                    "low": df["Low"].astype(float),
                    "close": df["Close"].astype(float),
                    "adjusted_close": df["Close"].astype(float),
                    "volume": df["Volume"].astype(float),
                    "dividend": 0.0,
                    "split_factor": 1.0,
                    "data_vendor": self.name,
                    "load_timestamp": utc_now().isoformat(),
                }
            )
            frames.append(out)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class LocalCsvProvider(MarketDataProvider):
    name = "local_csv"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get_daily_prices(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        out = df[df["symbol"].isin(symbols)].copy()
        start_dt = pd.to_datetime(start).date()
        out = out[out["date"] >= start_dt]
        if end:
            out = out[out["date"] <= pd.to_datetime(end).date()]
        return out


class SyntheticProvider(MarketDataProvider):
    name = "synthetic"

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def get_daily_prices(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed)
        dates = pd.bdate_range(start=start, end=end or pd.Timestamp.today().date())
        frames: list[pd.DataFrame] = []
        for i, symbol in enumerate(symbols):
            drift = 0.00015 + (i % 4) * 0.00002
            vol = 0.006 + (i % 5) * 0.0015
            shock = rng.normal(drift, vol, len(dates))
            # Add weak trend regimes to make signal pipeline non-trivial.
            regime = np.sin(np.linspace(0, 10, len(dates))) * 0.0005
            returns = shock + regime
            prices = 100 * np.exp(np.cumsum(returns))
            open_ = prices * (1 + rng.normal(0, 0.001, len(dates)))
            high = np.maximum(open_, prices) * (1 + np.abs(rng.normal(0, 0.002, len(dates))))
            low = np.minimum(open_, prices) * (1 - np.abs(rng.normal(0, 0.002, len(dates))))
            frames.append(
                pd.DataFrame(
                    {
                        "date": dates.date,
                        "symbol": symbol,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": prices,
                        "adjusted_close": prices,
                        "volume": rng.integers(100_000, 10_000_000, len(dates)),
                        "dividend": 0.0,
                        "split_factor": 1.0,
                        "data_vendor": self.name,
                        "load_timestamp": utc_now().isoformat(),
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)


def build_provider(name: str, local_csv: str | None = None) -> MarketDataProvider:
    if name == "synthetic":
        return SyntheticProvider()
    if name == "yahoo":
        return YahooFinanceProvider()
    if name == "stooq":
        return StooqProvider()
    if name == "local_csv":
        if not local_csv:
            raise ValueError("--local-csv is required for local_csv provider")
        return LocalCsvProvider(local_csv)
    raise ValueError(f"Unknown data source: {name}")
