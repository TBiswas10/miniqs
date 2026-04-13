"""Stateless technical indicators for quant trading."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(prices: pd.Series, window: int = 14) -> float:
    """Relative Strength Index."""
    if len(prices) < window + 1:
        return 50.0
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, 1e-9)
    res = 100.0 - (100.0 / (1.0 + rs.iloc[-1]))
    return float(res) if not pd.isna(res) else 50.0


def macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float]:
    """Moving Average Convergence Divergence."""
    if len(prices) < slow:
        return 0.0, 0.0
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return float(macd_line.iloc[-1]), float(macd_signal_line.iloc[-1])


def atr(prices: pd.Series, window: int = 14) -> float:
    """Average True Range (Simplified for tick data)."""
    if len(prices) < window:
        return 0.0
    highs = prices.rolling(window=window).max()
    lows = prices.rolling(window=window).min()
    tr = highs - lows
    res = tr.rolling(window=window).mean().iloc[-1]
    return float(res) if not pd.isna(res) else 0.0


def ema(prices: pd.Series, span: int) -> float:
    """Exponential Moving Average."""
    if len(prices) < 1:
        return 0.0
    return float(prices.ewm(span=span, adjust=False).mean().iloc[-1])


def slope(values: pd.Series) -> float:
    """Linear regression slope."""
    if len(values) < 2:
        return 0.0
    y = values.to_numpy(dtype="float64")
    x = np.arange(len(y), dtype="float64")
    return float(np.polyfit(x, y, 1)[0])
