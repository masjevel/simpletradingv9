# ============================================================
# ki_model.py
# ------------------------------------------------------------
# Konjunkturmodellen (KI Barometerindikator). Helt separat
# signallogik från den tekniska RSI/MACD/VIX-modellen - blandas
# aldrig ihop, och används av en egen backtestmotor (portfolio.py).
#
# State machine (krav 13-15):
#   NORMAL      -> KI stiger till/över säljgränsen i N månader     -> SÄLJ, gå till DERISKED
#   DERISKED    -> vänta tills KI passerat golvnivån (floor)        -> FLOOR_REACHED
#   FLOOR_REACHED -> köpregel uppfylld (klassisk eller vändning)    -> KÖP, gå till NORMAL
#
# Detta garanterar att en enda lång överhettningsperiod bara skapar
# EN säljsignal (inte en ny varje månad), och att en liten studs i
# botten (t.ex. 113->115->112->113) inte triggar återköp förrän KI
# faktiskt passerat golvnivån.
#
# Look-ahead: KI-värdet för månad M anses första gången tillgängligt
# KI_PUBLICATION_LAG_DAYS dagar efter månadsskiftet (se config.py),
# och en eventuell portföljåtgärd sker därefter tidigast nästa
# handelsdag. Se README för antagandet - exakt historiskt
# publiceringsdatum hämtas inte robust från öppna källor.
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
import pandas as pd

from config import KI_PUBLICATION_LAG_DAYS


class KiState(Enum):
    NORMAL = auto()
    DERISKED = auto()
    FLOOR_REACHED = auto()


@dataclass
class KiParams:
    sell_threshold: float = 110.0
    buy_threshold: float = 90.0
    duration_months: int = 3
    floor_threshold: float = 90.0
    buyback_rule: str = "classic"  # classic | turn_1m | turn_2m | turn_3m | flat_or_up
    # Antagen fördröjning (kalenderdagar efter månadsslut) innan KI-värdet får användas för handel.
    publication_lag_days: int = KI_PUBLICATION_LAG_DAYS


def _turn_up_months(rule: str) -> int:
    return {"turn_1m": 1, "turn_2m": 2, "turn_3m": 3}.get(rule, 0)


def generate_ki_signals(ki_monthly: pd.Series, params: KiParams) -> pd.DataFrame:
    """
    ki_monthly: pd.Series indexerad på månadsslutdatum (från data.fetch_ki_barometer).

    Returnerar en DataFrame (samma index) med kolumnerna:
      Signal      : 1 = köp/återköp, -1 = sälj/avriskning, 0 = inget
      Signal_Type : "KI SÄLJ" / "KI KÖP" / None
      State       : strängrepresentation av state machine-läget EFTER dagens signal
      Available_Date : datum då informationen anses tillgänglig för handel (publiceringsfördröjning)
    """
    values = ki_monthly.to_numpy(dtype=float)
    dates = ki_monthly.index
    n = len(values)

    signal = np.zeros(n, dtype=int)
    signal_type: list[str | None] = [None] * n
    state_out: list[str] = [""] * n

    state = KiState.NORMAL
    consecutive_over = 0
    consecutive_under_buy = 0  # för "classic"-regeln, räknas bara när FLOOR_REACHED (dvs. har varit under floor)
    rising_streak = 0
    prev_value = None

    for i in range(n):
        val = values[i]
        if np.isnan(val):
            state_out[i] = state.name
            prev_value = val
            continue

        if state == KiState.NORMAL:
            consecutive_over = consecutive_over + 1 if val > params.sell_threshold else 0
            if consecutive_over >= params.duration_months:
                signal[i] = -1
                signal_type[i] = "KI SÄLJ"
                state = KiState.DERISKED
                consecutive_over = 0
                consecutive_under_buy = 0
                rising_streak = 0

        elif state == KiState.DERISKED:
            # Väntar på att KI passerat golvnivån innan någon återköpslogik alls aktiveras.
            activation_threshold = params.buy_threshold if params.buyback_rule == "flat_or_up" else params.floor_threshold
            if val < activation_threshold:
                state = KiState.FLOOR_REACHED
                # Räknarna nollställs här; själva räkningen för DENNA månad sker i
                # FLOOR_REACHED-blocket nedan (samma iteration) så att ingen månad räknas dubbelt.
                consecutive_under_buy = 0
                rising_streak = 0

        if state == KiState.FLOOR_REACHED:
            # OBS: körs även samma iteration som man precis gått in i FLOOR_REACHED (inte elif).
            if params.buyback_rule == "classic":
                consecutive_under_buy = consecutive_under_buy + 1 if val < params.buy_threshold else 0
                if consecutive_under_buy >= params.duration_months:
                    signal[i] = 1
                    signal_type[i] = "KI KÖP"
                    state = KiState.NORMAL
                    consecutive_under_buy = 0
                    rising_streak = 0
            elif params.buyback_rule == "flat_or_up":
                # Köpgränsen aktiverar regeln. Återköpet får ske ovanför gränsen,
                # men jämförelsen måste avse två intilliggande kalendermånader.
                adjacent_month = i > 0 and dates[i].to_period("M") == dates[i - 1].to_period("M") + 1
                if adjacent_month and prev_value is not None and np.isfinite(prev_value) and val >= prev_value:
                    signal[i] = 1
                    signal_type[i] = "KI KÖP"
                    state = KiState.NORMAL
                    rising_streak = 0
                    consecutive_under_buy = 0
            else:
                need = _turn_up_months(params.buyback_rule)
                if prev_value is not None and not np.isnan(prev_value) and val > prev_value:
                    rising_streak += 1
                else:
                    rising_streak = 0
                if rising_streak >= need and need > 0:
                    signal[i] = 1
                    signal_type[i] = "KI KÖP"
                    state = KiState.NORMAL
                    rising_streak = 0
                    consecutive_under_buy = 0

        state_out[i] = state.name
        prev_value = val

    reasons = []
    for i, sig in enumerate(signal):
        if sig == -1:
            reason = f"KI > {params.sell_threshold:g} i {params.duration_months} månader"
        elif sig == 1 and params.buyback_rule == 'flat_or_up':
            reason = f"KI har varit under {params.buy_threshold:g}; {values[i-1]:g} → {values[i]:g}, oförändrat eller stigande"
        elif sig == 1 and params.buyback_rule == 'classic':
            reason = f"KI < {params.buy_threshold:g} i {params.duration_months} månader efter passerat golv"
        elif sig == 1:
            reason = f"KI stigande i {_turn_up_months(params.buyback_rule)} månader efter passerat golv {params.floor_threshold:g}"
        else:
            reason = ""
        reasons.append(reason)
    available_dates = dates + pd.Timedelta(days=int(params.publication_lag_days))

    return pd.DataFrame(
        {
            "Barometer": values,
            "Reason": reasons,
            "Signal": signal,
            "Signal_Type": signal_type,
            "State": state_out,
            "Available_Date": available_dates,
        },
        index=dates,
    )


def map_signals_to_trading_days(ki_signals: pd.DataFrame, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Översätter månadssignaler till konkreta exekveringsdatum: tidigast nästa
    handelsdag efter att informationen (Available_Date) blivit tillgänglig.
    Detta är den enda platsen där KI-signaler kopplas till en handelskalender,
    så order inte föregår antagen tillgänglighet. Reviderade historiska
    KI-värden kan fortfarande påverka resultatet.

    Returnerar DataFrame med kolumnerna: Exec_Date, Signal, Signal_Type.
    """
    rows = []
    trading_days = pd.DatetimeIndex(trading_days).sort_values()
    trading_dates = trading_days.normalize()
    for date, row in ki_signals.iterrows():
        if row["Signal"] == 0:
            continue
        avail = row["Available_Date"]
        pos = trading_dates.searchsorted(pd.Timestamp(avail).normalize(), side="right")
        if pos >= len(trading_days):
            continue  # signalen skulle exekveras efter datasetets slut
        exec_date = trading_days[pos]
        rows.append({"Signal_Date": date, "Available_Date": avail, "Reason": row.get("Reason", ""), "Barometer": row.get("Barometer", np.nan), "Exec_Date": exec_date, "Signal": int(row["Signal"]), "Signal_Type": row["Signal_Type"]})

    if not rows:
        return pd.DataFrame(columns=["Exec_Date", "Signal", "Signal_Type"]).set_index("Exec_Date")

    out = pd.DataFrame(rows).set_index("Exec_Date")
    # Before the price history begins, only the latest known decision sets the
    # starting position. Multiple historical orders must not execute on day one.
    out = out[~out.index.duplicated(keep="last")]
    return out
