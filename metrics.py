# ============================================================
# metrics.py
# ------------------------------------------------------------
# Avkastnings- och riskmått. Rena funktioner på NumPy/Pandas-
# serier, oberoende av Streamlit och av vilken backtestmotor
# som producerade kurvan.
# ============================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Portföljkurvor kan bära attrs["initial_capital"] för mått som ska inkludera
# initialköpets kostnad. Vanliga serier behåller tidigare beteende.
TRADING_DAYS_PER_YEAR = 252


def compute_drawdown(equity: np.ndarray, initial_capital: float | None = None) -> np.ndarray:
    peak = np.maximum.accumulate(equity)
    if initial_capital is not None:
        peak = np.maximum(peak, initial_capital)
    peak = np.where(peak == 0, np.nan, peak)
    return (equity - peak) / peak * 100.0


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return float("nan")
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-6)
    ratio = equity.iloc[-1] / equity.attrs.get("initial_capital", equity.iloc[0])
    if ratio <= 0:
        return -100.0
    return (ratio ** (1.0 / years) - 1.0) * 100.0


def total_return(equity: pd.Series) -> float:
    if len(equity) < 1 or equity.iloc[0] == 0:
        return float("nan")
    return (equity.iloc[-1] / equity.attrs.get("initial_capital", equity.iloc[0]) - 1.0) * 100.0


def max_drawdown(equity: pd.Series) -> float:
    dd = compute_drawdown(equity.to_numpy(), equity.attrs.get("initial_capital"))
    if len(dd) == 0 or np.all(np.isnan(dd)):
        return float("nan")
    return float(np.nanmin(dd))


def _daily_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def sharpe_ratio(equity: pd.Series, risk_free_annual: float = 0.0) -> float:
    r = _daily_returns(equity)
    if len(r) < 2:
        return float("nan")
    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = r - rf_daily
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(excess.mean() / std * math.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(equity: pd.Series, risk_free_annual: float = 0.0) -> float:
    r = _daily_returns(equity)
    if len(r) < 2:
        return float("nan")
    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = r - rf_daily
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("nan")
    downside_std = downside.std(ddof=1)
    if downside_std == 0 or np.isnan(downside_std):
        return float("nan")
    return float(excess.mean() / downside_std * math.sqrt(TRADING_DAYS_PER_YEAR))


def calmar_ratio(equity: pd.Series) -> float:
    c = cagr(equity)
    mdd = max_drawdown(equity)
    if np.isnan(c) or np.isnan(mdd) or mdd == 0:
        return float("nan")
    return float(c / abs(mdd))


def exposure_pct(position: pd.Series) -> float:
    if len(position) == 0:
        return float("nan")
    return float((position != 0).sum() / len(position) * 100.0)


@dataclass
class TradeStats:
    """Affärsstatistik som strikt separerar avslutade affärer från ev. öppen affär."""

    n_closed: int = 0
    n_open: int = 0
    win_rate_pct: float | None = None
    profit_factor: float | None = None  # None om ej beräkningsbart, float("inf") vid oändlig PF
    gross_profit: float = 0.0
    gross_loss: float = 0.0


def compute_trade_stats(trades: list[dict]) -> TradeStats:
    """
    trades: lista av dicts med minst nycklarna 'pnl' (realiserad kronor/dollar-P&L)
    och 'status' ('closed' eller 'open').

    Profit Factor beräknas på FAKTISK REALISERAD P&L (gross profit / gross loss),
    inte på summerade procentavkastningar - och exkluderar alltid ev. öppen affär.
    """
    closed = [t for t in trades if t.get("status") == "closed"]
    open_trades = [t for t in trades if t.get("status") == "open"]

    stats = TradeStats(n_closed=len(closed), n_open=len(open_trades))
    if not closed:
        return stats

    winning = [t for t in closed if t["pnl"] > 0]
    losing = [t for t in closed if t["pnl"] < 0]

    stats.win_rate_pct = len(winning) / len(closed) * 100.0
    stats.gross_profit = sum(t["pnl"] for t in winning)
    stats.gross_loss = abs(sum(t["pnl"] for t in losing))

    if stats.gross_loss > 0:
        stats.profit_factor = stats.gross_profit / stats.gross_loss
    elif stats.gross_profit > 0:
        stats.profit_factor = float("inf")  # inga förlustaffärer alls
    else:
        stats.profit_factor = None  # varken vinst eller förlust att dela på

    return stats


def format_profit_factor(pf: float | None) -> str:
    if pf is None:
        return "N/A - inga förlustaffärer"
    if math.isinf(pf):
        return "∞"
    return f"{pf:.2f}"


@dataclass
class RiskReport:
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    calmar: float
    exposure_pct: float
    final_value: float
    trade_stats: TradeStats = field(default_factory=TradeStats)


def build_risk_report(equity: pd.Series, position: pd.Series, trades: list[dict], risk_free_annual: float = 0.0) -> RiskReport:
    return RiskReport(
        total_return_pct=total_return(equity),
        cagr_pct=cagr(equity),
        max_drawdown_pct=max_drawdown(equity),
        sharpe=sharpe_ratio(equity, risk_free_annual),
        sortino=sortino_ratio(equity, risk_free_annual),
        calmar=calmar_ratio(equity),
        exposure_pct=exposure_pct(position),
        final_value=float(equity.iloc[-1]) if len(equity) else float("nan"),
        trade_stats=compute_trade_stats(trades),
    )
