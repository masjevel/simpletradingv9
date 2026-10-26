# ============================================================
# reentry.py
# ------------------------------------------------------------
# Kombinerat återköp efter en KI-säljsignal.
#
# Den klassiska KI-modellen (ki_model.py) säljer och köper enbart
# på KI-månadsvärden. Här kan återköpet i stället ske i STEG, där
# varje valt villkor köper tillbaka en lika stor del:
#
#   ki     – KI:s egen återköpsregel (klassisk, vänder upp, E ...)
#   vix    – VIX-panik efter försäljningen (valfritt: först när paniken lagt sig)
#   credit – kreditspreaden (HYG/IEF) har visat stress och börjar vända
#   trend  – priset har varit under sin trend efter försäljningen och går över igen
#   rsi    – RSI < gräns medan priset ligger under SMA 200 ("Köp, negativ trend")
#   time   – tidsspärr: köp tillbaka resten efter X månader oavsett signaler
#
# Säljsidan är densamma som i ki_model: KI över säljgränsen i N månader.
# Efter ett fullständigt återköp kan en ny försäljning först ske när KI
# har varit nere på eller under säljgränsen igen (återaktivering), så att
# ett tidigt VIX-återköp inte direkt följs av en ny försäljning.
#
# Ingen look-ahead: dagliga villkor för handelsdag d använder bara data
# som fanns STRIKT FÖRE d (föregående handelsdags stängning). KI-månader
# används först handelsdagen efter antagen publicering.
# Motorn importerar inte Streamlit och kan testas fristående.
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from indicators import compute_rsi
from ki_model import KiParams, _turn_up_months

TRIGGER_ORDER = ["ki", "vix", "credit", "rsi", "trend"]
TRIGGER_LABELS = {
    "ki": "KI-vändning",
    "vix": "VIX-panik",
    "credit": "Kreditspread vänder",
    "rsi": "Köp (negativ trend)",
    "trend": "Trendvändning",
    "time": "Tidsspärr",
    "sell": "KI-sälj",
}
TREND_MODES = {
    "monthly_10m": "Månadsvis: pris över 10-månaders medelvärde",
    "daily_sma200": "Dagligen: pris över SMA 200",
}


@dataclass
class ReentryParams:
    use_ki: bool = True
    use_vix: bool = True
    vix_threshold: float = 34.0
    vix_calm_level: float = 25.0  # 0 = köp direkt vid paniken
    use_credit: bool = False
    credit_stress_pct: float = 5.0
    credit_sma: int = 50
    use_rsi: bool = False
    rsi_threshold: float = 28.0
    use_trend: bool = True
    trend_mode: str = "monthly_10m"
    time_stop_months: int = 18  # 0 = av
    staged: bool = True

    def triggers(self) -> list[str]:
        flags = {"ki": self.use_ki, "vix": self.use_vix, "credit": self.use_credit,
                 "rsi": self.use_rsi, "trend": self.use_trend}
        return [t for t in TRIGGER_ORDER if flags[t]]


def known_before(series: pd.Series | None, calendar: pd.DatetimeIndex) -> np.ndarray:
    """Värdet som var känt STRIKT FÖRE varje dag i kalendern (senaste observation < d).

    Fungerar även när serien har en annan handelskalender (t.ex. amerikansk VIX
    mot svenska handelsdagar). Saknas tidigare observation blir värdet NaN.
    """
    out = np.full(len(calendar), np.nan)
    if series is None:
        return out
    s = pd.Series(series).astype(float).dropna().sort_index()
    if s.empty:
        return out
    pos = s.index.searchsorted(pd.DatetimeIndex(calendar), side="left") - 1
    valid = pos >= 0
    out[valid] = s.to_numpy()[pos[valid]]
    return out


def _bool_known_before(mask: pd.Series | None, calendar) -> np.ndarray:
    vals = known_before(None if mask is None else mask.astype(float), calendar)
    return np.nan_to_num(vals, nan=0.0) > 0.5


def monthly_trend_ok(reference: pd.Series, months: int = 10) -> pd.Series:
    """Pris vid månadsslut över sitt N-månaders medelvärde. Index = månadens sista handelsdag."""
    ref = reference.dropna().sort_index()
    if ref.empty:
        return pd.Series(dtype=float)
    last_day = ref.groupby(ref.index.to_period("M")).apply(lambda x: x.index[-1])
    monthly = ref.groupby(ref.index.to_period("M")).last()
    sma = monthly.rolling(months, min_periods=months).mean()
    ok = (monthly > sma).where(sma.notna())
    # Värdet stämplas på månadens sista handelsdag och används därför först dagen efter.
    ok.index = pd.DatetimeIndex(last_day.to_numpy())
    return ok


def prepare_conditions(calendar, params: ReentryParams, reference: pd.Series | None = None,
                       vix: pd.Series | None = None, credit_ratio: pd.Series | None = None) -> pd.DataFrame:
    """Dagliga villkor, var och en baserad på data känd före respektive handelsdag."""
    calendar = pd.DatetimeIndex(calendar)
    out = pd.DataFrame(index=calendar)
    vix_prev = known_before(vix, calendar)
    out["vix_spike"] = np.nan_to_num(vix_prev, nan=-np.inf) > params.vix_threshold
    out["vix_calm"] = np.nan_to_num(vix_prev, nan=np.inf) < params.vix_calm_level

    if credit_ratio is not None and not credit_ratio.dropna().empty:
        ratio = credit_ratio.dropna().sort_index()
        high = ratio.rolling(252, min_periods=60).max()
        sma = ratio.rolling(params.credit_sma, min_periods=params.credit_sma).mean()
        stress = (ratio / high - 1.0) <= -params.credit_stress_pct / 100.0
        ok = (ratio > sma) & sma.notna()
        out["credit_stress"] = _bool_known_before(stress, calendar)
        out["credit_ok"] = _bool_known_before(ok, calendar)
    else:
        out["credit_stress"] = False
        out["credit_ok"] = False

    if reference is not None and not reference.dropna().empty:
        ref = reference.dropna().sort_index()
        sma200 = ref.rolling(200, min_periods=200).mean()
        rsi = compute_rsi(ref, 14)
        below = (ref < sma200) & sma200.notna()
        out["rsi_neg"] = _bool_known_before((rsi < params.rsi_threshold) & below, calendar)
        if params.trend_mode == "daily_sma200":
            ok = (ref > sma200).where(sma200.notna())
        else:
            ok = monthly_trend_ok(ref, 10)
        ok_prev = known_before(ok.astype(float), calendar)
        out["trend_known"] = ~np.isnan(ok_prev)
        out["trend_ok"] = np.nan_to_num(ok_prev, nan=0.0) > 0.5
    else:
        out["rsi_neg"] = False
        out["trend_known"] = False
        out["trend_ok"] = False
    return out


@dataclass
class _KiBuyTracker:
    """Speglar återköpsreglerna i ki_model.generate_ki_signals (DERISKED -> FLOOR_REACHED -> köp)."""
    params: KiParams
    state: str = "derisked"
    under_buy: int = 0
    rising: int = 0

    def update(self, val: float, prev_val, adjacent: bool) -> bool:
        p = self.params
        if self.state == "derisked":
            activation = p.buy_threshold if p.buyback_rule == "flat_or_up" else p.floor_threshold
            if val < activation:
                self.state = "floor"
                self.under_buy = 0
                self.rising = 0
        if self.state != "floor":
            return False
        if p.buyback_rule == "classic":
            self.under_buy = self.under_buy + 1 if val < p.buy_threshold else 0
            return self.under_buy >= p.duration_months
        if p.buyback_rule == "flat_or_up":
            return bool(adjacent and prev_val is not None and np.isfinite(prev_val) and val >= prev_val)
        need = _turn_up_months(p.buyback_rule)
        if prev_val is not None and not np.isnan(prev_val) and val > prev_val:
            self.rising += 1
        else:
            self.rising = 0
        return need > 0 and self.rising >= need


@dataclass
class _Cycle:
    sell_date: pd.Timestamp
    sell_ref_date: pd.Timestamp
    time_stop_date: pd.Timestamp | None
    steps: list = field(default_factory=list)
    complete_date: pd.Timestamp | None = None


def run_reentry_engine(ki_monthly: pd.Series, ki_params: KiParams, calendar,
                       conditions: pd.DataFrame, params: ReentryParams) -> dict:
    """Kör KI-sälj + kombinerat återköp på en daglig kalender.

    Returnerar dict med:
      orders  : DataFrame indexerad på Exec_Date med Signal, Exposure, Signal_Type, Trigger,
                Reason, Signal_Date, Available_Date, Barometer (samma format som KI-ordrar)
      cycles  : lista med säljcykler (säljdatum, steg, tidsspärrdatum, fullt återköp)
      state   : modellens läge efter sista handelsdagen
      exposure: daglig serie (0 = fullt avriskad, 1 = normalt investerad)
    """
    calendar = pd.DatetimeIndex(calendar).sort_values().unique()
    cond = conditions.reindex(calendar)
    for col in ["vix_spike", "vix_calm", "credit_stress", "credit_ok", "rsi_neg", "trend_known", "trend_ok"]:
        if col not in cond:
            cond[col] = False
        cond[col] = cond[col].fillna(False).astype(bool)
    c = {col: cond[col].to_numpy() for col in cond.columns}

    months = pd.Series(ki_monthly).astype(float).sort_index()
    m_dates = months.index
    m_vals = months.to_numpy()
    avail = m_dates + pd.Timedelta(days=int(ki_params.publication_lag_days))
    cal_norm = calendar.normalize()
    m_pos = cal_norm.searchsorted(avail.normalize(), side="right")
    by_day: dict[int, list[int]] = {}
    for j, pos in enumerate(m_pos):
        if pos < len(calendar):
            by_day.setdefault(int(pos), []).append(j)

    triggers = params.triggers()
    k = len(triggers)
    orders: list[dict] = []
    cycles: list[_Cycle] = []
    exposure_hist = np.ones(len(calendar))

    st = {
        "out": False, "armed": True, "consec": 0, "exposure": 1.0, "fired": set(),
        "vix_seen": False, "credit_seen": False, "trend_neg_seen": False,
        "tracker": None, "sell_date": None, "last_ki": np.nan, "last_ki_date": None,
        "prev_val": None, "prev_date": None,
    }

    def emit(d, signal, exposure, trigger, reason, signal_date, available_date):
        label = TRIGGER_LABELS[trigger]
        row = {"Exec_Date": d, "Signal": signal, "Exposure": exposure, "Trigger": trigger,
               "Signal_Type": "KI SÄLJ" if signal == -1 else f"Återköp: {label}",
               "Reason": reason, "Signal_Date": signal_date, "Available_Date": available_date,
               "Barometer": st["last_ki"]}
        if orders and orders[-1]["Exec_Date"] == d and orders[-1]["Signal"] == signal == 1:
            prev = orders[-1]
            prev.update(Exposure=exposure, Trigger=prev["Trigger"] + "+" + trigger,
                        Signal_Type=prev["Signal_Type"] + " + " + label,
                        Reason=prev["Reason"] + " · " + reason)
        else:
            orders.append(row)

    def finish_cycle(d):
        st["out"] = False
        st["consec"] = 0
        st["armed"] = bool(np.isfinite(st["last_ki"]) and st["last_ki"] <= ki_params.sell_threshold)
        st["tracker"] = None
        if cycles:
            cycles[-1].complete_date = d

    def fire(trigger, d, reason, signal_date=None, available_date=None):
        st["fired"].add(trigger)
        if trigger == "time" or not params.staged or k == 0:
            new_exp = 1.0
        else:
            new_exp = min(1.0, len(st["fired"] & set(triggers)) / k)
        step_txt = ""
        if params.staged and trigger != "time" and k > 1:
            step_txt = f" (steg {len(st['fired'] & set(triggers))}/{k})"
        st["exposure"] = new_exp
        emit(d, 1, new_exp, trigger, reason + step_txt,
             d if signal_date is None else signal_date, d if available_date is None else available_date)
        if cycles:
            cycles[-1].steps.append({"date": d, "trigger": trigger, "exposure": new_exp})
        if new_exp >= 1.0 - 1e-9:
            finish_cycle(d)

    def process_month(j, d, i):
        val = m_vals[j]
        mdate = m_dates[j]
        adjacent = st["prev_date"] is not None and mdate.to_period("M") == st["prev_date"].to_period("M") + 1
        prev_val = st["prev_val"]
        st["prev_date"] = mdate
        if np.isnan(val):
            st["prev_val"] = val
            return
        st["last_ki"] = val
        st["last_ki_date"] = mdate
        if not st["out"]:
            if st["armed"]:
                st["consec"] = st["consec"] + 1 if val > ki_params.sell_threshold else 0
                if st["consec"] >= ki_params.duration_months:
                    st.update(out=True, consec=0, exposure=0.0, fired=set(), vix_seen=False,
                              credit_seen=False, trend_neg_seen=False,
                              tracker=_KiBuyTracker(ki_params), sell_date=d)
                    sell_ref = d if avail[j] >= calendar[0] else pd.Timestamp(avail[j])
                    ts = sell_ref + pd.DateOffset(months=params.time_stop_months) if params.time_stop_months > 0 else None
                    cycles.append(_Cycle(sell_date=d, sell_ref_date=sell_ref, time_stop_date=ts))
                    emit(d, -1, 0.0, "sell",
                         f"KI > {ki_params.sell_threshold:g} i {ki_params.duration_months} månader",
                         mdate, avail[j])
            elif val <= ki_params.sell_threshold:
                st["armed"] = True
                st["consec"] = 0
        elif "ki" in triggers and "ki" not in st["fired"] and st["tracker"] is not None:
            if st["tracker"].update(val, prev_val, adjacent):
                rule = ki_params.buyback_rule
                if rule == "flat_or_up":
                    why = f"KI {prev_val:g} → {val:g} efter att ha varit under {ki_params.buy_threshold:g}"
                elif rule == "classic":
                    why = f"KI < {ki_params.buy_threshold:g} i {ki_params.duration_months} månader"
                else:
                    why = f"KI stigande {_turn_up_months(rule)} mån efter golv {ki_params.floor_threshold:g}"
                fire("ki", d, why, mdate, avail[j])
        st["prev_val"] = val

    for i, d in enumerate(calendar):
        for j in by_day.get(i, []):
            process_month(j, d, i)

        if st["out"] and st["sell_date"] is not None and d > st["sell_date"]:
            fired = st["fired"]
            if "vix" in triggers and "vix" not in fired:
                if params.vix_calm_level > 0:
                    if c["vix_spike"][i]:
                        st["vix_seen"] = True
                    elif st["vix_seen"] and c["vix_calm"][i]:
                        fire("vix", d, f"VIX var över {params.vix_threshold:g} och är nu under {params.vix_calm_level:g}")
                elif c["vix_spike"][i]:
                    fire("vix", d, f"VIX över {params.vix_threshold:g}")
            if st["out"] and "credit" in triggers and "credit" not in st["fired"]:
                if c["credit_stress"][i]:
                    st["credit_seen"] = True
                if st["credit_seen"] and c["credit_ok"][i]:
                    fire("credit", d, f"HYG/IEF har fallit ≥ {params.credit_stress_pct:g} % och är åter över SMA {params.credit_sma}")
            if st["out"] and "rsi" in triggers and "rsi" not in st["fired"] and c["rsi_neg"][i]:
                fire("rsi", d, f"RSI < {params.rsi_threshold:g} och pris under SMA 200")
            if st["out"] and "trend" in triggers and "trend" not in st["fired"] and c["trend_known"][i]:
                if not c["trend_ok"][i]:
                    st["trend_neg_seen"] = True
                elif st["trend_neg_seen"]:
                    fire("trend", d, "Priset har varit under trend efter sälj och är nu över ("
                         + TREND_MODES.get(params.trend_mode, params.trend_mode) + ")")
        # Tidsspärr. En försäljning från före kalenderns start vars spärr redan löpt ut
        # avslutas direkt första dagen, så startläget blir det som gällt vid den tidpunkten.
        if st["out"] and params.time_stop_months > 0 and cycles and cycles[-1].time_stop_date is not None:
            deadline = cycles[-1].time_stop_date
            if d >= deadline and (d > st["sell_date"] or deadline < calendar[0]):
                fire("time", d, f"Inget fullt återköp inom {params.time_stop_months} månader")
        exposure_hist[i] = st["exposure"] if st["out"] else 1.0

    cols = ["Signal", "Exposure", "Signal_Type", "Trigger", "Reason", "Signal_Date", "Available_Date", "Barometer"]
    if orders:
        out = pd.DataFrame(orders).set_index("Exec_Date")[cols]
        out = out[~out.index.duplicated(keep="last")]
    else:
        out = pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="Exec_Date"))
    pending = [t for t in triggers if t not in st["fired"]] if st["out"] else []
    return {
        "orders": out,
        "cycles": [vars(cy) for cy in cycles],
        "exposure": pd.Series(exposure_hist, index=calendar, name="Exposure"),
        "state": {"out": st["out"], "exposure": st["exposure"] if st["out"] else 1.0,
                  "armed": st["armed"], "months_over": st["consec"], "pending": pending,
                  "fired": sorted(st["fired"]), "last_ki": st["last_ki"],
                  "time_stop_date": cycles[-1].time_stop_date if st["out"] and cycles else None},
    }


def map_orders_to_calendar(orders: pd.DataFrame, calendar) -> pd.DataFrame:
    """Flytta ordrar till första handelsdag ≥ orderdagen i en annan kalender.

    Flera ordrar som hamnar samma dag slås ihop till den sista, eftersom 'Exposure'
    anger den absoluta nivån. Ordrar efter kalenderns slut utelämnas.
    """
    if orders.empty:
        return orders.copy()
    calendar = pd.DatetimeIndex(calendar).sort_values()
    pos = calendar.searchsorted(pd.DatetimeIndex(orders.index), side="left")
    keep = pos < len(calendar)
    out = orders.loc[keep].copy()
    out.index = pd.DatetimeIndex(calendar[pos[keep]], name="Exec_Date")
    return out[~out.index.duplicated(keep="last")]
