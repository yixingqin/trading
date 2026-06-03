import pandas as pd
import numpy as np
from config import STOCH_RSI_K, STOCH_RSI_D, STOCH_RSI_RSI_PERIOD, STOCH_RSI_STOCH_PERIOD, RSI_PERIOD


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stoch_rsi(
    close: pd.Series,
    rsi_period: int = STOCH_RSI_RSI_PERIOD,
    stoch_period: int = STOCH_RSI_STOCH_PERIOD,
    k_smooth: int = STOCH_RSI_K,
    d_smooth: int = STOCH_RSI_D,
) -> tuple[pd.Series, pd.Series]:
    """Returns (%K, %D) matching TradingView Stoch RSI (3,3,14,14)."""
    rsi_values = rsi(close, rsi_period)
    rsi_min = rsi_values.rolling(stoch_period).min()
    rsi_max = rsi_values.rolling(stoch_period).max()
    stoch = 100 * (rsi_values - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    k = stoch.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    return k, d


def current_signals(df: pd.DataFrame) -> dict:
    """
    Given a DataFrame with a 'close' column (4h OHLCV), return the latest
    indicator values and signal classification.
    """
    if len(df) < 50:
        return {"signal": "insufficient_data"}

    k, d = stoch_rsi(df["close"])
    rsi_vals = rsi(df["close"], RSI_PERIOD)

    latest_k = k.iloc[-1]
    latest_d = d.iloc[-1]
    latest_rsi = rsi_vals.iloc[-1]

    signal = "none"
    if latest_k < 10 and latest_rsi <= 50:
        signal = "best_buy"
    elif latest_k < 10 and latest_rsi <= 60:
        signal = "watch"

    return {
        "k": round(latest_k, 2),
        "d": round(latest_d, 2),
        "rsi": round(latest_rsi, 2),
        "signal": signal,
    }


def exit_tranches_hit(current_k: float, filled_tranches: list[int]) -> list[int]:
    """Return tranche k-levels that have been crossed but not yet sold."""
    from config import EXIT_TRANCHES
    hit = []
    for level, _ in EXIT_TRANCHES:
        if current_k >= level and level not in filled_tranches:
            hit.append(level)
    return hit
