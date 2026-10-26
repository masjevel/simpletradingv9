"""Shared, testable helpers for periods, pending trend orders and diagnostics."""
from __future__ import annotations

import pandas as pd
import numpy as np


def select_period(frame, start=None, end=None):
    if start is not None and end is not None and pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("Startdatum måste vara före eller samma dag som slutdatum.")
    return frame.loc[start:end].copy()


def trend_orders(orders, reference, calendar, window=200):
    """Hold KI buys until the PREVIOUS close exceeds its SMA. A sell cancels a pending buy.

    Run on full history before slicing the test window to preserve the starting state.
    """
    calendar = pd.DatetimeIndex(calendar)
    if orders.empty:
        return orders.copy()
    reference = reference.sort_index()
    ok = (reference > reference.rolling(window, min_periods=window).mean())
    # Reindex first, shift second: never use today's close for today's execution.
    ok = ok.reindex(calendar).fillna(False).shift(1, fill_value=False)
    incoming = {pd.Timestamp(d): row.to_dict() for d, row in orders.iterrows()}
    pending = None
    rows = []
    for d in calendar:
        order = incoming.get(d)
        if order is not None:
            if order['Signal'] == -1:
                pending = None
                rows.append(dict(order, Exec_Date=d))
            else:
                pending = order
        if pending is not None and bool(ok.loc[d]):
            rows.append(dict(pending, Exec_Date=d, Reason=str(pending.get('Reason', 'KI återköp')) +
                             f'; föregående stängning över SMA {window}'))
            pending = None
    if not rows:
        return orders.iloc[:0].copy()
    return pd.DataFrame(rows).set_index('Exec_Date')


def orders_for_period(orders, calendar):
    """Seed only the last known position before the start; do not replay old trades."""
    if len(calendar) == 0 or orders.empty:
        return orders.iloc[:0].copy()
    start, end = calendar[0], calendar[-1]
    current = orders.loc[(orders.index >= start) & (orders.index <= end)].copy()
    prior = orders.loc[orders.index < start]
    if not prior.empty and start not in current.index:
        seed = prior.iloc[[-1]].copy()
        seed.index = pd.DatetimeIndex([start], name=orders.index.name)
        seed['Reason'] = 'Startläge från senast kända KI-/trendbeslut. ' + seed.get('Reason', pd.Series('', index=seed.index)).fillna('')
        current = pd.concat([seed, current])
    return current


def longest_underwater_days(equity):
    if equity.empty:
        return 0
    peak = float(equity.attrs.get('initial_capital', equity.iloc[0]))
    peak_date = equity.index[0]
    longest = 0
    underwater = False
    for d, value in equity.items():
        if value < peak or underwater:
            longest = max(longest, (d - peak_date).days)
        underwater = value < peak
        if value >= peak:
            peak, peak_date = value, d
    return longest


def completed_cycles(events):
    """Antal sälj följt av FULLT återköp. Ett delsteg i en återköpstrappa räknas inte."""
    pending = False
    count = 0
    for event in events:
        if event['signal'] == -1:
            pending = True
        elif event['signal'] == 1 and pending and event.get('exposure', 1.0) >= 0.999:
            count += 1
            pending = False
    return count


def ki_trade_log(events):
    return pd.DataFrame([{
        'Handelsdatum': e['date'], 'Signalmånad': e['signal_date'],
        'Antaget tillgängligt': e['available_date'],
        'Åtgärd': 'Sälj' if e['signal'] == -1 else 'Återköp',
        'Utlösare': e.get('type') or ('KI SÄLJ' if e['signal'] == -1 else 'KI KÖP'),
        'KI': e['ki'], 'Förklaring': e.get('reason', ''),
        'Aktieandel före (%)': e['before'] * 100,
        'Aktieandel efter (%)': e['after'] * 100,
        'Till/från räntekonto (kr)': e['cash_change'],
    } for e in events])


def episode_starts(mask: pd.Series, cooldown_days: int = 15) -> pd.DatetimeIndex:
    """Första dagen i varje period där villkoret är sant (minst `cooldown_days` handelsdagar isär).

    Används för att visa EN markör per VIX-panik eller översåld period i grafen,
    i stället för en markör för varje dag villkoret råkar vara uppfyllt.
    """
    m = mask.fillna(False).astype(bool).to_numpy()
    out = []
    last = -10**9
    for i in range(len(m)):
        if m[i] and (i == 0 or not m[i - 1]) and i - last > cooldown_days:
            out.append(mask.index[i])
            last = i
    return pd.DatetimeIndex(out)


def sell_event_table(events, market: pd.Series, lookback_days: int = 365) -> pd.DataFrame:
    """Hur bra var varje försäljning? Mäts mot en marknadsserie (t.ex. köp och behåll).

    - Topp: högsta värdet från `lookback_days` före försäljningen till fullt återköp (eller slutet).
    - Dagar från topp: negativt = sålde före toppen, positivt = efter toppen.
    - Missad uppgång: hur mycket marknaden steg efter försäljningen innan toppen.
    - Största fall efter sälj: lägsta värdet före fullt återköp jämfört med säljdagen.
    - Återköpsnivå: marknaden vid fullt återköp jämfört med säljdagen (negativt = köpte billigare).
    """
    market = market.dropna().sort_index()
    rows = []
    sells = [e for e in events if e['signal'] == -1]
    for e in sells:
        d = pd.Timestamp(e['date'])
        if d not in market.index:
            continue
        later_buys = [b for b in events if b['signal'] == 1 and pd.Timestamp(b['date']) > d
                      and b.get('exposure', 1.0) >= 0.999]
        next_sell = [x for x in sells if pd.Timestamp(x['date']) > d]
        end = pd.Timestamp(later_buys[0]['date']) if later_buys else market.index[-1]
        if next_sell and pd.Timestamp(next_sell[0]['date']) < end:
            end = pd.Timestamp(next_sell[0]['date'])
        window = market.loc[d - pd.Timedelta(days=lookback_days):end]
        after = market.loc[d:end]
        sell_value = float(market.loc[d])
        top_date = window.idxmax()
        rows.append({
            'Säljdag': str(d.date()),
            'Topp (datum)': str(top_date.date()),
            'Dagar från topp': int((d - top_date).days),
            'Under toppen vid sälj (%)': (sell_value / float(window.max()) - 1) * 100,
            'Missad uppgång efter sälj (%)': (float(after.max()) / sell_value - 1) * 100,
            'Största fall efter sälj (%)': (float(after.min()) / sell_value - 1) * 100,
            'Fullt återköp': str(end.date()) if later_buys and end == pd.Timestamp(later_buys[0]['date']) else 'ej ännu',
            'Återköpsnivå mot sälj (%)': (float(market.loc[:end].iloc[-1]) / sell_value - 1) * 100,
            'Dagar utanför': int((end - d).days),
        })
    return pd.DataFrame(rows)
