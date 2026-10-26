# ============================================================
# signals.py
# ------------------------------------------------------------
# EN central funktion avgör den slutliga signalen för varje dag.
# Grafen (charts.py), signalserien (df["Signal"]) och backtesten
# (backtest.py) läser alla från exakt samma output härifrån -
# det finns ingen separat signallogik någon annanstans i koden.
#
# Signalprioritering vid ev. konflikt samma dag:
#   1. SÄLJ (MACD-baserad) prioriteras framför KÖP om båda skulle
#      trigga samma dag, eftersom säljsignalen är riskreducerande
#      och vi hellre reagerar defensivt vid osäkerhet.
#   2. Bland köpkandidater prioriteras VIX-panik framför RSI-köp,
#      eftersom VIX-panik historiskt representerar mer extrema/
#      sällsynta lägen.
#   3. Köp och sälj har separata cooldown-räknare (i handelsdagar).
# ============================================================

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SignalParams:
    buy_rsi_threshold: float = 28.0
    sell_rsi_filter: float = 65.0
    vix_panic_threshold: float = 34.0
    cooldown_bars: int = 15  # handelsdagar
    use_rsi_buy: bool = True
    use_vix_buy: bool = True
    use_macd_sell: bool = True
    use_rsi_sell_filter: bool = True
    use_trend_filter: bool = False


def generate_signals(df: pd.DataFrame, params: SignalParams) -> pd.DataFrame:
    """
    Beräknar den slutgiltiga, entydiga signalserien.

    Kräver kolumnerna: Close, RSI, MACD, MACD_Signal, VIX, SMA.
    Returnerar df med tillagda kolumner:
      Signal      : 1 = köp, -1 = sälj, 0 = neutral
      Signal_Type : sträng eller None
    Aktiva RSI/MACD-villkor kräver beräknade indikatorer (inte NaN).
    Avstängda villkor blockerar inte signaler under uppvärmning.
    """
    out = df.copy()
    n = len(out)

    rsis = out["RSI"].to_numpy()
    macds = out["MACD"].to_numpy()
    macd_sig = out["MACD_Signal"].to_numpy()
    vixes = out["VIX"].to_numpy() if "VIX" in out.columns else np.full(n, np.nan)

    signal = np.zeros(n, dtype=int)
    signal_type: list[str | None] = [None] * n

    last_buy_idx = -10**9
    last_sell_idx = -10**9

    for i in range(n):
        # RSI/MACD warm-up: ingen signal kan genereras innan indikatorerna är riktiga tal.
        # Only enabled indicators participate in warm-up.
        if (params.use_rsi_buy or (params.use_macd_sell and params.use_rsi_sell_filter)) and np.isnan(rsis[i]):
            continue
        if params.use_macd_sell and (np.isnan(macds[i]) or np.isnan(macd_sig[i])):
            continue

        vix_ok = not np.isnan(vixes[i])
        vix_panic = params.use_vix_buy and vix_ok and vixes[i] > params.vix_panic_threshold
        rsi_buy = params.use_rsi_buy and rsis[i] < params.buy_rsi_threshold

        prev_macd = macds[i - 1] if i > 0 and not np.isnan(macds[i - 1]) else macds[i]
        prev_sig = macd_sig[i - 1] if i > 0 and not np.isnan(macd_sig[i - 1]) else macd_sig[i]
        macd_cross_down = (prev_macd > prev_sig) and (macds[i] < macd_sig[i])
        sell_candidate = params.use_macd_sell and macd_cross_down and (not params.use_rsi_sell_filter or rsis[i] > params.sell_rsi_filter)

        buy_candidate = vix_panic or rsi_buy
        if params.use_trend_filter:
            buy_candidate = buy_candidate and pd.notna(out['SMA'].iloc[i]) and out['Close'].iloc[i] > out['SMA'].iloc[i]

        buy_ready = buy_candidate and (i - last_buy_idx) > params.cooldown_bars
        sell_ready = sell_candidate and (i - last_sell_idx) > params.cooldown_bars

        # --- Central prioritering: sälj slår köp vid krock samma dag ---
        if sell_ready:
            signal[i] = -1
            signal_type[i] = "MACD SÄLJ"
            last_sell_idx = i
        elif buy_ready:
            signal[i] = 1
            if vix_panic:
                signal_type[i] = "VIX Panik KÖP"
            else:
                signal_type[i] = "RSI KÖP"
            last_buy_idx = i

    out["Signal_Reason"] = [
        (f"MACD korsade ned" + (f" och RSI > {params.sell_rsi_filter:g}" if params.use_rsi_sell_filter else "")) if sig == -1 else
        ((f"VIX > {params.vix_panic_threshold:g}" if typ == "VIX Panik KÖP" else f"RSI < {params.buy_rsi_threshold:g}") +
         ("; pris över SMA" if params.use_trend_filter else "")) if sig == 1 else ""
        for sig, typ in zip(signal, signal_type)]
    out["Signal"] = signal
    out["Signal_Type"] = signal_type
    return out
