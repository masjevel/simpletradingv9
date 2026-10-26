# ============================================================
# charts.py
# ------------------------------------------------------------
# Bygger Plotly-figurer. Inga Streamlit-anrop här - varje
# funktion returnerar en go.Figure som app.py sedan renderar
# med st.plotly_chart().
# ============================================================

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COMMON_LAYOUT = dict(
    hovermode="x unified",
    margin=dict(l=10, r=10, t=60, b=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)
GRID = dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)")


def build_trend_heatmap_chart(df: pd.DataFrame, ticker: str, sma_period: int, color_cap: int, signal_markers: dict) -> go.Figure:
    fig = go.Figure()

    pos_mask = df["Streak"] > 0
    fig.add_trace(
        go.Bar(
            x=df.index[pos_mask],
            y=(df["Close"] - df["SMA"])[pos_mask],
            base=df["SMA"][pos_mask],
            marker=dict(color=df["Streak"][pos_mask], colorscale=[[0, "#e6ffe6"], [1, "#004d00"]], cmin=0, cmax=color_cap, line_width=0),
            name="Positiv Trend",
            hoverinfo="skip",
        )
    )
    neg_mask = df["Streak"] < 0
    fig.add_trace(
        go.Bar(
            x=df.index[neg_mask],
            y=(df["Close"] - df["SMA"])[neg_mask],
            base=df["SMA"][neg_mask],
            marker=dict(color=df["Streak"][neg_mask].abs(), colorscale=[[0, "#ffe6e6"], [1, "#800000"]], cmin=0, cmax=color_cap, line_width=0),
            name="Negativ Trend",
            hoverinfo="skip",
        )
    )
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], mode="lines", name=f"SMA {sma_period}", line=dict(color="#3498db", width=1.2)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name=f"Pris ({ticker})", line=dict(color="#f1c40f", width=1.8)))

    marker_style = {
        "buy_neg": dict(symbol="triangle-up", color="rgba(46, 204, 113, 0.8)", size=10, line=dict(color="black", width=1)),
        "buy_pos": dict(symbol="triangle-up", color="#00d2d3", size=12, line=dict(color="white", width=1)),
        "sell": dict(symbol="triangle-down", color="rgba(231, 76, 60, 0.85)", size=10, line=dict(color="black", width=1)),
        "vix_buy_neg": dict(symbol="diamond", color="#1dd1a1", size=14, line=dict(color="black", width=1.5)),
        "vix_buy_pos": dict(symbol="diamond", color="#ff9ff3", size=14, line=dict(color="white", width=1.5)),
    }
    names = {
        "buy_neg": "Köp (Negativ Trend)",
        "buy_pos": "Köp (Positiv Trend)",
        "sell": "MACD Vändning (Sälj)",
        "vix_buy_neg": "VIX Panik (Negativ Trend)",
        "vix_buy_pos": "VIX Panik (Positiv Trend)",
    }
    for key, style in marker_style.items():
        dates_, prices_ = signal_markers.get(key, ([], []))
        fig.add_trace(go.Scatter(x=dates_, y=prices_, mode="markers", name=names[key], marker=style))

    fig.update_layout(yaxis_title="Pris", bargap=0, **COMMON_LAYOUT)
    fig.update_xaxes(rangeslider=dict(visible=False), type="date", **GRID)
    fig.update_yaxes(**GRID)
    return fig


OVERLAY_STYLES = {
    "vix": dict(symbol="diamond", color="#1dd1a1", size=13, line=dict(color="black", width=1.2)),
    "rsi": dict(symbol="circle", color="#54a0ff", size=10, line=dict(color="black", width=1)),
}


def build_ki_chart(df_combo: pd.DataFrame, ticker: str, sell_threshold: float, buy_threshold: float, buy_dates, sell_dates, overlays: dict | None = None) -> go.Figure:
    """overlays: {"vix": (namn, datum), "rsi": (namn, datum)} – valbara tekniska lager i KI-grafen."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if df_combo.empty:
        return fig

    normalized = (df_combo["Close"] / df_combo["Close"].iloc[0]) * 100.0
    fig.add_trace(go.Scatter(x=df_combo.index, y=normalized, mode="lines", name=f"{ticker} (Bas 100)", line=dict(color="#f1c40f", width=1.8)), secondary_y=False)

    fig.add_trace(
        go.Scatter(x=df_combo.index, y=df_combo["Barometer"], mode="lines", name="Barometerindikator (KI)", line=dict(color="rgba(180,180,180,0.7)", width=2)),
        secondary_y=True,
    )
    fig.add_hline(y=sell_threshold, line_dash="dash", line_color="rgba(231,76,60,0.8)", annotation_text=f"Sälj ({sell_threshold})", annotation_position="top left", secondary_y=True)
    fig.add_hline(y=buy_threshold, line_dash="dash", line_color="rgba(46,204,113,0.8)", annotation_text=f"Köp ({buy_threshold})", annotation_position="bottom left", secondary_y=True)

    if len(buy_dates) > 0:
        buy_y = [normalized.iloc[min(normalized.index.searchsorted(d), len(normalized) - 1)] for d in buy_dates]
        fig.add_trace(go.Scatter(x=buy_dates, y=buy_y, mode="markers", name="KÖP (KI-signal)", marker=dict(symbol="triangle-up", color="#2ecc71", size=14, line=dict(color="black", width=1.5))), secondary_y=False)
    if len(sell_dates) > 0:
        sell_y = [normalized.iloc[min(normalized.index.searchsorted(d), len(normalized) - 1)] for d in sell_dates]
        fig.add_trace(go.Scatter(x=sell_dates, y=sell_y, mode="markers", name="SÄLJ (KI-signal)", marker=dict(symbol="triangle-down", color="#e74c3c", size=14, line=dict(color="black", width=1.5))), secondary_y=False)
    for key, (name, dates_) in (overlays or {}).items():
        dates_ = [d for d in dates_ if normalized.index[0] <= d <= normalized.index[-1]]
        if not dates_:
            continue
        ys = [normalized.iloc[min(normalized.index.searchsorted(d), len(normalized) - 1)] for d in dates_]
        fig.add_trace(go.Scatter(x=dates_, y=ys, mode="markers", name=name, marker=OVERLAY_STYLES.get(key, {})), secondary_y=False)

    fig.update_layout(**COMMON_LAYOUT)
    fig.update_yaxes(title_text="Normaliserat Pris (Start = 100)", secondary_y=False, **GRID)
    fig.update_yaxes(title_text="Barometerindikator", secondary_y=True, showgrid=False)
    fig.update_xaxes(**GRID)
    return fig


def build_equity_drawdown_chart(strategy_equity: pd.Series, bnh_equity: pd.Series, strategy_dd, bnh_dd, strategy_name: str = "Strategi") -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.65, 0.35], subplot_titles=["Portföljens kapitalutveckling", "Historisk Drawdown (%)"])

    fig.add_trace(go.Scatter(x=strategy_equity.index, y=strategy_equity.values, mode="lines", name=strategy_name, line=dict(color="#00d2d3", width=2.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=bnh_equity.index, y=bnh_equity.values, mode="lines", name="Köp & Behåll (Buy & Hold)", line=dict(color="rgba(149,165,166,0.8)", width=1.5, dash="dash")), row=1, col=1)

    fig.add_trace(go.Scatter(x=strategy_equity.index, y=strategy_dd, mode="lines", name=f"Drawdown: {strategy_name}", line=dict(color="#e74c3c", width=1.5), fill="tozeroy", fillcolor="rgba(231,76,60,0.15)"), row=2, col=1)
    fig.add_trace(go.Scatter(x=bnh_equity.index, y=bnh_dd, mode="lines", name="Drawdown: Buy & Hold", line=dict(color="rgba(127,140,141,0.6)", width=1.2, dash="dot"), fill="tozeroy", fillcolor="rgba(127,140,141,0.08)"), row=2, col=1)

    fig.update_layout(xaxis2=dict(type="date"), **COMMON_LAYOUT)
    fig.update_yaxes(title_text="Portföljvärde", row=1, col=1, **GRID)
    fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1, **GRID)
    fig.update_xaxes(**GRID)
    return fig


def build_allocation_chart(weights_df: pd.DataFrame, label_map: dict) -> go.Figure:
    fig = go.Figure()
    for col in weights_df.columns:
        fig.add_trace(go.Scatter(x=weights_df.index, y=weights_df[col] * 100.0, mode="lines", stackgroup="one", name=label_map.get(col, col)))
    fig.update_layout(yaxis_title="Andel av portföljen (%)", **COMMON_LAYOUT)
    fig.update_xaxes(**GRID)
    fig.update_yaxes(range=[0, 100], **GRID)
    return fig


def build_ki_indicator_chart(ki_signals: pd.DataFrame, sell_threshold: float, buy_threshold: float, floor_threshold: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ki_signals.index, y=ki_signals["Barometer"], mode="lines", name="Barometerindikator", line=dict(color="#3498db", width=2)))
    fig.add_hline(y=sell_threshold, line_dash="dash", line_color="rgba(231,76,60,0.8)", annotation_text=f"Säljgräns ({sell_threshold})")
    fig.add_hline(y=buy_threshold, line_dash="dash", line_color="rgba(46,204,113,0.8)", annotation_text=f"Köpgräns ({buy_threshold})")
    fig.add_hline(y=floor_threshold, line_dash="dot", line_color="rgba(149,165,166,0.6)", annotation_text=f"Golv för återköp ({floor_threshold})")

    sells = ki_signals[ki_signals["Signal"] == -1]
    buys = ki_signals[ki_signals["Signal"] == 1]
    fig.add_trace(go.Scatter(x=sells.index, y=sells["Barometer"], mode="markers", name="▼ KI AVRISKNING", marker=dict(symbol="triangle-down", color="#e74c3c", size=13, line=dict(color="black", width=1))))
    fig.add_trace(go.Scatter(x=buys.index, y=buys["Barometer"], mode="markers", name="▲ KI ÅTERKÖP", marker=dict(symbol="triangle-up", color="#2ecc71", size=13, line=dict(color="black", width=1))))

    fig.update_layout(yaxis_title="Barometerindikator", **COMMON_LAYOUT)
    fig.update_xaxes(**GRID)
    fig.update_yaxes(**GRID)
    return fig


def technical_events(trades):
    events = []
    for trade in trades:
        for side, prefix in ((1, "entry"), (-1, "exit")):
            if side == -1 and trade["status"] != "closed":
                continue
            values = trade.get(prefix + "_indicators", {})
            events.append({"date": trade[prefix + "_date"], "signal": side,
                           "label": "▲ KÖP" if side == 1 else "▼ SÄLJ",
                           "hover": f"Signaltyp: {trade.get('signal_type') if side == 1 else trade.get('exit_signal_type')}<br>"
                           f"Signaldatum: {trade.get(prefix + '_signal_date')}<br>"
                           f"Executionsdatum: {trade[prefix + '_date']}<br>"
                           f"Executionspris: {trade[prefix + '_price']:.2f}<br>" +
                           "<br>".join(f"{k}: {v:.2f}" for k, v in values.items())})
    return events


# Symbol, kort etikett och förklarande namn per återköpsorsak (se reentry.py).
TRIGGER_MARKERS = {
    "ki": ("triangle-up", "▲ KI", "Återköp: KI-vändning"),
    "vix": ("diamond", "◆ VIX", "Återköp: VIX-panik"),
    "credit": ("square", "■ KREDIT", "Återköp: kreditspread"),
    "rsi": ("circle", "● RSI", "Återköp: köp (negativ trend)"),
    "trend": ("triangle-up-open", "△ TREND", "Återköp: trendvändning"),
    "time": ("star", "★ TIDSSPÄRR", "Återköp: tidsspärr"),
}


def _event_marker(e):
    """(symbol, etikett, legendgrupp) för en KI-portföljhändelse."""
    if e["signal"] == -1:
        return "triangle-down", f"▼ AVRISKNING {e['derisk_pct']:g} %", "Sälj / avriskning"
    trig = e.get("trigger")
    if not isinstance(trig, str) or not trig:
        return "triangle-up", "▲ ÅTERKÖP", "Köp / återköp"
    parts = trig.split("+")
    symbol, _, group = TRIGGER_MARKERS.get(parts[-1], ("triangle-up", "▲", "Köp / återköp"))
    label = " + ".join(TRIGGER_MARKERS.get(p, ("", p, ""))[1] for p in parts)
    exp = e.get("exposure", 1.0)
    if exp is not None and exp < 0.999:
        label += f" ({exp:.0%})"
    return symbol, label, group


def _portfolio_hover(e):
    ki = e.get("ki")
    ki_txt = f"{ki:.2f}" if isinstance(ki, (int, float)) and pd.notna(ki) else "–"
    head = f"{e['type']}<br>" if isinstance(e.get("type"), str) else ""
    return (head + f"{e.get('reason', 'KI-signal')}<br>KI-värde: {ki_txt}<br>Signaldatum: {e['signal_date']}<br>"
            f"Tillgänglig för handel: {e['available_date']}<br>Handelsdatum: {e['date']}<br>"
            f"Aktieandel före: {e['before']:.1%}<br>Aktieandel efter: {e['after']:.1%}<br>"
            f"Belopp {'till' if e['cash_change'] >= 0 else 'från'} räntekonto: {abs(e['cash_change']):,.2f} kr")


def portfolio_events(events):
    out = []
    for e in events:
        symbol, label, group = _event_marker(e)
        out.append({**e, "label": label, "symbol": symbol, "group": group, "hover": _portfolio_hover(e)})
    return out


def add_transactions(fig, equity, events, invested, show_text: bool = True):
    """Annotera faktiska exekveringar på kapitalserien, aldrig obekräftade signaler.

    Bakgrund: grön = fullt investerad, gul = delvis återköpt (trappa), grå = avriskad/kassa.
    """
    if len(equity) == 0:
        return fig
    inv = invested.reindex(equity.index).fillna(0).to_numpy(dtype=float)
    floor = float(np.nanmin(inv)) if len(inv) else 0.0
    level = np.where(inv > .999, 2, np.where(inv > floor + 1e-6, 1, 0))
    colors = {2: "rgba(46,204,113,0.055)", 1: "rgba(241,196,15,0.08)", 0: "rgba(140,140,140,0.045)"}
    starts = [0] + [i for i in range(1, len(level)) if level[i] != level[i-1]]
    for start, end in zip(starts, starts[1:] + [len(level)-1]):
        fig.add_vrect(x0=equity.index[start], x1=equity.index[end], fillcolor=colors[int(level[start])],
                      line_width=0, layer="below", row=1, col=1)
    groups: dict = {}
    for e in events:
        if e['date'] not in equity.index:
            continue
        default_group = "Köp / återköp" if e['signal'] == 1 else "Sälj / avriskning"
        key = (e['signal'], e.get('group', default_group), e.get('symbol'))
        groups.setdefault(key, []).append(e)
    for (side, group_name, symbol), group in groups.items():
        color = "#20bf6b" if side == 1 else "#eb3b5a"
        fig.add_trace(go.Scatter(x=[e['date'] for e in group], y=[equity.loc[e['date']] for e in group],
                                 mode="markers+text" if show_text else "markers", text=[e['label'] for e in group],
                                 textposition="top center" if side == 1 else "bottom center",
                                 textfont=dict(size=12, color=color),
                                 marker=dict(size=17, symbol=symbol or ("triangle-up" if side == 1 else "triangle-down"),
                                             color=color, line=dict(color="white", width=1)),
                                 customdata=[e['hover'] for e in group], hovertemplate="%{customdata}<extra></extra>",
                                 name=group_name, cliponaxis=False), row=1, col=1)
        for e in group:
            fig.add_vline(x=e['date'], line_width=1, line_dash="dash", line_color=color, row=1, col=1)
    fig.update_layout(hovermode="closest", height=650,
                      legend=dict(orientation="h", yanchor="top", y=-0.15, x=0),
                      margin=dict(l=10, r=10, t=55, b=110))
    return fig


def add_time_stop_lines(fig, deadlines, start, end):
    """Prickad linje där tidsspärren skulle tvinga fram återköp (visas även om den aldrig behövdes)."""
    for d in deadlines:
        if d is None or not (start <= d <= end):
            continue
        fig.add_shape(type="line", x0=d, x1=d, y0=0, y1=1, yref="y domain", xref="x",
                      line=dict(color="rgba(155,89,182,0.8)", width=1.5, dash="dot"), row=1, col=1)
        fig.add_annotation(x=d, y=1, yref="y domain", xref="x", text="Tidsspärr", showarrow=False,
                           font=dict(size=10, color="rgba(155,89,182,1)"), yanchor="bottom")
    return fig


def build_exposure_chart(equity_share: pd.Series) -> go.Figure:
    """Aktieandel 0–100 % över tid. Visar trappan tydligt: andelen kliver upp i steg."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_share.index, y=equity_share.values * 100, mode="lines", line_shape="hv",
                             name="Aktieandel", line=dict(color="#00a8a8", width=2), fill="tozeroy",
                             fillcolor="rgba(0,168,168,0.12)"))
    fig.update_layout(yaxis_title="Aktieandel (%)", height=230, showlegend=False,
                      **{**COMMON_LAYOUT, "margin": dict(l=10, r=10, t=20, b=10)})
    fig.update_xaxes(**GRID)
    fig.update_yaxes(range=[0, 105], **GRID)
    return fig


def build_robustness_heatmap(table: pd.DataFrame, value_col: str, title: str, current=None) -> go.Figure:
    """Rader = bekräftande månader, kolumner = säljgräns. Nuvarande val markeras med ram."""
    pivot = table.pivot(index="Månader", columns="Säljgräns", values=value_col)
    fig = go.Figure(go.Heatmap(z=pivot.values, x=[str(c) for c in pivot.columns], y=[f"{r} mån" for r in pivot.index],
                               colorscale="RdYlGn", zmid=0 if pivot.min().min() < 0 < pivot.max().max() else None,
                               text=[[f"{v:+.1f}" if pd.notna(v) else "" for v in row] for row in pivot.values],
                               texttemplate="%{text}", hovertemplate="Säljgräns %{x} · %{y}<br>%{z:.2f}<extra></extra>",
                               colorbar=dict(title="", thickness=10)))
    if current is not None and current[0] in pivot.columns and current[1] in pivot.index:
        x = list(pivot.columns).index(current[0])
        y = list(pivot.index).index(current[1])
        fig.add_shape(type="rect", x0=x-.5, x1=x+.5, y0=y-.5, y1=y+.5, line=dict(color="black", width=3))
    fig.update_layout(title=dict(text=title, font=dict(size=13)), height=300, margin=dict(l=10, r=10, t=40, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title="Säljgräns (KI)", type="category")
    fig.update_yaxes(type="category")
    return fig


def trade_log(trades):
    rows = []
    for t in trades:
        closed = t['status'] == 'closed'
        rows.append({"Signaldatum köp": t.get('entry_signal_date'), "Köpdatum": t['entry_date'],
                     "Köpsignal": t['signal_type'], "Köpkurs": t['entry_price'],
                     "Signaldatum sälj": t.get('exit_signal_date') if closed else None,
                     "Säljdatum": t['exit_date'] if closed else None,
                     "Säljsignal": t.get('exit_signal_type') if closed else None,
                     "Säljkurs": t['exit_price'] if closed else None,
                     "Avkastning": f"{t['return_pct']:+.2f} %", "Hålltid": f"{t['days']} dagar",
                     "Status": "Stängd" if closed else "Öppen (orealiserad)", "Resultat i USD": t['pnl']})
    return pd.DataFrame(rows)


def build_savings_chart(ki_equity: pd.Series, bnh_equity: pd.Series, invested: pd.Series,
                        extra_deposits: pd.Series | None = None, ki_cash_share: pd.Series | None = None,
                        extra_labels: list | None = None) -> go.Figure:
    """Värde för KI-strategi och köp och behåll med samma sparplan, mot insatt kapital."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=invested.index, y=invested.values, mode="lines", name="Insatt kapital",
                             line=dict(color="rgba(127,140,141,0.9)", width=1.5, shape="hv"),
                             fill="tozeroy", fillcolor="rgba(127,140,141,0.12)",
                             hovertemplate="Insatt: %{y:,.0f} kr<extra></extra>"))
    fig.add_trace(go.Scatter(x=bnh_equity.index, y=bnh_equity.values, mode="lines", name="Köp och behåll",
                             line=dict(color="#e67e22", width=1.8), hovertemplate="Köp och behåll: %{y:,.0f} kr<extra></extra>"))
    custom = None if ki_cash_share is None else (ki_cash_share.reindex(ki_equity.index).fillna(0.0) * 100).to_numpy()
    fig.add_trace(go.Scatter(x=ki_equity.index, y=ki_equity.values, mode="lines", name="KI-strategi",
                             line=dict(color="#00a8a8", width=2.2), customdata=custom,
                             hovertemplate="KI-strategi: %{y:,.0f} kr" + (" (räntekonto %{customdata:.0f} %)" if custom is not None else "") + "<extra></extra>"))
    if extra_deposits is not None and len(extra_deposits):
        y = bnh_equity.reindex(extra_deposits.index)
        fig.add_trace(go.Scatter(x=extra_deposits.index, y=y.values, mode="markers+text", name="Extra insättning",
                                 marker=dict(symbol="star", size=14, color="#8e44ad", line=dict(color="black", width=1)),
                                 text=[f"+{v:,.0f}".replace(",", " ") for v in extra_deposits.values], textposition="top center",
                                 customdata=extra_labels if extra_labels is not None else [""] * len(extra_deposits),
                                 hovertemplate="Extra insättning %{text} kr %{customdata}<extra></extra>"))
    fig.update_layout(yaxis_title="Värde (kr)", separators=", ", **COMMON_LAYOUT)
    fig.update_xaxes(**GRID)
    fig.update_yaxes(tickformat=",.0f", **GRID)
    return fig


def build_start_year_chart(table: pd.DataFrame) -> go.Figure:
    """Pengaviktad årsavkastning per startår för samma sparplan."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=table["Startår"], y=table["Köp och behåll (%/år)"], name="Köp och behåll", marker_color="#e67e22"))
    fig.add_trace(go.Bar(x=table["Startår"], y=table["KI-strategi (%/år)"], name="KI-strategi", marker_color="#00a8a8"))
    fig.update_layout(barmode="group", yaxis_title="Årsavkastning på insättningarna (%)", xaxis_title="Startår (januari)", **COMMON_LAYOUT)
    fig.update_xaxes(type="category", **GRID)
    fig.update_yaxes(**GRID)
    return fig
