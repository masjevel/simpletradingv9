# ============================================================
# signal_sources.py
# ------------------------------------------------------------
# Alternativa konjunktursignaler för KI-portföljbacktestet.
#
# OECD:s ledande indikator (CLI) för USA är normerad till 100 men
# svänger bara några enheter. För att samma state machine, gränser
# (t.ex. 113/90) och robusthetstest ska fungera räknas den om till
# KI-barometerns skala:
#
#     skalat = 100 + 10 × (CLI − 100) / std
#
# där std är standardavvikelsen för (CLI − 100) från seriens start
# fram till och med respektive månad (växande fönster). Ingen
# framtida data används; de första US_CLI_MIN_HISTORY_MONTHS
# månaderna saknar värde. Precis som KI:s egen serie kan den
# hämtade historiken vara reviderad.
# ============================================================

from __future__ import annotations

import numpy as np
import pandas as pd

from config import US_CLI_MIN_HISTORY_MONTHS


def rescale_to_barometer(cli: pd.Series, min_months: int = US_CLI_MIN_HISTORY_MONTHS) -> pd.Series:
    """CLI (normal 100) -> KI-skala (100 = normalt, 10 = en standardavvikelse), utan look-ahead."""
    s = pd.Series(cli, dtype=float).dropna().sort_index()
    if s.empty:
        return pd.Series(dtype=float, name="Barometer")
    dev = s - 100.0
    # Standardavvikelse kring normalnivån 100 (inte kring urvalets medel), med data t.o.m. varje månad.
    std = np.sqrt((dev ** 2).expanding(min_periods=min_months).mean())
    scaled = 100.0 + 10.0 * dev / std.replace(0.0, np.nan)
    return scaled.rename("Barometer")


def as_signal_frame(scaled: pd.Series) -> pd.DataFrame:
    """Samma format som KI-serien (kolumnen 'Barometer', månadsslut) så att all KI-logik kan återanvändas."""
    return pd.DataFrame({"Barometer": scaled.dropna()})
