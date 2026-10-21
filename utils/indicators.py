"""
utils/indicators.py
====================
Indicadores técnicos implementados en pandas puro: transparentes, sin
dependencias frágiles y fáciles de auditar. Si prefieres, puedes sustituirlos
por pandas-ta (ver requirements.txt).
"""

from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Media móvil exponencial (Exponential Moving Average)."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Relative Strength Index), método de Wilder.
    Devuelve valores 0-100: <30 sobreventa, >70 sobrecompra.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Promedio suavizado tipo Wilder (equivale a ewm con alpha = 1/period)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR (Average True Range), método de Wilder. Mide la volatilidad reciente
    en unidades de precio (no en %). Requiere columnas high/low/close.
    """
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def bollinger(series: pd.Series, period: int = 20, n_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bandas de Bollinger: media móvil simple +/- n_std desviaciones estándar.
    Devuelve (banda_inferior, media, banda_superior).
    """
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    return lower, mid, upper
