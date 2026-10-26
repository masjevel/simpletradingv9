# ============================================================
# backtest.py
# ------------------------------------------------------------
# Backtestmotor för den TEKNISKA signalmodellen (RSI/MACD/VIX).
# Helt fristående från Streamlit - kan testas med pytest.
#
# Metodologiska principer (enligt kravspecifikation):
#  - En signal som uppstår vid stängning dag t exekveras TIDIGAST
#    nästa handelsdag (t+1), antingen till dess Open eller Close.
#  - Courtage och slippage (baspunkter) appliceras vid varje
#    exekvering.
#  - En öppen position vid periodens slut räknas INTE som en
#    avslutad affär i Win Rate/Profit Factor - den redovisas separat.
#  - Profit Factor beräknas på faktisk P&L i kronor/dollar (se metrics.py).
# ============================================================

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ExecutionParams:
    initial_capital: float = 10_000.0
    cost_bps: float = 0.0        # courtage/transaktionskostnad, baspunkter av affärsvärdet
    slippage_bps: float = 0.0    # slippage, baspunkter
    execution_method: str = "close"  # "close" eller "open" (nästa handelsdags pris)
    require_sma: bool = True  # legacy default; UI disables when trend is display-only


def _execution_price(row_price: float, side: str, params: ExecutionParams) -> float:
    """Applicerar slippage: köp blir dyrare, sälj blir billigare (konservativt antagande)."""
    slip = params.slippage_bps / 10_000.0
    if side == "buy":
        return row_price * (1.0 + slip)
    return row_price * (1.0 - slip)


def _cost_amount(trade_value: float, params: ExecutionParams) -> float:
    return abs(trade_value) * (params.cost_bps / 10_000.0)


def run_technical_backtest(df: pd.DataFrame, params: ExecutionParams) -> dict | None:
    """
    df måste innehålla: Close, Open (kan vara NaN om ej tillgänglig), SMA, Signal, Signal_Type.
    Rader med NaN i SMA (warm-up) exkluderas eftersom modellen förutsätter en beräknad trend.

    Returnerar dict med bl.a. 'equity' (pd.Series), 'position' (pd.Series),
    'trades' (list[dict] med 'status' in {'closed','open'} och 'pnl' i kronor/dollar),
    eller None om otillräcklig data.
    """
    valid_mask = df["SMA"].notna().to_numpy() if params.require_sma else df["Close"].notna().to_numpy()
    if not np.any(valid_mask):
        return None

    bt = df.loc[valid_mask].copy()
    n = len(bt)
    if n < 2:
        return None

    use_open = params.execution_method == "open" and "Open" in bt.columns and bt["Open"].notna().any()
    exec_col = "Open" if use_open else "Close"
    # Om Open saknas för enskilda rader, fall tillbaka till Close för just den raden.
    exec_prices = bt[exec_col].to_numpy()
    close_prices = bt["Close"].to_numpy()
    exec_prices = np.where(np.isnan(exec_prices), close_prices, exec_prices)

    sigs = bt["Signal"].to_numpy()
    sig_types = bt.get("Signal_Reason", bt["Signal_Type"]).to_numpy()
    dates = bt.index

    equity = np.zeros(n, dtype=float)
    position = np.zeros(n, dtype=int)

    cash = params.initial_capital
    shares = 0.0
    invested = False

    pending = None  # ("buy"/"sell", signal_type) - schemalagd för EXEKVERING vid rad i (dvs. t+1 relativt signaldagen)
    trades: list[dict] = []
    active_trade: dict | None = None

    for i in range(n):
        # 1) Exekvera order schemalagd från föregående dag (tidigast t+1 relativt signaldagen).
        if pending is not None:
            order_side, order_sig_type, signal_date, indicator_values = pending
            raw_price = exec_prices[i]

            if order_side == "buy" and not invested:
                px = _execution_price(raw_price, "buy", params)
                cost = _cost_amount(cash, params)
                usable_cash = cash - cost
                shares = usable_cash / px if px > 0 else 0.0
                cash = 0.0
                invested = True
                active_trade = {
                    "entry_signal_date": signal_date,
                    "entry_indicators": indicator_values,
                    "entry_date": dates[i],
                    "entry_price": px,
                    "shares": shares,
                    "signal_type": order_sig_type,
                    "entry_cost": cost,
                }

            elif order_side == "sell" and invested:
                px = _execution_price(raw_price, "sell", params)
                gross_proceeds = shares * px
                cost = _cost_amount(gross_proceeds, params)
                net_proceeds = gross_proceeds - cost
                cash = net_proceeds
                if active_trade is not None:
                    entry_value = active_trade["shares"] * active_trade["entry_price"] + active_trade["entry_cost"]
                    pnl = net_proceeds - entry_value
                    trades.append(
                        {
                            "entry_signal_date": active_trade["entry_signal_date"],
                            "entry_indicators": active_trade["entry_indicators"],
                            "entry_date": active_trade["entry_date"],
                            "exit_signal_date": signal_date,
                            "exit_signal_type": order_sig_type,
                            "exit_indicators": indicator_values,
                            "exit_date": dates[i],
                            "signal_type": active_trade["signal_type"],
                            "entry_price": active_trade["entry_price"],
                            "exit_price": px,
                            "return_pct": (px / active_trade["entry_price"] - 1.0) * 100.0,
                            "pnl": pnl,
                            "days": (dates[i] - active_trade["entry_date"]).days,
                            "status": "closed",
                        }
                    )
                    active_trade = None
                shares = 0.0
                invested = False

            pending = None

        # 2) Daglig marknadsvärdering.
        if invested:
            equity[i] = shares * close_prices[i]
            position[i] = 1
        else:
            equity[i] = cash
            position[i] = 0

        # 3) Schemalägg ev. ny order baserat på dagens signal (exekveras tidigast nästa rad => ingen look-ahead).
        current_sig = sigs[i]
        if current_sig == 1 and not invested and pending is None:
            pending = ("buy", sig_types[i] or "KÖP", dates[i], {k: bt.iloc[i].get(k, np.nan) for k in ("RSI", "SMA", "MACD", "MACD_Signal", "VIX")})
        elif current_sig == -1 and invested and pending is None:
            pending = ("sell", sig_types[i] or "SÄLJ", dates[i], {k: bt.iloc[i].get(k, np.nan) for k in ("RSI", "SMA", "MACD", "MACD_Signal", "VIX")})

    # Öppen position vid periodens slut - redovisas separat, räknas EJ som avslutad affär.
    if invested and active_trade is not None:
        current_value = active_trade["shares"] * close_prices[-1]
        entry_value = active_trade["shares"] * active_trade["entry_price"] + active_trade["entry_cost"]
        unrealized_pnl = current_value - entry_value
        trades.append(
            {
                "entry_signal_date": active_trade["entry_signal_date"],
                            "entry_indicators": active_trade["entry_indicators"],
                            "entry_date": active_trade["entry_date"],
                "exit_signal_date": None,
                "exit_signal_type": None,
                "exit_indicators": {},
                "exit_date": dates[-1],
                "signal_type": active_trade["signal_type"],
                "entry_price": active_trade["entry_price"],
                "exit_price": close_prices[-1],
                "return_pct": (close_prices[-1] / active_trade["entry_price"] - 1.0) * 100.0,
                "pnl": unrealized_pnl,
                "days": (dates[-1] - active_trade["entry_date"]).days,
                "status": "open",
            }
        )

    equity_series = pd.Series(equity, index=dates, name="Strategy_Equity")
    position_series = pd.Series(position, index=dates, name="Position")

    # Buy & Hold-jämförelse med samma startkapital, ingen kostnad (representerar en engångsaffär).
    bnh_shares = params.initial_capital / close_prices[0]
    bnh_equity = pd.Series(bnh_shares * close_prices, index=dates, name="BnH_Equity")

    return {
        "equity": equity_series,
        "bnh_equity": bnh_equity,
        "position": position_series,
        "trades": trades,
        "params": params,
    }
