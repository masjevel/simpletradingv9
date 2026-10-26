# ============================================================
# savings.py
# ------------------------------------------------------------
# Månadssparande och engångsinsättningar ovanpå KI-portföljmotorn.
#
#   - build_contributions : sparplan (startbelopp, månadsbelopp med
#                           årlig ökning, extra insättningar) som
#                           belopp per kalenderdatum
#   - map_to_trading_days : flyttar varje insättning till första
#                           handelsdag på eller efter datumet
#   - xirr                : pengaviktad årsavkastning (din faktiska
#                           avkastning givet när pengarna sattes in)
#   - twr_series / twr_cagr : tidsviktad avkastning (strategins
#                           avkastning oberoende av insättningarna)
#   - run_plan            : kör KI-strategi och köp och behåll med
#                           samma sparplan
#
# Ingen Streamlit här - modulen testas fristående.
# ============================================================

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import portfolio


@dataclass
class SavingsPlan:
    start: pd.Timestamp
    end: pd.Timestamp
    initial_amount: float = 0.0
    monthly_amount: float = 2_000.0
    deposit_day: int = 25
    annual_increase_pct: float = 0.0
    extra: list = field(default_factory=list)  # [(datum, belopp), ...]


EXTRA_COLUMNS = ["Datum", "Belopp (kr)", "Beskrivning"]


def empty_extra_table() -> pd.DataFrame:
    """Tom tabell för extra insättningar (startläge i appen)."""
    return pd.DataFrame({"Datum": pd.Series(dtype="datetime64[ns]"),
                         "Belopp (kr)": pd.Series(dtype=float),
                         "Beskrivning": pd.Series(dtype=object)})


def parse_extra_deposits(table: pd.DataFrame | None) -> tuple[list, int]:
    """Läser tabellen med extra insättningar (valfritt antal rader).

    Returnerar ([(radnummer, datum, belopp, beskrivning), ...] sorterat på datum, antal ofullständiga rader).
    Rader utan datum eller med belopp <= 0 hoppas över och räknas som ofullständiga; helt tomma rader ignoreras.
    """
    if table is None or len(table) == 0:
        return [], 0
    t = table.reset_index(drop=True)
    n_rows = len(t)
    # Kolumnvis läsning: iterrows skulle göra om tomma celler till NaT i alla kolumner.
    dates = pd.to_datetime(t["Datum"], errors="coerce") if "Datum" in t else pd.Series([pd.NaT] * n_rows)
    amounts = pd.to_numeric(t["Belopp (kr)"], errors="coerce") if "Belopp (kr)" in t else pd.Series([np.nan] * n_rows)
    labels = t["Beskrivning"] if "Beskrivning" in t else pd.Series([None] * n_rows)
    out, incomplete = [], 0
    for i in range(n_rows):
        d, amount, raw_label = dates.iloc[i], amounts.iloc[i], labels.iloc[i]
        label = "" if raw_label is None or pd.isna(raw_label) else str(raw_label).strip()
        if pd.isna(d) and pd.isna(amount) and not label:
            continue  # helt tom rad
        if pd.isna(d) or pd.isna(amount) or float(amount) <= 0:
            incomplete += 1
            continue
        out.append((i + 1, pd.Timestamp(d).normalize(), float(amount), label))
    out.sort(key=lambda r: (r[1], r[0]))
    return out, incomplete


def build_contributions(plan: SavingsPlan) -> pd.Series:
    """Insättningar per kalenderdatum (före mappning till handelsdagar).

    Månadsbeloppet sätts in på vald dag varje månad från startmånaden (första gången på
    eller efter startdatum) och höjs med annual_increase_pct var tolfte månad.
    """
    start = pd.Timestamp(plan.start).normalize()
    end = pd.Timestamp(plan.end).normalize()
    if end < start:
        raise ValueError("Slutdatum måste vara efter startdatum.")
    day = int(min(max(plan.deposit_day, 1), 28))
    flows: dict[pd.Timestamp, float] = {}

    def add(d, amount):
        if amount > 0 and start <= d <= end:
            flows[d] = flows.get(d, 0.0) + float(amount)

    add(start, plan.initial_amount)
    if plan.monthly_amount > 0:
        first = pd.Timestamp(start.year, start.month, day)
        if first < start:
            first = first + pd.DateOffset(months=1)
        n = 0
        d = first
        growth = 1.0 + plan.annual_increase_pct / 100.0
        while d <= end:
            add(d, plan.monthly_amount * growth ** (n // 12))
            n += 1
            d = first + pd.DateOffset(months=n)
    for d, amount in plan.extra:
        add(pd.Timestamp(d).normalize(), amount)
    if not flows:
        return pd.Series(dtype=float, name="Deposit")
    return pd.Series(flows, name="Deposit").sort_index()


def map_to_trading_days(flows: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Varje insättning görs första handelsdag på eller efter datumet. Insättningar efter
    kalenderns sista dag utelämnas."""
    if flows.empty:
        return flows.copy()
    calendar = pd.DatetimeIndex(calendar).sort_values()
    pos = calendar.searchsorted(pd.DatetimeIndex(flows.index), side="left")
    keep = pos < len(calendar)
    out = pd.Series(flows.to_numpy()[keep], index=calendar[pos[keep]], name="Deposit")
    return out.groupby(level=0).sum()


def xirr(flow_dates, amounts, final_date, final_value) -> float:
    """Pengaviktad årsavkastning (decimal). Insättningar är positiva belopp in i portföljen.

    Löser  sum(F_i * (1+r)^((T - t_i)/365)) = slutvärde  med bisektion. NaN om det saknas lösning.
    """
    amounts = np.asarray(amounts, dtype=float)
    if len(amounts) == 0 or amounts.sum() <= 0 or not np.isfinite(final_value):
        return float("nan")
    years = np.array([(pd.Timestamp(final_date) - pd.Timestamp(d)).days / 365.0 for d in flow_dates])
    if years.max() <= 0:
        return float("nan")

    def fv(r):
        return float(np.sum(amounts * (1.0 + r) ** years)) - final_value

    lo, hi = -0.99, 1.0
    while fv(hi) < 0 and hi < 1e3:
        hi *= 2
    if fv(lo) > 0 or fv(hi) < 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if fv(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def twr_series(equity: pd.Series, flows: pd.Series) -> pd.Series:
    """Tidsviktat index (start 1): dagens avkastning räknas före dagens insättning."""
    flows = flows.reindex(equity.index).fillna(0.0)
    v = equity.to_numpy(dtype=float)
    f = flows.to_numpy(dtype=float)
    out = np.ones(len(v))
    started = False
    for i in range(len(v)):
        if not started:
            started = v[i] > 0
            continue
        prev = v[i - 1]
        r = (v[i] - f[i]) / prev - 1.0 if prev > 0 else 0.0
        out[i] = out[i - 1] * (1.0 + r)
    return pd.Series(out, index=equity.index, name="TWR")


def twr_cagr(index: pd.Series, start=None) -> float:
    """Årlig tidsviktad avkastning i procent, från första dagen med pengar i portföljen."""
    s = index if start is None else index.loc[start:]
    if len(s) < 2:
        return float("nan")
    years = (s.index[-1] - s.index[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return float(((s.iloc[-1] / s.iloc[0]) ** (1.0 / years) - 1.0) * 100.0)


def max_drawdown_pct(index: pd.Series) -> float:
    """Största fall (procent, negativt tal) i det tidsviktade indexet."""
    if index.empty:
        return float("nan")
    peak = index.cummax()
    return float(((index / peak) - 1.0).min() * 100.0)


def summarize(result: dict, flows: pd.Series) -> dict:
    equity = result["equity"]
    flows = flows.reindex(equity.index).fillna(0.0)
    invested = float(flows.sum())
    final = float(equity.iloc[-1])
    paid = flows[flows > 0]
    first_day = paid.index[0] if len(paid) else equity.index[0]
    twr = twr_series(equity, flows)
    return {
        "final_value": final,
        "invested": invested,
        "profit": final - invested,
        "xirr_pct": xirr(paid.index, paid.to_numpy(), equity.index[-1], final) * 100.0,
        "twr_cagr_pct": twr_cagr(twr, first_day),
        "max_dd_pct": max_drawdown_pct(twr.loc[first_day:]),
        "twr": twr,
    }


def run_plan(prices: pd.DataFrame, orders: pd.DataFrame | None, params: portfolio.PortfolioParams,
             flows: pd.Series) -> dict:
    """KI-strategi och köp och behåll med samma insättningar. Startkapitalet är 0; allt
    kapital kommer från sparplanen."""
    base = dataclasses.replace(params, initial_capital=0.0)
    ki = portfolio.simulate_portfolio(prices, orders, base, cash_flows=flows)
    bnh = portfolio.simulate_portfolio(prices, None, dataclasses.replace(base, apply_ki=False), cash_flows=flows)
    return {"ki": ki, "bnh": bnh, "ki_summary": summarize(ki, flows), "bnh_summary": summarize(bnh, flows)}
