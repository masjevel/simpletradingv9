# ============================================================
# indicators.py
# ------------------------------------------------------------
# Rena tekniska indikatorer i Pandas/NumPy. Inga sidoeffekter,
# inget Streamlit, ingen nätverksåtkomst - lätt att testa isolerat.
# ============================================================

from __future__ import annotations

import numpy as np
import pandas as pd

from config import MACD_FAST, MACD_SIGNAL, MACD_SLOW


def compute_sma(close: pd.Series, period: int) -> pd.Series:
    """Enkelt glidande medelvärde. Kolumnen heter medvetet inte 'SMA_200' -
    perioden är en parameter, inte en del av namnet."""
    return close.rolling(window=period, min_periods=period).mean().rename("SMA")


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilders RSI: SMA-seed över N prisförändringar, därefter Wilder-recursion.

    VIKTIGT: RSI är NaN tills tillräckligt många observationer finns
    (N+1 priser). Efter datagap börjar uppvärmningen om. Raderna får INTE sättas
    till 100 - det skulle kunna trigga falska köpsignaler under warm-up.
    """
    if not isinstance(period, (int, np.integer)) or period < 1:
        raise ValueError("period måste vara ett positivt heltal")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = pd.Series(np.nan, index=close.index)
    avg_loss = pd.Series(np.nan, index=close.index)
    count = 0
    g = l = 0.0
    for i, (up, down) in enumerate(zip(gain, loss)):
        if pd.isna(up) or pd.isna(down):
            count = 0
            g = l = 0.0
            continue
        if count < period:
            g += up
            l += down
            count += 1
            if count < period:
                continue
            g /= period
            l /= period
        else:
            g = (g * (period - 1) + up) / period
            l = (l * (period - 1) + down) / period
        avg_gain.iloc[i] = g
        avg_loss.iloc[i] = l

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Specialfall (bara där avg_gain/avg_loss faktiskt är beräknade, dvs. inte NaN):
    # avg_loss == 0 och avg_gain > 0  -> RSI = 100 (bara vinster)
    # avg_loss == 0 och avg_gain == 0 -> RSI = 50  (ingen rörelse alls)
    both_defined = avg_gain.notna() & avg_loss.notna()
    only_gains = both_defined & (avg_loss == 0.0) & (avg_gain > 0.0)
    no_movement = both_defined & (avg_loss == 0.0) & (avg_gain == 0.0)
    rsi = rsi.mask(only_gains, 100.0)
    rsi = rsi.mask(no_movement, 50.0)

    return rsi.rename("RSI")


def compute_macd(
    close: pd.Series,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> pd.DataFrame:
    """MACD-linje och signallinje. NaN förekommer inte här (EMA definierad från start),
    men de tidigaste värdena är statistiskt mindre pålitliga (ingen min_periods-spärr)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"MACD": macd, "MACD_Signal": macd_signal})


def compute_trend_streak(close: pd.Series, sma: pd.Series) -> pd.Series:
    """
    Vektoriserad "streak"-beräkning: hur många barer i följd som priset
    legat över (positivt) respektive under (negativt) sitt SMA.
    NaN i SMA (warm-up) ger streak = 0.
    """
    trend_now = np.where(close.to_numpy() > sma.to_numpy(), 1, -1)
    trend_now = np.where(sma.isna().to_numpy(), 0, trend_now)

    streak = np.zeros(len(close), dtype=int)
    current_streak = 0
    current_trend = 0
    for i, t in enumerate(trend_now):
        if t == 0:
            streak[i] = 0
            current_streak = 0
            current_trend = 0
            continue
        if t == current_trend:
            current_streak += 1
        else:
            current_trend = t
            current_streak = 1
        streak[i] = current_streak * current_trend

    return pd.Series(streak, index=close.index, name="Streak")


def calculate_technical_indicators(raw_df: pd.DataFrame, sma_period: int, rsi_period: int = 14) -> pd.DataFrame:
    """Bekvämlighetsfunktion som lägger till samtliga tekniska kolumner på en kopia av raw_df."""
    df = raw_df.copy()
    df["SMA"] = compute_sma(df["Close"], sma_period)
    df["RSI"] = compute_rsi(df["Close"], rsi_period)
    macd_df = compute_macd(df["Close"])
    df["MACD"] = macd_df["MACD"]
    df["MACD_Signal"] = macd_df["MACD_Signal"]
    df["Streak"] = compute_trend_streak(df["Close"], df["SMA"])
    return df
