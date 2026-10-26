# ============================================================
# portfolio.py
# ------------------------------------------------------------
# HELT SEPARAT backtestmotor för KI-portföljbacktesten (skiljs
# strikt från den tekniska RSI/MACD/VIX-backtesten i backtest.py).
#
# Simulerar en flertillgångsportfölj (Global/Sverige/EM + räntekonto)
# dag för dag i gemensam basvaluta (SEK), med:
#   - periodisk rebalansering (samma schema för KI-strategi och B&H)
#   - KI-styrd avriskning/återköp med valbar scope (hela / Sverige /
#     Sverige+EM) och valbar avriskningsgrad
#   - räntekonto som förräntas dagligen (kalenderdagskorrekt), med fast
#     ränta, nollränta eller historisk svensk kortränta (Riksbanken)
#   - valfria insättningar (månadssparande/engångsbelopp) som placeras
#     enligt dagens målvikter
# ============================================================

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def validate_weights(weights: dict[str, float], tol: float = 1e-6) -> bool:
    return abs(sum(weights.values()) - 1.0) <= tol


def to_common_currency(price_usd: pd.Series, fx_usd_to_base: pd.Series) -> pd.Series:
    """Konverterar en USD-prisserie till basvalutan via en (framåtfylld) växelkurs."""
    # Behåll även tidigare FX-observationer på dagar utan ETF-pris.
    calendar = price_usd.index.union(fx_usd_to_base.index).sort_values()
    aligned_fx = fx_usd_to_base.reindex(calendar).ffill().reindex(price_usd.index)
    return price_usd * aligned_fx


def align_prices(prices: dict[str, pd.Series]) -> pd.DataFrame:
    """Slår ihop flera prisserier på en gemensam handelskalender (union, framåtfylld)."""
    df = pd.concat(prices, axis=1)
    df = df.sort_index().ffill()
    df = df.dropna(how="any")  # kräver att samtliga serier startat
    return df


def weighted_index(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Portföljens egna aktier som ett index (start 1), dagligen viktat enligt målvikterna.

    Används som trendreferens för trend-/RSI-villkoren, så att t.ex. en ren Global-portfölj
    följer Globals trend och inte Sveriges. Med en enda tillgång blir indexet samma serie
    som priset (skalat), så SMA/RSI-signalerna blir identiska.
    """
    keys = [k for k, w in weights.items() if w > 0 and k in prices.columns]
    if not keys or prices.empty:
        return pd.Series(dtype=float, name="Portfolio_Index")
    w = pd.Series({k: weights[k] for k in keys}, dtype=float)
    w = w / w.sum()
    rets = prices[keys].astype(float).pct_change().fillna(0.0)
    index = (1.0 + rets.mul(w, axis=1).sum(axis=1)).cumprod()
    return index.rename("Portfolio_Index")


def effective_rate_series(raw_rates: pd.Series | None, deduction_pct: float = 0.0,
                          floor_zero: bool = False) -> pd.Series | None:
    """Historisk årsränta (decimal) minus avdrag i procentenheter, valfritt med golv på 0 %."""
    if raw_rates is None:
        return None
    s = pd.Series(raw_rates, dtype=float).dropna().sort_index()
    if s.empty:
        return None
    s = s - float(deduction_pct) / 100.0
    if floor_zero:
        s = s.clip(lower=0.0)
    return s.rename("Rate")


def average_rate(rates: pd.Series | None, start, end, fallback: float = 0.0) -> float:
    """Genomsnittlig årsränta under perioden (dagsvärden framåtfyllda över kalenderdagar)."""
    if rates is None or len(rates) == 0:
        return fallback
    days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")
    if len(days) == 0:
        return fallback
    s = pd.Series(rates, dtype=float).sort_index()
    daily = s.reindex(s.index.union(days)).ffill().reindex(days)
    return float(daily.mean()) if daily.notna().any() else fallback


def compute_rebalance_dates(trading_days: pd.DatetimeIndex, freq: str) -> set:
    if freq == "none" or len(trading_days) == 0:
        return set()
    period_map = {"annual": "Y", "quarterly": "Q", "monthly": "M"}
    if freq not in period_map:
        return set()
    periods = pd.PeriodIndex(trading_days, freq=period_map[freq])
    tmp = pd.DataFrame({"date": trading_days, "period": periods})
    first_days = tmp.groupby("period")["date"].min()
    dates = set(pd.DatetimeIndex(first_days)) - {trading_days[0]}
    return dates


def _target_weights(base_weights: dict[str, float], scope_keys: set[str], multiplier: float) -> dict[str, float]:
    w = {}
    for k, base in base_weights.items():
        w[k] = base * (multiplier if k in scope_keys else 1.0)
    cash_w = 1.0 - sum(w.values())
    w["cash"] = max(cash_w, 0.0)
    return w


@dataclass
class PortfolioParams:
    base_weights: dict[str, float]
    rebalance_freq: str = "annual"
    scope_keys: set = field(default_factory=lambda: {"global", "sweden", "em"})
    derisk_pct: float = 50.0
    interest_mode: str = "fixed"  # "fixed" | "zero" | "historical"
    annual_interest_rate: float = 0.025
    # Endast för "historical": årsränta i decimalform per datum (redan justerad för avdrag/golv).
    # Dagar före första observationen använder annual_interest_rate.
    interest_rates: pd.Series | None = None
    initial_capital: float = 100_000.0
    apply_ki: bool = True  # False => ren Buy & Hold-simulering (KI-signaler ignoreras)
    cost_bps: float = 0.0
    slippage_bps: float = 0.0

    @property
    def risk_free_annual(self) -> float:
        if self.interest_mode == "historical":
            if self.interest_rates is not None and len(self.interest_rates):
                return float(pd.Series(self.interest_rates).mean())
            return self.annual_interest_rate
        return self.annual_interest_rate if self.interest_mode == "fixed" else 0.0


def _allocate(values: dict, target: dict, keys: list, rate: float) -> tuple[dict, float, float]:
    """Kostnad = (courtage + slippage)/10000 × faktiskt omsatt aktievärde.

    Lös nettoförmögenheten efter kostnad så målvikterna uppnås utan belåning.
    Kontantbenet kostnadsbeläggs inte en andra gång.
    """
    total = sum(values.values())
    low, high = 0.0, total
    for _ in range(80):
        net = (low + high) / 2
        turnover = sum(abs(net * target[k] - values[k]) for k in keys)
        if net + rate * turnover > total:
            high = net
        else:
            low = net
    net = (low + high) / 2 if rate else total
    turnover = sum(abs(net * target[k] - values[k]) for k in keys)
    return {k: net * target[k] for k in target}, rate * turnover, turnover


def _daily_cash_rates(dates: pd.DatetimeIndex, params: PortfolioParams) -> np.ndarray | None:
    """Årsränta som gäller från handelsdag i-1 till i (känd vid dag i-1). None = ingen förräntning."""
    if params.interest_mode == "zero":
        return None
    n = len(dates)
    if params.interest_mode == "historical" and params.interest_rates is not None and len(params.interest_rates):
        s = pd.Series(params.interest_rates, dtype=float).dropna().sort_index()
        pos = s.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
        out = np.full(n, float(params.annual_interest_rate))
        valid = pos >= 0
        out[valid] = s.to_numpy()[pos[valid]]
        return out
    return np.full(n, float(params.annual_interest_rate))


def simulate_portfolio(
    prices_base_ccy: pd.DataFrame,
    ki_exec_signals: pd.DataFrame | None,
    params: PortfolioParams,
    cash_flows: pd.Series | None = None,
) -> dict:
    """
    prices_base_ccy: DataFrame med kolumner som matchar params.base_weights.keys()
                      (t.ex. 'global','sweden','em'), redan i basvalutan, gemensam kalender.
    ki_exec_signals: DataFrame indexerad på Exec_Date (handelsdag) med kolumnen 'Signal'
                      (1=köp/återköp, -1=sälj/avriskning). None eller apply_ki=False => ingen KI-påverkan.

    cash_flows: valfri serie med insättningar (kr) per handelsdag i prices_base_ccy. Insättningen
                görs efter dagens kursrörelse och placeras enligt dagens målvikter (inklusive
                räntekontots andel när KI har avriskat). Ingen rebalansering av befintligt innehav.

    Returnerar dict med 'equity' (total, pd.Series), 'components' (DataFrame per sleeve,
    inkl. 'cash'), 'weights', 'risk_multiplier', 'transaction_costs', 'turnover' och 'flows'.
    Equity bär initial_capital i attrs för avkastningsmått inklusive initialköpets kostnad.
    """
    if not validate_weights(params.base_weights):
        raise ValueError(f"Portföljvikterna summerar inte till 100 %: {params.base_weights}")
    rate = (params.cost_bps + params.slippage_bps) / 10_000.0
    if not (np.isfinite(rate) and params.cost_bps >= 0 and params.slippage_bps >= 0 and rate < 1):
        raise ValueError("Kostnader måste vara ändliga, icke-negativa och totalt under 10000 bps")

    dates = prices_base_ccy.index
    n = len(dates)
    keys = list(params.base_weights.keys())

    rebalance_dates = compute_rebalance_dates(dates, params.rebalance_freq)

    # Signal per handelsdag: (riktning, exponering). Exponering anger hur stor del av den
    # avriskade andelen som är återinvesterad: 0 = fullt avriskad, 1 = normalt investerad.
    # Saknas kolumnen 'Exposure' gäller klassisk tolkning (sälj = 0, köp = 1).
    ki_signal_by_date: dict[pd.Timestamp, tuple[int, float]] = {}
    if params.apply_ki and ki_exec_signals is not None and not ki_exec_signals.empty:
        has_exposure = "Exposure" in ki_exec_signals.columns
        for d, row in ki_exec_signals.iterrows():
            s = int(row["Signal"])
            if has_exposure and pd.notna(row["Exposure"]):
                exposure = float(min(max(row["Exposure"], 0.0), 1.0))
            else:
                exposure = 0.0 if s == -1 else 1.0
            ki_signal_by_date[pd.Timestamp(d)] = (s, exposure)

    derisk = params.derisk_pct / 100.0

    def multiplier_for(exposure: float) -> float:
        return 1.0 - derisk * (1.0 - exposure)

    values = {k: 0.0 for k in keys}
    values["cash"] = 0.0
    multiplier = 1.0

    component_hist = {k: np.zeros(n) for k in keys}
    component_hist["cash"] = np.zeros(n)
    weight_hist = {k: np.zeros(n) for k in keys}
    weight_hist["cash"] = np.zeros(n)
    multiplier_hist = np.ones(n)
    total_hist = np.zeros(n)
    cost_hist = np.zeros(n)
    turnover_hist = np.zeros(n)

    events = []
    # NumPy-matris i stället för .iloc per dag: samma beräkning, betydligt snabbare.
    price_arr = prices_base_ccy[keys].to_numpy(dtype=float)
    cash_rates = _daily_cash_rates(dates, params)
    flow_arr = np.zeros(n)
    if cash_flows is not None and len(cash_flows):
        cf = pd.Series(cash_flows, dtype=float).groupby(level=0).sum()
        unknown = cf.index.difference(dates)
        if len(unknown):
            raise ValueError("Insättningar måste ligga på handelsdagar i priskalendern; mappa dem först.")
        flow_arr = cf.reindex(dates).fillna(0.0).to_numpy()
        if (flow_arr < 0).any():
            raise ValueError("Endast insättningar (positiva belopp) stöds.")

    for i, d in enumerate(dates):
        if i == 0:
            # En ev. KI-signal redan på startdagen påverkar den allra första allokeringen.
            sig0, exp0 = ki_signal_by_date.get(pd.Timestamp(d), (0, 1.0))
            if sig0 != 0:
                multiplier = multiplier_for(exp0)

            total = params.initial_capital
            tw = _target_weights(params.base_weights, params.scope_keys, multiplier)
            values["cash"] = total
            values, cost_hist[i], turnover_hist[i] = _allocate(values, tw, keys, rate)
        else:
            # 1) Organisk tillväxt av respektive sleeve enligt dagens prisrörelse.
            for j, k in enumerate(keys):
                prev_p = price_arr[i - 1, j]
                cur_p = price_arr[i, j]
                if prev_p and not np.isnan(prev_p) and not np.isnan(cur_p) and prev_p != 0:
                    values[k] = values[k] * (cur_p / prev_p)

            # 2) Räntekontot förräntas dagligen, korrekt över kalenderdagar (ej bara vid årsskiften).
            #    Räntan som gällde vid föregående handelsdag används för hela mellanperioden.
            elapsed_days = (dates[i] - dates[i - 1]).days
            if cash_rates is not None and elapsed_days > 0:
                values["cash"] = values["cash"] * (1.0 + cash_rates[i - 1]) ** (elapsed_days / 365.0)
            # interest_mode == "zero": ingen förräntning alls.

            # 3) KI-signal denna dag? (Endast om apply_ki=True.) Ändrar risk_multiplier
            #    och triggar en OMEDELBAR omallokering till nytt målvärde.
            sig, exposure = ki_signal_by_date.get(pd.Timestamp(d), (0, 1.0))
            if sig != 0:
                multiplier = multiplier_for(exposure)

            do_rebalance = (d in rebalance_dates) or (sig != 0)
            if do_rebalance:
                tw = _target_weights(params.base_weights, params.scope_keys, multiplier)
                before_total = sum(values.values())
                before_cash = values["cash"]
                values, cost_hist[i], turnover_hist[i] = _allocate(values, tw, keys, rate)
                if sig and turnover_hist[i] > 1e-8:
                    meta = ki_exec_signals.loc[d]
                    if isinstance(meta, pd.DataFrame):
                        meta = meta.iloc[-1]
                    events.append({"date": d, "signal_date": meta.get("Signal_Date", pd.NaT),
                                   "available_date": meta.get("Available_Date", pd.NaT),
                                   "ki": meta.get("Barometer", np.nan), "signal": sig,
                                   "type": meta.get("Signal_Type", None),
                                   "trigger": meta.get("Trigger", None),
                                   "exposure": exposure,
                                   "before": 1 - before_cash/before_total,
                                   "after": 1 - values["cash"]/sum(values.values()),
                                   "cash_change": values["cash"] - before_cash,
                                   "derisk_pct": params.derisk_pct, "reason": meta.get("Reason", "KI-signal")})

        # 4) Insättning: placeras enligt dagens målvikter, kostnad på aktiedelen.
        if flow_arr[i] > 0:
            tw_new = _target_weights(params.base_weights, params.scope_keys, multiplier)
            equity_share = 1.0 - tw_new["cash"]
            net = flow_arr[i] / (1.0 + rate * equity_share)
            for k in keys:
                values[k] += net * tw_new[k]
            values["cash"] += net * tw_new["cash"]
            cost_hist[i] += flow_arr[i] - net
            turnover_hist[i] += net * equity_share

        total_now = sum(values[k] for k in keys) + values["cash"]
        for k in keys:
            component_hist[k][i] = values[k]
            weight_hist[k][i] = values[k] / total_now if total_now > 0 else 0.0
        component_hist["cash"][i] = values["cash"]
        weight_hist["cash"][i] = values["cash"] / total_now if total_now > 0 else 0.0
        multiplier_hist[i] = multiplier
        total_hist[i] = total_now

    components_df = pd.DataFrame(component_hist, index=dates)
    weights_df = pd.DataFrame(weight_hist, index=dates)
    equity = pd.Series(total_hist, index=dates, name="Equity")
    equity.attrs["initial_capital"] = params.initial_capital
    multiplier_series = pd.Series(multiplier_hist, index=dates, name="Risk_Multiplier")

    return {
        "events": events,
        "equity": equity,
        "components": components_df,
        "weights": weights_df,
        "risk_multiplier": multiplier_series,
        "transaction_costs": pd.Series(cost_hist, index=dates, name="Transaction_Costs"),
        "turnover": pd.Series(turnover_hist, index=dates, name="Turnover"),
        "flows": pd.Series(flow_arr, index=dates, name="Flows"),
    }


def run_ki_vs_bnh(
    prices_base_ccy: pd.DataFrame,
    ki_exec_signals: pd.DataFrame | None,
    params: PortfolioParams,
) -> dict:
    """Kör KI-styrd variant och dess Buy & Hold-benchmark med EXAKT samma
    rebalanseringsschema, så att jämförelsen är rättvis (krav 10)."""
    ki_params = params
    bnh_params = dataclasses.replace(params, apply_ki=False)
    ki_result = simulate_portfolio(prices_base_ccy, ki_exec_signals, ki_params)
    bnh_result = simulate_portfolio(prices_base_ccy, None, bnh_params)
    return {"ki": ki_result, "bnh": bnh_result}
